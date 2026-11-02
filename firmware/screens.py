"""Quem aparece no display, e o texto das telas de informação.

O proxy.py pergunta pick() quando a tela do amp não tem a vez (3 s depois de cada
redesenho do controlador). Em ordem:

1. Standby: o relógio, se ligado; senão, a tela do amp (apagada).
2. Fim do lado (se o aviso estiver ligado, e só nas entradas do toca-discos): no último
   minuto, "End of side A" e o tempo; depois que acaba, "Flip the record" piscando por
   FLIP_MS, e então a tela do amp. Um fim de lado que já veio no primeiro pacote (o Pico
   acabou de ligar) não conta: o aviso é para quando o disco acaba.
3. Modo fixo: a tela escolhida, o tempo todo enquanto toca. O VU não entra.
4. Modo temporário: a cada faixa nova, as telas marcadas em sequência, "secs" cada uma
   (a da agulha só no começo de um lado). Depois o VU, se ligado; senão, a tela do amp.
   A tela da agulha só aparece nas entradas do toca-discos ("turntable": PHONO, TUNER...).
5. Sem música ou sem dados: o VU (que só aparece com música) ou a tela do amp.

Bluetooth na entrada do streaming (amp_state.STREAMING_INPUT): a tela "quality" (codec,
sample rate, bits, bitrate) entra por "secs" quando o Bluetooth começa ou a qualidade muda,
se estiver marcada; no modo fixo, o tempo todo. Ela vem antes do passo 2 (o aviso de fim do
lado é só das entradas do toca-discos). O nome do streaming na tela do amp ("AirPlay",
"Bluetooth") é o stream_label(), que o proxy.py passa ao names.rewrite().

Os textos são em inglês, como os do amp. As barras usam os desenhos do VU (vu.GLYPHS); o
desenho 7 (o clip do VU, que as telas não usam) vira o símbolo do Bluetooth.
"""

import time

import vu as vu_meter
from amp_state import STREAMING_INPUT

KINDS = ("track", "pos", "side", "stylus", "quality")
TRACK_KINDS = KINDS[:4]         # as que entram em sequência a cada faixa nova
ALERT_S = 60                    # o aviso de fim do lado começa no último minuto
FLIP_MS = 60000                 # escolhido: "Flip the record" fica 1 min; o disco parado não pede mais
BLINK_MS = (1000, 500)          # "Flip the record": aceso, apagado
SCROLL_PAUSE_MS = 2000          # nome longo: parado 2 s, depois anda
SCROLL_STEP_MS = 350            # uma letra a cada 0,35 s
STYLUS_WARN = 90                # % de desgaste: "Replace stylus"
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MIN_YEAR = 2025                 # antes disso, o relógio do Pico ainda não foi acertado
BT = 7                          # o código do símbolo do Bluetooth (ᛒ) nos desenhos próprios
BT_GLYPH = bytes((0x04, 0x06, 0x15, 0x0E, 0x0E, 0x15, 0x06, 0x04))
GLYPHS = vu_meter.GLYPHS[:8 * BT] + BT_GLYPH
STREAM_NAMES = {"airplay": "AirPlay", "bluetooth": chr(BT) + " Bluetooth"}


