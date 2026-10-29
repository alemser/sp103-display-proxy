#!/usr/bin/env python3
"""Simula no computador o firmware/proxy.py com as capturas .lac do amp.

1. Responder (busy.py): confere nas capturas a suposição do programa do PIO, de que o RW
   já está no valor certo na subida do E e não muda até a descida.
2. Proxy: roda o laço listen() do proxy.py com um sniffer, um relógio e um display de
   mentira, alimentado com as palavras das capturas, e confere que o display do amp
   mostra cada tela do controlador já com os nomes personalizados (names.rewrite).

    python3 tools/test_proxy.py
"""

import asyncio
import glob
import os
import struct
import sys
import time as real_time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import hd44780_decode as hd   # noqa: E402
from test_sniffer import SKIP, screens_from_words, words_from_lac   # noqa: E402

NAMES = {"inputs": {"TUNER": "Rega Planar 2", "TAPE/AUX": "Yamaha KX-393", "CD": "Yamaha CD-S300",
                    "DAB": "AirPlay/BT - DAC"},
         "boot": ["", ""], "about": ["Oceano Amplifier", "SP103"]}


# --- 1. a suposição do Responder ----------------------------------------------

def check_rw(path):
    freq, pre, _, by_number, by_name = hd.load_lac(path)
    sig = hd.pick_signals(by_number, by_name)
    if "RW" not in sig:
        return None
    e, rw = sig["E"], sig["RW"]
    reads = bad = 0
    rise_rw = None
    for i in range(1, len(e)):
        if e[i] and not e[i - 1]:
            rise_rw = rw[i]
        elif e[i - 1] and not e[i] and rise_rw is not None:
            if rw[i - 1]:
                reads += 1
            if rw[i - 1] != rise_rw:
                bad += 1
    return reads, bad


# --- 2. o proxy.py ------------------------------------------------------------

class Clock:
    us = 0


def fake_time():
    t = types.ModuleType("time")
    for k in dir(real_time):
        if not k.startswith("__"):
            setattr(t, k, getattr(real_time, k))
    t.ticks_us = lambda: Clock.us
    t.ticks_ms = lambda: Clock.us // 1000
    t.ticks_diff = lambda a, b: a - b
    t.ticks_add = lambda a, b: a + b
    t.sleep_us = t.sleep_ms = lambda n: None
    return t


class FakeLcd:
    """O display do amp, visto de fora: o que o proxy mandou mostrar."""
    def __init__(self, *a, **k):
        self.lines, self.cgram, self.on, self.resyncs = [" " * 16, " " * 16], bytearray(64), True, 0

    def reset(self):
        self.lines = [" " * 16, " " * 16]

    def resync(self):
        self.resyncs += 1

    def display(self, on):
        self.on = on

    def define_char(self, code, rows):
        self.cgram[8 * code:8 * code + 8] = bytes(rows)

    def write_line(self, row, text):
        assert len(text) == 16, text
        self.lines[row] = text


class FakeSniffer:
    words = []                          # (µs, palavra)

    def read(self):
        while self.words and self.words[0][0] <= Clock.us:
            yield self.words.pop(0)[1]


def load_proxy():
    stubs = {"time": fake_time(), "sniffer": types.SimpleNamespace(Sniffer=FakeSniffer),
             "busy": types.SimpleNamespace(Responder=lambda: None),
             "lcd1602": types.SimpleNamespace(Lcd1602=FakeLcd),
             "ota": types.SimpleNamespace(in_trial=lambda: False, handle=None),
             "web": types.SimpleNamespace(Publisher=None, wifi_task=None)}
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    run, asyncio.run = asyncio.run, lambda coro: coro.close()   # não roda o main()
    try:
        import names
        names.load = lambda: names.validate(NAMES)
        names.save = lambda cfg: None
        sys.modules.pop("proxy", None)
        import proxy
    finally:
        asyncio.run = run
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k)
            else:
                sys.modules[k] = v
    return proxy


@types.coroutine
def _tick(ms):
    yield ms


def run_capture(proxy, words):
    """Roda o listen() do proxy sobre as palavras; devolve as telas que o display mostrou."""
    import names
    proxy.asyncio = types.SimpleNamespace(sleep_ms=_tick)
    proxy.powers = []                   # o "power" a cada mudança do estado
    proxy.pub = types.SimpleNamespace(changed=lambda: proxy.powers.append(proxy.state.power))
    t0 = words[0][0] if words else 0
    FakeSniffer.words = [(int(t - t0) + 1000, w) for t, w in words]
    Clock.us = 0
    end = (FakeSniffer.words[-1][0] if FakeSniffer.words else 0) + 50_000
    shown, loop = [], proxy.listen()
    while Clock.us < end:
        ms = loop.send(None)
        Clock.us += ms * 1000
        cur = tuple(proxy.lcd.lines)
        if not shown or shown[-1] != cur:
            shown.append(cur)
    return shown[1:] if shown and shown[0] == (" " * 16,) * 2 else shown


class FakeRelay:
    """O socket UDP do vu.py: o relay entrega um quadro a cada 46 ms, de start a stop (ms)."""
    start, stop, music = 0, 0, True

    def __init__(self, *a):
        self.next = FakeRelay.start

    def setblocking(self, flag):
        pass

    def sendto(self, data, addr):
        pass

    def recv(self, n):
        now = Clock.us // 1000
        if self.next > now or self.next >= FakeRelay.stop:
            raise OSError(11)
        self.next += 46
        return struct.pack("<2sBBff", b"VU", 1, 3 if FakeRelay.music else 2, 0.1, 0.05)

    def close(self):
        pass


