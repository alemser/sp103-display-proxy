#!/usr/bin/env python3
"""Testa no computador o caminho do sniffer (firmware/hd44780.py) com as capturas .lac.

Monta as palavras que o PIO leria a cada descida do E, passa pelo Bus do firmware e
entrega cada tela completa ao leitor (amp_state), como o escuta.py faz no Pico.
Confere que as telas saem iguais às do decodificador das capturas (tools/test_amp_state.py).

    python3 tools/test_sniffer.py                     # todas as capturas em captures/
    python3 tools/test_sniffer.py captures/04-phono-b.lac
"""

import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import hd44780_decode as hd   # noqa: E402
from amp_state import AmpState   # noqa: E402
from hd44780 import Bus   # noqa: E402
from test_amp_state import QUIET_US, screens   # noqa: E402

# Capturas com fios soltos (ver docs/descobertas-protocolo.md): o RW falhou, então
# leituras viram escritas e a tela sai diferente. Não servem para comparar.
SKIP = {"13-function-1.lac", "13-function-todos.lac", "03-liga-telas.lac"}


def words_from_lac(path):
    """(tempo em µs, palavra) a cada descida do E, no formato do sniffer."""
    freq, pre, _, by_number, by_name = hd.load_lac(path)
    sig = hd.pick_signals(by_number, by_name)
    e, us = sig["E"], 1e6 / freq
    order = ["RS", "RW"] + ["D%d" % i for i in range(8)]
    out = []
    for i in range(1, len(e)):
        if e[i - 1] and not e[i]:
            word = 0
            for bit, name in enumerate(order, start=1):
                if name in sig and sig[name][i - 1]:
                    word |= 1 << bit
            out.append(((i - pre) * us, word))
    return out


def screens_from_words(words):
    bus = Bus()
    got, last_t = [], None
    for t, word in words:
        if bus.pending and last_t is not None and t - last_t > QUIET_US:
            got.append(bus.take())
        bus.feed(word)
        last_t = t
    if bus.pending:
        got.append(bus.take())
    return got, bus


def screens_reference(path):
    """As mesmas telas pelo decodificador das capturas (o caminho já testado)."""
    freq, pre, _, by_number, by_name = hd.load_lac(path)
    events, _, _, _ = hd.decode(hd.pick_signals(by_number, by_name), freq, pre)
    lcd, got, pending, last_t = hd.Lcd(), [], False, None
    for t, rs, rw, full, _ in events:
        if pending and last_t is not None and t - last_t > QUIET_US:
            got.append(tuple(screens(lcd)))
            pending = False
        last_t = t
        if rw:
            continue
        lcd.data(full) if rs else lcd.command(full)
        pending = True
    if pending:
        got.append(tuple(screens(lcd)))
    return got


def main():
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(HERE, "..", "captures", "*.lac")))
    bad = 0
    for path in paths:
        name = os.path.basename(path)
        if name in SKIP and len(sys.argv) == 1:
            continue
        got, bus = screens_from_words(words_from_lac(path))
        ok = got == screens_reference(path)
        bad += not ok
        st = AmpState()
        for l1, l2 in got:
            st.update(l1, l2, 0)
        d = st.to_dict()
        print("%s %-22s %3d telas, %4d escritas, %4d leituras, clear=%d  -> %s | %s" % (
            "ok   " if ok else "FALHA", name, len(got), bus.writes, bus.reads, bus.clears,
            d["lcd"][0], d["lcd"][1]))
    print("\n%s" % ("tudo igual ao decodificador" if not bad else "%d captura(s) diferente(s)" % bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
