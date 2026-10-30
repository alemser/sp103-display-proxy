"""Telas de informação: recebe da fonte o que está tocando (docs/api-telas.md).

O Pico não sabe de onde vêm os dados: só conhece o contrato. Pede a cada 2 s ("SUB2" com
o bit das telas) e recebe um pacote "NP" quando algo muda e a cada 5 s:

    "NP" 0x01 flags  campo 0x1F campo ...     (flags: bit 0 = tocando, bit 1 = o lado acabou)

Os tempos valem no instante do envio. Com "tocando", o Pico conta sozinho a partir dali,
e só corrige a conta quando um pacote novo difere mais de RESYNC_S. Campo vazio = None.
Leve de propósito: um split por pacote, nada de JSON, e os tempos só são calculados na
hora de desenhar.
"""

import socket
import time

PORT = 7091
SUBSCRIBE = b"SUB2\x02"         # só as telas; o VU pede à parte (vu.py)
SUBSCRIBE_MS = 2000             # a fonte esquece o pedido em 6 s
STALE_MS = 15000                # sem pacote por 15 s: os dados não valem mais
RESYNC_S = 2
FLAG_PLAYING = 1
FLAG_SIDE_END = 2
FIELDS = ("artist", "title", "position", "elapsed", "duration", "side", "side_track", "side_tracks",
          "side_left", "stylus_hours", "stylus_wear")
NUMBERS = ("elapsed", "duration", "side_track", "side_tracks", "side_left", "stylus_hours", "stylus_wear")


class Info:
    def __init__(self):
        self.on = False
        self.addr = None
        self.sock = None
        self.last_sub = None
        self.last_packet = None
        self.packets = 0
        self.playing = False
        self.side_end = False
        self.data = {name: None for name in FIELDS}
        self.track_seq = 0              # muda a cada faixa nova (as telas temporárias recomeçam)
        self.side_start = False         # a faixa de agora é a primeira do lado
        self._base = 0                  # ticks_ms em que elapsed e side_left valiam o que está em data

    def configure(self, on, source):
        addr = (source, PORT)
        if addr != self.addr or not on:
            self.close()
        self.on = on
        self.addr = addr
        self.last_sub = None            # pede logo

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        self.last_packet = None

    def poll(self, now):
        """Pede e lê os pacotes (sem esperar). True se chegou um pacote novo."""
        if not self.on:
            return False
        if self.sock is None:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)
        if self.last_sub is None or time.ticks_diff(now, self.last_sub) >= SUBSCRIBE_MS:
            self.last_sub = now
            try:
                self.sock.sendto(SUBSCRIBE, self.addr)
            except OSError:
                pass                    # sem Wi-Fi ainda: tenta de novo em 2 s
        new = False
        while True:
            try:
                packet = self.sock.recv(512)
            except OSError:
                break                   # nada na fila
            if len(packet) >= 4 and packet[:3] == b"NP\x01":
                try:
                    self.feed(packet, now)
                except UnicodeError:
                    continue            # fora do contrato (só ASCII): ignora o pacote
                new = True
        return new

    def feed(self, packet, now):
        flags = packet[3]
        parts = str(packet[4:], "ascii").split("\x1f")
        data = {}
        for i, name in enumerate(FIELDS):
            v = parts[i] if i < len(parts) else ""
            if not v:
                v = None
            elif name in NUMBERS:
                try:
                    v = int(v)
                except ValueError:
                    v = None
            data[name] = v
        old = self.data
        playing = bool(flags & FLAG_PLAYING)
        if playing and (data["title"], data["position"], data["artist"]) != \
                (old["title"], old["position"], old["artist"]):
            self.track_seq += 1
            self.side_start = data["side_track"] == 1 or data["side"] != old["side"]
            self._take(data, now)
        elif not self.playing or not playing or self._drift(data, now) > RESYNC_S:
            self._take(data, now)
        else:
            # A mesma faixa, e a conta do Pico está certa: fica com ela (não pula à toa).
            keep = old["elapsed"], old["side_left"]
            self.data = data
            data["elapsed"], data["side_left"] = keep
        self.playing = playing
        self.side_end = bool(flags & FLAG_SIDE_END)
        self.last_packet = now
        self.packets += 1

    def _take(self, data, now):
        self.data = data
        self._base = now

    def _drift(self, data, now):
        """A maior diferença entre a conta do Pico e o pacote (posição e tempo do lado)."""
        drift = 0
        for mine, theirs in ((self.elapsed(now), data["elapsed"]), (self.side_left(now), data["side_left"])):
            if (mine is None) != (theirs is None):
                return RESYNC_S + 1     # a fonte passou a saber (ou deixou de saber): fica com ela
            if mine is not None:
                drift = max(drift, abs(mine - theirs))
        return drift

    def fresh(self, now):
        return self.on and self.last_packet is not None and time.ticks_diff(now, self.last_packet) < STALE_MS

    def _passed(self, now):
        return time.ticks_diff(now, self._base) // 1000 if self.playing else 0

    def elapsed(self, now):
        """Segundos tocados da faixa, contados pelo Pico desde o último acerto."""
        e, d = self.data["elapsed"], self.data["duration"]
        if e is None:
            return None
        e += self._passed(now)
        return min(e, d) if d is not None else e

    def side_left(self, now):
        left = self.data["side_left"]
        return None if left is None else max(0, left - self._passed(now))

    def status(self, now):
        age = None if self.last_packet is None else time.ticks_diff(now, self.last_packet)
        return {"on": self.on, "packets": self.packets, "last_packet_ms": age, "playing": self.playing,
                "side_end": self.side_end, "artist": self.data["artist"], "title": self.data["title"]}
