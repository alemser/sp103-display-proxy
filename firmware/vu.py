"""VU meter no display do amp: barras dos canais L e R, com a marca de pico.

Os quadros vêm do sp103-vu-relay (relay/main.go), que repassa o VU do groove-detector
por UDP. O Pico pede a cada 2 s ("SUB1"); cada quadro tem 12 bytes:

    "VU" 0x01 flags  float32 L  float32 R      (RMS 0..1; flags: bit 0 = há música)

Linha 1 = L, linha 2 = R. A coluna 0 mostra a letra; as colunas 1..15 são a barra, com
5 colunas de pixels cada: 75 passos do piso até o topo (os dois configuráveis, names.py;
o REC OUT costuma chegar bem abaixo de 0 dBFS). As marcas da escala ficam a -30, -20, -10,
-6 e -3 dB do topo. Os 8
desenhos próprios (CGRAM) do modo VU estão em GLYPHS; ao sair, o proxy.py grava de volta
os do controlador.

A barra sobe na hora e cai a 26 dB/s. O pico fica parado 1,5 s e cai a 15 dB/s. Acima de
-1 dBFS (o clip de verdade, não o topo) a última célula acende inteira por 1 s.
"""

import math
import socket
import struct
import time

PORT = 7091
SUBSCRIBE = b"SUB1"
SUBSCRIBE_MS = 2000             # o relay esquece o pedido em 6 s
STALE_MS = 1000                 # sem quadro por 1 s: volta a tela do amp
FALL_DB_S = 26
PEAK_HOLD_MS = 1500
PEAK_FALL_DB_S = 15
CLIP_DB = -1
CLIP_MS = 1000
STEPS = 75                      # 15 células x 5 colunas de pixels
TICKS_DB = (-30, -20, -10, -6, -3)   # abaixo do topo
SILENT_DB = -100.0
FLAG_PROGRAMME = 1


def _rows(bits, rows):
    return bytes([bits if r in rows else 0 for r in range(8)])


_BAR = (1, 2, 3, 4, 5, 6)       # a barra deixa a linha de pixels de cima e a de baixo livres
GLYPHS = b"".join((
    _rows(0x10, _BAR),          # 0: 1 coluna
    _rows(0x18, _BAR),          # 1: 2 colunas
    _rows(0x1C, _BAR),          # 2: 3 colunas
    _rows(0x1E, _BAR),          # 3: 4 colunas
    _rows(0x1F, _BAR),          # 4: célula cheia
    _rows(0x04, range(8)),      # 5: marca de pico, mais alta que a barra
    _rows(0x04, (7,)),          # 6: marca da escala, no fundo da barra vazia
    _rows(0x1F, range(8)),      # 7: clip, na última célula
))
FULL, PEAK, TICK, CLIP = 4, 5, 6, 7


def db(rms):
    return 20 * math.log10(rms) if rms > 1e-5 else SILENT_DB


class Meter:
    """Um canal: nível com queda lenta, pico parado e clip."""

    def __init__(self):
        self.level = SILENT_DB
        self.peak = SILENT_DB
        self.hold_until = 0
        self.clip_until = 0
        self.clip = False

    def feed(self, value_db, dt_ms, now):
        if value_db >= self.level:
            self.level = value_db
        else:
            self.level = max(value_db, self.level - FALL_DB_S * dt_ms / 1000)
        if self.level >= self.peak:
            self.peak = self.level
            self.hold_until = time.ticks_add(now, PEAK_HOLD_MS)
        elif time.ticks_diff(now, self.hold_until) > 0:
            self.peak = max(self.level, self.peak - PEAK_FALL_DB_S * dt_ms / 1000)
        if value_db > CLIP_DB:
            self.clip_until = time.ticks_add(now, CLIP_MS)
        self.clip = time.ticks_diff(self.clip_until, now) > 0


class Vu:
    def __init__(self):
        self.on = False
        self.floor = -40
        self.top = 0
        self.addr = None
        self.sock = None
        self.last_sub = None
        self.last_frame = None
        self.programme = False
        self.frames = 0
        self.error = None               # o proxy.py desliga o VU se ele der erro
        self.L = Meter()
        self.R = Meter()
        self._ticks = ()

    def configure(self, cfg):
        """cfg = names.json "vu": {"on", "floor", "top", "relay"}."""
        self.on = cfg["on"]
        self.error = None
        self.floor = cfg["floor"]
        self.top = cfg["top"]
        self._ticks = tuple(c for c in (self._cell(self.top + d) for d in TICKS_DB
                                        if self.top + d > self.floor) if c >= 0)
        addr = (cfg["relay"], PORT)
        if addr != self.addr or not self.on:
            self.close()
        self.addr = addr
        self.last_sub = None            # pede logo

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        self.last_frame = None

    def _px(self, value_db):
        x = round((value_db - self.floor) * STEPS / (self.top - self.floor))
        return 0 if x < 0 else STEPS if x > STEPS else x

    def _cell(self, value_db):
        return (self._px(value_db) - 1) // 5

    def poll(self, now):
        """Pede e lê os quadros (sem esperar). True se chegou um quadro novo."""
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
                data = self.sock.recv(32)
            except OSError:
                break                   # nada na fila
            if len(data) != 12 or data[:3] != b"VU\x01":
                continue
            _, _, flags, left, right = struct.unpack("<2sBBff", data)
            dt = 46 if self.last_frame is None else \
                min(200, max(10, time.ticks_diff(now, self.last_frame)))
            self.L.feed(db(left), dt, now)
            self.R.feed(db(right), dt, now)
            self.programme = bool(flags & FLAG_PROGRAMME)
            self.last_frame = now
            self.frames += 1
            new = True
        return new

    def active(self, now):
        """Ligado, com quadros chegando e música tocando."""
        return self.on and self.programme and self.last_frame is not None \
            and time.ticks_diff(now, self.last_frame) < STALE_MS

    def _row(self, label, m):
        lv, pk = self._px(m.level), self._px(m.peak)
        peak_cell = (pk - 1) // 5 if pk > lv else -1
        out = [label]
        for c in range(15):
            filled = lv - 5 * c
            if c == 14 and m.clip:
                out.append(chr(CLIP))
            elif filled >= 5:
                out.append(chr(FULL))
            elif filled > 0:
                out.append(chr(filled - 1))
            elif c == peak_cell:
                out.append(chr(PEAK))
            elif c in self._ticks:
                out.append(chr(TICK))
            else:
                out.append(" ")
        return "".join(out)

    def lines(self):
        return self._row("L", self.L), self._row("R", self.R)

    def status(self, now):
        age = None if self.last_frame is None else time.ticks_diff(now, self.last_frame)
        return {"on": self.on, "frames": self.frames, "last_frame_ms": age,
                "music": self.programme, "showing": self.active(now), "error": self.error}