def mmss(s):
    return "%d:%02d" % (s // 60, s % 60)


def lr(left, right):
    """Texto à esquerda e à direita numa linha de 16."""
    gap = 16 - len(left) - len(right)
    return (left + " " * max(1, gap) + right)[:16]


def center(text):
    left = (16 - len(text)) // 2
    return (" " * left + text + " " * 16)[:16]


def roll(text, width, ms):
    """Nome maior que a largura: parado SCROLL_PAUSE_MS, depois anda em volta."""
    if len(text) <= width:
        return text
    loop = text + "   "
    period = SCROLL_PAUSE_MS + len(loop) * SCROLL_STEP_MS
    k = ms % period
    off = 0 if k < SCROLL_PAUSE_MS else (k - SCROLL_PAUSE_MS) // SCROLL_STEP_MS
    return (loop + loop)[off:off + width]


def khz(rate):
    """44100 -> "44.1kHz", 48000 -> "48kHz"."""
    if rate % 1000 == 0:
        return "%dkHz" % (rate // 1000)
    return "%d.%dkHz" % (rate // 1000, rate % 1000 // 100)


def with_bt_glyph(cgram):
    """Os desenhos do controlador com o símbolo do Bluetooth no 7 (para a tela do amp)."""
    return bytes(cgram[:8 * BT]) + BT_GLYPH


def bar(fraction, cells):
    """Barra com os desenhos do VU: 5 colunas de pixels por célula."""
    n = int(max(0, min(1, fraction)) * cells * 5 + 0.5)
    out = []
    for c in range(cells):
        filled = n - 5 * c
        out.append(chr(vu_meter.FULL) if filled >= 5 else chr(filled - 1) if filled > 0 else " ")
    return "".join(out)


def _last_sunday(year, month):
    """Dia do último domingo de um mês de 31 dias (março e outubro)."""
    # Dias desde 1970-01-01 (uma quinta) até o dia 31: o algoritmo "days from civil".
    y = year - (month <= 2)
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + 30
    days = era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468
    weekday = (days + 3) % 7               # 0 = segunda
    return 31 - (weekday + 1) % 7


def eu_summer(t):
    """Horário de verão europeu: do último domingo de março ao de outubro, à 1h UTC."""
    y, m, d, h = t[0], t[1], t[2], t[3]
    if 3 < m < 10:
        return True
    if m == 3:
        ls = _last_sunday(y, 3)
        return d > ls or (d == ls and h >= 1)
    if m == 10:
        ls = _last_sunday(y, 10)
        return d < ls or (d == ls and h < 1)
    return False


class Screens:
    def __init__(self, info):
        self.info = info
        self.cfg = {"on": False, "mode": "temp", "fixed": "track", "show": list(KINDS), "secs": 8,
                    "alert": True, "clock": True, "scroll": True, "utc_offset": 0, "eu_dst": True}
        self.seq = []
        self.seq_at = 0
        self.seen_track = 0
        self.seen_stream = 0
        self.quality_at = None          # quando a tela "quality" entrou (modo temporário)
        self.key = None
        self.since = 0
        self.input = None               # a entrada do amp agora ("TUNER"), do amp_state
        self.error = None

    def configure(self, cfg):
        """cfg = names.json "info" (names.py)."""
        self.cfg = cfg
        self.seq = []
        self.seen_track = self.info.track_seq
        self.seen_stream = self.info.stream_seq
        self.quality_at = None
        self.error = None

    def vu_allowed(self):
        """No modo fixo o VU não entra: o Pico nem pede os quadros."""
        return not (self.cfg["on"] and self.cfg["mode"] == "fixed")

    def _has(self, kind, now):
        d = self.info.data
        if kind == "track":
            return d["title"] is not None
        if kind == "pos":
            return d["title"] is not None and (d["position"] is not None or d["duration"] is not None)
        if kind == "side":
            return d["side"] is not None and self.info.side_left(now) is not None
        if kind == "stylus":
            return d["stylus_hours"] is not None and self.input in self.cfg["turntable"]
        if kind == "quality":
            return d["stream"] == "bluetooth" and self.input == STREAMING_INPUT \
                and (d["codec"] is not None or d["sample_rate"] is not None)
        return False

    def stream_label(self, now):
        """O nome do streaming tocando ("AirPlay", "ᛒ Bluetooth"), para a linha da entrada
        na tela do amp, ou None. Vale com ou sem as telas ligadas."""
        if not self.info.fresh(now):
            return None
        return STREAM_NAMES.get(self.info.data["stream"])

    def _clock_time(self):
        t = time.time()
        if time.gmtime(t)[0] < MIN_YEAR:
            return None
        t += int(self.cfg["utc_offset"] * 3600)
        if self.cfg["eu_dst"] and eu_summer(time.gmtime(time.time())):
            t += 3600
        return time.gmtime(t)

    def pick(self, now, standby, vu_active, amp_input=None):
        """A tela de agora: "vu", uma das telas de informação, ou None (a tela do amp)."""
        self.input = amp_input
        key = self._pick(now, standby, vu_active)
        if key != self.key:
            self.key, self.since = key, now
        return key

    def _pick(self, now, standby, vu_active):
        cfg, info = self.cfg, self.info
        if standby:
            return "clock" if cfg["on"] and cfg["clock"] and self._clock_time() else None
        if not cfg["on"] or not info.fresh(now):
            return "vu" if vu_active else None
        quality = self._has("quality", now)
        if info.stream_seq != self.seen_stream:
            self.seen_stream = info.stream_seq
            self.quality_at = now if quality and "quality" in cfg["show"] else None
        if quality and cfg["mode"] == "fixed" and cfg["fixed"] == "quality":
            return "quality"
        if quality and cfg["mode"] == "temp" and self.quality_at is not None:
            if time.ticks_diff(now, self.quality_at) < cfg["secs"] * 1000:
                return "quality"
            self.quality_at = None
        if info.track_seq != self.seen_track:
            self.seen_track = info.track_seq
            self.seq = [k for k in TRACK_KINDS if k in cfg["show"] and (k != "stylus" or info.side_start)]
            self.seq_at = now
        if cfg["alert"] and info.data["side"] is not None and self.input in cfg["turntable"]:
            left = info.side_left(now)
            if info.side_end:
                if info.side_end_at is not None and time.ticks_diff(now, info.side_end_at) < FLIP_MS:
                    return "alert"
            elif info.playing and left is not None and left < ALERT_S:
                return "alert"
        if not info.playing:
            return "vu" if vu_active else None
        if cfg["mode"] == "fixed":
            kind = cfg["fixed"]
            return kind if self._has(kind, now) else "track" if self._has("track", now) else None
        secs = cfg["secs"] * 1000
        while self.seq and (time.ticks_diff(now, self.seq_at) >= secs or not self._has(self.seq[0], now)):
            if self._has(self.seq[0], now):
                self.seq_at = time.ticks_add(self.seq_at, secs)
            self.seq.pop(0)
        if self.seq:
            return self.seq[0]
        return "vu" if vu_active else None

    def lines(self, key, now):
        """As duas linhas (16 caracteres cada) de uma tela de informação."""
        d, info = self.info.data, self.info
        ms = time.ticks_diff(now, self.since) if self.cfg["scroll"] else 0
        title = d["title"] or ""
        if key == "track":
            # Só a música rola: o artista fica cortado, para não haver duas linhas andando.
            l1, l2 = (d["artist"] or "")[:16], roll(title, 16, ms)
        elif key == "pos":
            pos = d["position"]
            l1 = (pos + " " + roll(title, 15 - len(pos), ms)) if pos else roll(title, 16, ms)
            el, dur = info.elapsed(now), d["duration"]
            l2 = lr(mmss(el) + "/" + mmss(dur), "-" + mmss(dur - el)) if el is not None and dur else ""
        elif key == "side":
            l1 = lr("Side " + d["side"], "track %d/%d" % (d["side_track"], d["side_tracks"])
                    if d["side_track"] and d["side_tracks"] else "")
            l2 = lr("Left", mmss(info.side_left(now)))
        elif key == "alert":
            l1 = "End of side " + (d["side"] or "")
            if info.side_end:
                blink = time.ticks_diff(now, self.since) % sum(BLINK_MS)
                l2 = "Flip the record" if blink < BLINK_MS[0] else ""
            else:
                left = info.side_left(now)
                l2 = lr("Left", mmss(left)) if left is not None else ""
        elif key == "stylus":
            wear = d["stylus_wear"]
            l1 = "Replace stylus" if wear is not None and wear >= STYLUS_WARN \
                else lr("Stylus", "%d h" % d["stylus_hours"])
            l2 = (bar(wear / 100, 12) + "%4s" % ("%d%%" % wear)) if wear is not None else ""   # sem rjust no MicroPython
        elif key == "quality":
            l1 = lr(STREAM_NAMES["bluetooth"], d["codec"] or "")
            fmt = [khz(d["sample_rate"])] if d["sample_rate"] else []
            if d["bit_depth"]:
                fmt.append("%db" % d["bit_depth"])
            l2 = lr(" ".join(fmt), "%dk" % d["bitrate"] if d["bitrate"] else "")
        elif key == "clock":
            t = self._clock_time()
            if t is None:
                return " " * 16, " " * 16
            l1 = center("%02d:%02d" % (t[3], t[4]))
            l2 = center("%s %d %s" % (DAYS[t[6]], t[2], MONTHS[t[1] - 1]))
        else:
            l1 = l2 = ""
        return (l1 + " " * 16)[:16], (l2 + " " * 16)[:16]

    def status(self, now):
        return {"on": self.cfg["on"], "mode": self.cfg["mode"], "showing": self.key, "error": self.error}
