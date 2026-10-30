"""VU meter no display do amp: os canais L e R, com a marca de pico, em quatro layouts.

Os quadros vêm do sp103-vu-relay (relay/main.go), que repassa o VU do groove-detector
por UDP. O Pico pede a cada 2 s ("SUB1"); cada quadro tem 12 bytes:

    "VU" 0x01 flags  float32 L  float32 R      (RMS 0..1; flags: bit 0 = há música)

Layouts (names.py "layout"); cada um tem os seus 8 desenhos próprios (CGRAM), em
Vu.glyphs, e ao sair o proxy.py grava de volta os do controlador:

- "bars", barras finas: linha 1 = L, linha 2 = R. A coluna 0 mostra a letra; as colunas
  1..15 são a barra, com 5 colunas de pixels cada: 75 passos do piso até o topo. As marcas
  da escala ficam a -30, -20, -10, -6 e -3 dB do topo.
- "deck", deck de cassete: como "bars", mas com dois segmentos separados por célula (30
  passos); os das 3 últimas células são mais altos, no lugar da zona vermelha. O pico é
  um segmento aceso sozinho; o clip acende a última célula.
- "scale", escala impressa: L e R dividem a linha 1 (L na metade de cima de cada célula,
  R na de baixo; 2 segmentos por célula, 32 passos). A linha 2 é a régua, em dB abaixo
  do topo. O pico é um segmento aceso sozinho; no clip, o "0" da régua vira um bloco cheio
  (o caractere 255 da ROM, fora dos 8 desenhos).
- "kx393", o medidor do Yamaha KX-393: L e R dividem a linha 1, sem letras, um segmento
  por célula (16 passos) na escala do deck, que não é linear: -30 a +8 dB, de 2 em 2 perto
  do 0. O 0 do deck fica KX_ZERO dB abaixo do topo, e os segmentos acima dele são mais
  altos, no lugar do vermelho. A linha 2 é a régua do deck. O pico é um segmento aceso
  sozinho; o clip acende o último.

Escala (names.py): o REC OUT chega em níveis bem diferentes conforme a fonte (medido em
2026-10-29 no Pi 5: DAB perto de -30 dBFS, o vinil perto de -11). Na escala automática,
o topo fica AUTO_HEADROOM dB acima do quadro mais alto: sobe na hora e, com música, desce
AUTO_FALL_DB_S; o piso fica AUTO_SPAN dB abaixo do topo. Na manual, piso e topo são fixos.

A barra sobe na hora e a cheia esvazia em FALL_S. O pico fica parado 1 s e cai a escala
inteira em PEAK_FALL_S. Acima de -1 dBFS (o clip de verdade, não o topo) o clip acende
por 1 s.
"""

import math
import socket
import struct
import time

PORT = 7091
SUBSCRIBE = b"SUB1"
SUBSCRIBE_MS = 2000             # o relay esquece o pedido em 6 s
STALE_MS = 1000                 # sem quadro por 1 s: volta a tela do amp
FALL_S = 0.5                    # a barra cheia esvazia em 0,5 s (proporcional à escala)
PEAK_HOLD_MS = 1000
PEAK_FALL_S = 1.0
# A música varia pouco de um quadro para outro (vinil em 2026-10-29: 90 % dos quadros numa
# faixa de 7 dB). Com 20 dB, como um VU de ponteiro, e 5 dB de folga, a barra fica entre
# metade e 3/4 e se mexe; com 30 dB e 3 dB ela ficava parada perto do fim.
AUTO_SPAN = 20                  # escala automática: do piso ao topo
AUTO_HEADROOM = 5               # o topo fica 5 dB acima do quadro mais alto
AUTO_FALL_DB_S = 1              # e desce 1 dB/s com música (de -3 a -27 em 24 s)
AUTO_TOP = (-40, 0)             # limites do topo automático
CLIP_DB = -1
CLIP_MS = 1000
STEPS = 75                      # 15 células x 5 colunas de pixels
TICKS_DB = (-30, -20, -10, -6, -3)   # abaixo do topo
SILENT_DB = -100.0
FLAG_PROGRAMME = 1
LAYOUTS = ("bars", "deck", "scale", "kx393")


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