def run_vu(proxy, words, end_ms):
    """Roda o listen() com o VU ligado; devolve [(ms, "vu" ou a tela do amp)] a cada troca."""
    proxy.asyncio = types.SimpleNamespace(sleep_ms=_tick)
    proxy.pub = types.SimpleNamespace(changed=lambda: None)
    proxy.vu_meter.socket = types.SimpleNamespace(socket=FakeRelay, AF_INET=2, SOCK_DGRAM=2)
    proxy.vu.configure({"on": True, "floor": -40, "top": 0, "relay": "192.168.178.105"})
    t0 = words[0][0]
    FakeSniffer.words = [(int(t - t0) + 1_000_000, w) for t, w in words]   # a tela do amp em 1 s
    Clock.us = 0
    changes, loop = [], proxy.listen()
    while Clock.us < end_ms * 1000:
        ms = loop.send(None)
        Clock.us += ms * 1000
        lines = proxy.lcd.lines
        kind = "vu" if lines[0][0] == "L" and lines[1][0] == "R" and proxy.vu_mode else tuple(lines)
        if not changes or changes[-1][1] != kind:
            changes.append((Clock.us // 1000, kind))
    return changes


def check_vu(path):
    """VU no ar; a tela do amp chega em 1 s e fica 3 s; os quadros param em 6 s."""
    fails = 0
    proxy = load_proxy()
    FakeRelay.start, FakeRelay.stop, FakeRelay.music = 0, 6000, True
    changes = run_vu(proxy, words_from_lac(path), 8000)
    kinds = [k if k == "vu" else "amp" for _, k in changes if k != (" " * 16,) * 2]
    at = {"vu": [], "amp": []}
    for t, k in changes:
        if k != (" " * 16,) * 2:
            at[k if k == "vu" else "amp"].append(t)
    amp = next((k for _, k in changes if k not in ("vu", (" " * 16,) * 2)), None)

    def ok(cond, what):
        nonlocal fails
        fails += not cond
        print("%-5s %s" % ("ok" if cond else "FALHA", what))

    ok(kinds[:4] == ["vu", "amp", "vu", "amp"], "VU, tela do amp, VU, tela do amp: %s" % kinds)
    ok(amp == ("Volume -28.75 dB", "Rega Planar 2   "), "a tela do amp já com o nome: %r" % (amp,))
    if len(changes) >= 4:
        t_amp, t_vu, t_end = at["amp"][0], at["vu"][1], at["amp"][1]
        ok(1000 <= t_amp <= 1020, "a tela do amp entra quando o controlador desenha (%d ms)" % t_amp)
        ok(3000 <= t_vu - t_amp <= 3060, "e fica 3 s (%d ms)" % (t_vu - t_amp))
        ok(6900 <= t_end <= 7100, "sem quadros por 1 s, volta a tela do amp (%d ms)" % t_end)
    ok(bytes(proxy.lcd.cgram) == bytes(proxy.bus.lcd.cgram), "os desenhos do controlador voltam")

    proxy = load_proxy()
    FakeRelay.start, FakeRelay.stop, FakeRelay.music = 0, 6000, False
    changes = run_vu(proxy, words_from_lac(path), 3000)
    ok(all(k != "vu" for _, k in changes), "sem música, o VU não aparece")
    return fails


def main():
    paths = sorted(glob.glob(os.path.join(HERE, "..", "captures", "*.lac")))
    fails = 0
    print("1. Responder: RW igual na subida e na descida do E")
    for p in paths:
        r = check_rw(p)
        name = os.path.basename(p)
        if r is None:
            print("--    %-24s sem RW" % name)
            continue
        reads, bad = r
        ok = bad == 0 or name in SKIP
        fails += not ok
        print("%-5s %-24s %4d leituras, %d mudanças no meio do pulso%s"
              % ("ok" if ok else "FALHA", name, reads, bad, " (fios soltos)" if bad and ok else ""))

    print("\n2. Proxy: o display mostra cada tela do controlador, com os nomes")
    import names
    for p in paths:
        name = os.path.basename(p)
        if name in SKIP:
            continue
        proxy = load_proxy()
        words = words_from_lac(p)
        expected, _ = screens_from_words(words)
        want = []
        for l1, l2 in expected:
            s = tuple(names.rewrite(l1, l2, proxy.texts))
            if not want or want[-1] != s:
                want.append(s)
        if want and want[0] == (" " * 16,) * 2:
            want = want[1:]             # tela vazia: o display já começa assim
        got = run_capture(proxy, words)
        # O busy_high aqui vem do display de verdade das capturas (ocupado logo depois do
        # "Clear display"); só no amp, com o Responder, ele precisa ficar em 0.
        ok = got == want and (not got or bytes(proxy.lcd.cgram) == bytes(proxy.bus.lcd.cgram))
        # Nenhuma captura tem o standby: a tela em branco do ligar não pode virar "standby".
        ok = ok and "standby" not in proxy.powers
        fails += not ok
        last = " | ".join(got[-1]) if got else "(nada)"
        print("%-5s %-24s %3d telas, busy_high=%d, power=%s  ->  %s"
              % ("ok" if ok else "FALHA", name, len(got), proxy.busy_high, proxy.state.power, last))
        if not ok and got != want:
            for i, (g, w) in enumerate(zip(got + [None] * len(want), want + [None] * len(got))):
                if g != w:
                    print("      tela %d: mostrou %r, esperado %r" % (i, g, w))
                    break

    print("\n3. VU: alterna com a tela do amp (05-tuner.lac)")
    fails += check_vu(os.path.join(HERE, "..", "captures", "05-tuner.lac"))
    print("\ntudo certo" if not fails else "\n%d falha(s)" % fails)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
