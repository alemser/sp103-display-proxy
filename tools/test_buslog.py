#!/usr/bin/env python3
"""Testa no computador o registro do barramento (firmware/buslog.py) e o tools/ler_bus.py.

Passa as palavras das capturas .lac pelo BusLog, como o escuta.py faz no Pico (em lotes
de 1 ms), gera o CSV, lê de volta com o ler_bus.py e confere que as telas saem iguais
às do sniffer (tools/test_sniffer.py). Também confere a volta do buffer e o horário.

    python3 tools/test_buslog.py
"""

import glob
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import ler_bus   # noqa: E402
from buslog import BusLog   # noqa: E402
from hd44780 import Bus   # noqa: E402
from test_sniffer import SKIP, screens_from_words, words_from_lac   # noqa: E402

bad = 0


def check(ok, what):
    global bad
    bad += not ok
    print("%s %s" % ("ok   " if ok else "FALHA", what))


def run(words, size=1 << 20, clock=None):
    """Põe as palavras no BusLog em lotes de 1 ms e devolve (log, texto do CSV)."""
    log = BusLog(Bus(), size)
    log.clear(0)
    if clock:
        log.set_clock(*clock)
    batch, batch_ms = 0, None
    for t, word in words:
        ms = int(t // 1000) + 10_000            # o relógio interno não começa no zero
        if ms != batch_ms and batch_ms is not None:
            log.poll(batch_ms, batch)
            batch = 0
        log.bus.feed(word)
        log.add(ms, word)
        batch, batch_ms = batch + 1, ms
    return log, "".join(log.csv(tz_min=120))


def from_csv(text):
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write(text)
    try:
        return ler_bus.screens(ler_bus.words(f.name))
    finally:
        os.unlink(f.name)


def main():
    paths = sorted(glob.glob(os.path.join(HERE, "..", "captures", "*.lac")))
    for path in paths:
        name = os.path.basename(path)
        if name in SKIP:
            continue
        words = words_from_lac(path)
        want, _ = screens_from_words(words)
        log, text = run(words)
        got, bus = from_csv(text)
        st = log.stats(log.ticks[(log.n - 1) % log.size])
        check([s[1:] for s in got] == want and len(text.splitlines()) == len(words) + 1
              and st["writes"] == bus.writes and st["reads"] == bus.reads,
              "%-22s %3d telas, %5d palavras, CSV ida e volta" % (name, len(got), len(words)))

    # Volta do buffer: só as últimas palavras, da mais antiga para a mais nova.
    words = [(i * 1000.0, (i % 256) << 3) for i in range(1000)]
    log, text = run(words, size=64)
    lines = text.splitlines()[1:]
    check(len(lines) == 64 and lines[0].split(",")[4] == "%02X" % (936 % 256)
          and lines[-1].split(",")[4] == "%02X" % (999 % 256), "volta do buffer (64 de 1000)")
    st = log.stats(log.ticks[63])
    check(st["log_words"] == 64 and st["words"] == 1000 and st["log_span_s"] == 0,
          "estatísticas do buffer")

    # Palavras novas durante o download sobrescrevem as que ainda não saíram: são puladas,
    # e o arquivo continua em ordem, até a última palavra do início do download.
    log, _ = run(words[:150], size=100)
    parts = log.csv(chunk=20)
    text = next(parts) + next(parts)
    for t, word in words[150:230]:
        log.add(int(t // 1000) + 10_000, word)
    text += "".join(parts)
    ms = [int(line.split(",")[1]) for line in text.splitlines()[1:]]
    check(ms == sorted(ms) and ms[19] == 10_069 and ms[20] == 10_130 and ms[-1] == 10_149,
          "buffer sobrescrito durante o download")

    # Horário: relógio acertado em 2026-10-24 19:00:00 UTC quando o ticks_ms valia 10 000;
    # o CSV pede o fuso +120 min, então a primeira palavra (ms 10 000) sai 21:00:00.000.
    log, text = run(words[:3], clock=(1792868400, 10_000))
    first = text.splitlines()[1].split(",")
    check(first[0] == "2026-10-24 21:00:00.000" and first[1] == "10000", "horário no CSV: %s" % first[0])
    log, text = run(words[:3])
    check(text.splitlines()[1].startswith(",10000,"), "sem relógio: coluna de horário vazia")

    print("\n%s" % ("tudo certo" if not bad else "%d falha(s)" % bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