DECK_GLYPHS = b"".join((
    _rows(0x18, _BAR),          # 0: segmento da esquerda
    _rows(0x1B, _BAR),          # 1: os dois segmentos
    _rows(0x03, _BAR),          # 2: o da direita (pico sozinho)
    _rows(0x18, range(8)),      # 3..5: os mesmos na zona quente, mais altos
    _rows(0x1B, range(8)),
    _rows(0x03, range(8)),
    _rows(0x04, (7,)),          # 6: marca da escala
    bytes(8),                   # 7: sem uso
))
DECK_HOT, DECK_TICK = 12, 6     # da célula 12 em diante: zona quente

# Escala impressa: estado de cada canal numa célula = 0 apagado, 1 só o segmento da
# esquerda, 2 os dois. O desenho do par (l, r) é o código 3 * l + r - 1.
_HALF = (0, 0x18, 0x1B)
SCALE_GLYPHS = b"".join(
    bytes([_HALF[l] if y < 3 else _HALF[r] if 4 <= y < 7 else 0 for y in range(8)])
    for l in range(3) for r in range(3) if l or r)
# Na ordem de prioridade: uma marca que não cabe sem encostar noutra fica de fora.
SCALE_MARKS = ((0, "0"), (-20, "20"), (-10, "10"), (-30, "30"), (-6, "6"), (-3, "3"))
BLOCK = chr(255)                # bloco cheio da ROM do HD44780

# KX-393: os degraus da escala do deck, em dB a partir do 0 dele (um por célula).
KX_DB = (-30, -25, -20, -17, -14, -12, -10, -8, -6, -4, -2, 0, 2, 4, 6, 8)
KX_ZERO = -10                   # o 0 do deck, abaixo do topo: os trechos mais altos chegam ao +4
KX_RULER = "30 17 10 4 0 4 8"   # cada número começa embaixo do seu segmento


def _kx(left, right, hot):
    """Um segmento do KX-393: L nas linhas de cima, R nas de baixo; o quente é mais alto."""
    rows_l, rows_r = ((0, 1, 2), (5, 6, 7)) if hot else ((1, 2), (5, 6))
    return bytes([0x1E if (left and y in rows_l) or (right and y in rows_r) else 0 for y in range(8)])


# Código = 3 se quente + 0 só L, 1 só R, 2 os dois; 6 e 7 sem uso.
KX_GLYPHS = b"".join(_kx(l, r, hot) for hot in (0, 1) for l, r in ((1, 0), (0, 1), (1, 1))) + bytes(16)


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

    def feed(self, value_db, dt_ms, now, span):
        if value_db >= self.level:
            self.level = value_db
        else:
            self.level = max(value_db, self.level - span / FALL_S * dt_ms / 1000)
        if self.level >= self.peak:
            self.peak = self.level
            self.hold_until = time.ticks_add(now, PEAK_HOLD_MS)
        elif time.ticks_diff(now, self.hold_until) > 0:
            self.peak = max(self.level, self.peak - span / PEAK_FALL_S * dt_ms / 1000)
        if value_db > CLIP_DB:
            self.clip_until = time.ticks_add(now, CLIP_MS)
        self.clip = time.ticks_diff(self.clip_until, now) > 0


