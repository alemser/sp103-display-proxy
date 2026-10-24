#!/usr/bin/env python3
"""Lê o CSV baixado de http://sp103.local/bus e remonta as telas do amp, com o horário.

    python3 tools/ler_bus.py ~/Downloads/sp103-bus-2026-10-24-2115.csv
    python3 tools/ler_bus.py arquivo.csv --palavras      # também cada palavra, uma por linha

Usa o mesmo hd44780.Bus do Pico (firmware/hd44780.py), então mostra o que o Pico viu.
O começo do arquivo costuma cair no meio de uma tela (o registro guarda só as últimas
palavras); a primeira tela completa vem logo depois.
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

from amp_state import lcd_text   # noqa: E402
from hd44780 import Bus, DATA_SHIFT, RS, RW   # noqa: E402

QUIET_MS = 5        # o Pico lê em lotes de ~1 ms; telas seguidas ficam bem mais longe que isso


def words(path):
    """(horário, ms, palavra) de cada linha do CSV."""
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            word = int(row["byte"], 16) << DATA_SHIFT
            word |= (RS if row["rs"] == "1" else 0) | (RW if row["rw"] == "1" else 0) | 1
            yield row["time"], int(row["ms"]), word


def screens(rows):
    """(horário, linha 1, linha 2) de cada tela completa."""
    bus, last, out = Bus(), None, []
    for when, ms, word in rows:
        if bus.pending and last is not None and ms - last[1] > QUIET_MS:
            out.append((last[0] or "%d ms" % last[1],) + bus.take())
        bus.feed(word)
        last = (when, ms)
    if bus.pending:
        out.append((last[0] or "%d ms" % last[1],) + bus.take())
    return out, bus


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("csv")
    ap.add_argument("--palavras", action="store_true", help="mostra também cada palavra")
    args = ap.parse_args()

    if args.palavras:
        with open(args.csv, newline="") as f:
            for row in csv.DictReader(f):
                print("%-23s %10s  %s" % (row["time"], row["ms"], row["meaning"]))
        print()

    got, bus = screens(words(args.csv))
    for when, l1, l2 in got:
        print("%-23s  %s | %s" % (when, lcd_text(l1), lcd_text(l2)))
    print("\n%d telas, %d escritas, %d leituras do busy flag, %d 'clear display' (amp ligando)" % (
        len(got), bus.writes, bus.reads, bus.clears))


if __name__ == "__main__":
    main()