class Vu:
    def __init__(self):
        self.on = False
        self.auto = True
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
        self.layout = "bars"
        self.glyphs = GLYPHS
        self._ticks = ()
        self._ruler = " " * 16

    def configure(self, cfg):
        """cfg = names.json "vu": {"on", "auto", "floor", "top", "layout", "relay"}."""
        self.on = cfg["on"]
        self.layout = cfg["layout"]
        self.glyphs = {"bars": GLYPHS, "deck": DECK_GLYPHS, "scale": SCALE_GLYPHS,
                       "kx393": KX_GLYPHS}[self.layout]
        self.error = None
        self.auto = cfg["auto"]
        if self.auto:
            # O topo começa embaixo: o primeiro quadro com música já o leva ao lugar.
            self.top = AUTO_TOP[0]
            self.floor = self.top - AUTO_SPAN
        else:
            self.floor = cfg["floor"]
            self.top = cfg["top"]
        # As marcas e a régua ficam a distâncias fixas do topo: na escala automática, que
        # só se desloca, as células delas não mudam.
        per_cell = 2 if self.layout == "deck" else 5
        steps = 15 * per_cell
        self._ticks = tuple(c for c in ((self._px(self.top + d, steps) - 1) // per_cell
                                        for d in TICKS_DB if self.top + d > self.floor) if c >= 0)
        span = self.top - self.floor
        ruler = [" "] * 18              # com uma casa vazia de cada lado
        for d, text in SCALE_MARKS:
            if d < -span:
                continue
            col = 1 + min(16 - len(text), int((d + span) * 15 / span + 0.5))
            if all(c == " " for c in ruler[col - 1:col + len(text) + 1]):
                ruler[col:col + len(text)] = list(text)   # o MicroPython só aceita lista aqui
        self._ruler = "".join(ruler[1:17])
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

    def _px(self, value_db, steps=STEPS):
        x = round((value_db - self.floor) * steps / (self.top - self.floor))
        return 0 if x < 0 else steps if x > steps else x

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
            self.programme = bool(flags & FLAG_PROGRAMME)
            l_db, r_db = db(left), db(right)
            if self.auto and self.programme:
                self._follow(max(l_db, r_db), dt)
            span = self.top - self.floor
            self.L.feed(l_db, dt, now, span)
            self.R.feed(r_db, dt, now, span)
            self.last_frame = now
            self.frames += 1
            new = True
        return new

    def _follow(self, value_db, dt_ms):
        """Escala automática: o topo sobe na hora até o quadro + folga e desce devagar."""
        want = value_db + AUTO_HEADROOM
        top = want if want > self.top else max(want, self.top - AUTO_FALL_DB_S * dt_ms / 1000)
        self.top = min(AUTO_TOP[1], max(AUTO_TOP[0], top))
        self.floor = self.top - AUTO_SPAN

    def active(self, now):
        """Ligado, com quadros chegando e música tocando."""
        return self.on and self.programme and self.last_frame is not None \
            and time.ticks_diff(now, self.last_frame) < STALE_MS

    def _bars(self, label, m):
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

    def _deck(self, label, m):
        lv, pk = self._px(m.level, 30), self._px(m.peak, 30)
        if pk <= lv:
            pk = 0
        out = [label]
        for c in range(15):
            a = lv >= 2 * c + 1 or pk == 2 * c + 1 or (c == 14 and m.clip)
            b = lv >= 2 * c + 2 or pk == 2 * c + 2 or (c == 14 and m.clip)
            hot = 3 if c >= DECK_HOT else 0
            if a or b:
                out.append(chr(hot + (1 if a and b else 0 if a else 2)))
            else:
                out.append(chr(DECK_TICK) if c in self._ticks else " ")
        return "".join(out)

    @staticmethod
    def _half(lv, pk, c):
        """Estado de um canal na célula c da escala impressa (0, 1 ou 2)."""
        s = lv - 2 * c
        s = 0 if s < 0 else 2 if s > 2 else s
        if s or pk <= lv or (pk - 1) // 2 != c:
            return s
        return 1 if pk % 2 else 2       # o pico sozinho: só o da direita não tem desenho

    def _scale(self):
        l, r = self._px(self.L.level, 32), self._px(self.R.level, 32)
        pl, pr = self._px(self.L.peak, 32), self._px(self.R.peak, 32)
        out = []
        for c in range(16):
            a, b = self._half(l, pl, c), self._half(r, pr, c)
            out.append(chr(3 * a + b - 1) if a or b else " ")
        ruler = self._ruler
        if self.L.clip or self.R.clip:
            ruler = ruler[:15] + BLOCK
        return "".join(out), ruler

    def _kx_lit(self, m):
        """Os segmentos acesos de um canal no KX-393: a barra, o pico sozinho e o clip."""
        zero = self.top + KX_ZERO
        lv = sum(1 for d in KX_DB if m.level >= zero + d)
        pk = sum(1 for d in KX_DB if m.peak >= zero + d)
        last = len(KX_DB) - 1
        return [i < lv or (pk > lv and i == pk - 1) or (i == last and m.clip) for i in range(last + 1)]

    def _kx393(self):
        l, r = self._kx_lit(self.L), self._kx_lit(self.R)
        out = []
        for i, d in enumerate(KX_DB):
            if l[i] or r[i]:
                out.append(chr((3 if d > 0 else 0) + (2 if l[i] and r[i] else 1 if r[i] else 0)))
            else:
                out.append(" ")
        return "".join(out), KX_RULER

    def lines(self):
        if self.layout == "scale":
            return self._scale()
        if self.layout == "kx393":
            return self._kx393()
        row = self._deck if self.layout == "deck" else self._bars
        return row("L", self.L), row("R", self.R)

    def status(self, now):
        age = None if self.last_frame is None else time.ticks_diff(now, self.last_frame)
        return {"on": self.on, "auto": self.auto, "layout": self.layout, "floor": round(self.floor), "top": round(self.top),
                "frames": self.frames, "last_frame_ms": age,
                "music": self.programme, "showing": self.active(now), "error": self.error}
