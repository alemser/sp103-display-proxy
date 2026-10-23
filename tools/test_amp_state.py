#!/usr/bin/env python3
"""Testa o leitor de telas (firmware/amp_state.py).

Sem argumentos: confere telas escritas à mão (as das capturas, ver docs/descobertas-protocolo.md).
Com capturas: reproduz cada .lac, entrega cada tela completa ao leitor e mostra o estado quando muda.

    python3 tools/test_amp_state.py
    python3 tools/test_amp_state.py captures/04-phono-b.lac captures/15-balance.lac
    python3 tools/test_amp_state.py --sem-rw captures/13-function-todos.lac
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import hd44780_decode as hd   # noqa: E402
from amp_state import AmpState, BOX, parse   # noqa: E402

# Uma tela está completa quando o controlador fica este tempo sem escrever.
QUIET_US = 2000

B = BOX
CASES = [
    # (linha 1, linha 2, tela esperada, campos esperados)
    ("Volume -28.75 dB", "PHONO           ", "normal", {"volume_db": -28.75, "input": "PHONO"}),
    ("Volume -15.00 dB", "TAPE/AUX        ", "normal", {"volume_db": -15.0, "input": "TAPE/AUX"}),
    ("Volume -28.75 dB", B * 10 + " " * 6, "volume", {"volume_db": -28.75}),
    ("Volume -27.75 dB", "PHONO           ", "unknown", {}),          # não é passo de 1,25
    ("Volume -28.75 dB", "PHO             ", "unknown", {}),          # tela pela metade
    ("Bass   2 dB     ", "       <>" + B + "      ", "bass", {"bass_db": 2}),
    ("Bass -10 dB     ", "  " + B * 5 + "<>       ", "bass", {"bass_db": -10}),
    ("Bass -10 dB     ", "   " + B * 4 + "<>       ", "unknown", {}),  # barra não confere
    ("Treble   0 dB   ", "       <>       ", "treble", {"treble_db": 0}),
    ("Balance <level> ", "       <>       ", "balance", {"balance": {"side": None, "db": 0.0}}),
    ("Balance -5.00 dB", "       <>" + B + "      ", "balance", {"balance": {"side": "R", "db": -5.0}}),
    ("Balance-10.00 dB", "     " + B * 2 + "<>       ", "balance", {"balance": {"side": "L", "db": -10.0}}),
    ("Balance -1.25 dB", "       <>       ", "balance", {"balance": {"side": None, "db": -1.25}}),
    ("   Loudness     ", " < OFF >   ON   ", "loudness", {"loudness": False}),
    ("   Speakers     ", "   OFF   < ON > ", "speakers", {"speakers": True}),
    ("    ACOUSTIC    ", "    SOLUTIONS   ", "boot", {}),
    ("Amplifier SP103 ", " SW version 1.0 ", "about", {"firmware": "1.0"}),
    ("                ", "                ", "unknown", {}),
]


def self_test():
    bad = 0
    for l1, l2, screen, values in CASES:
        got = parse(l1, l2)
        ok = got == (screen, values)
        bad += not ok
        print(("ok   " if ok else "FALHA"), repr(l1), repr(l2), "->", got)
    print(f"\n{len(CASES) - bad} de {len(CASES)} ok")
    return bad == 0


def screens(lcd):
    """As duas linhas da memória do LCD, com os códigos originais (chr(0) = caixa)."""
    return ["".join(chr(lcd.ddram[base + (col + lcd.shift) % 40]) for col in range(16))
            for base in (0x00, 0x40)]


def replay(path, sem_rw):
    freq, pre, burst, by_number, by_name = hd.load_lac(path)
    sig = hd.pick_signals(by_number, by_name)
    events, _, _, _ = hd.decode(sig, freq, pre)
    if sem_rw:
        events = [(t, rs, 1 if (rs == 0 and full < 0x80) else 0, full, nib)
                  for t, rs, rw, full, nib in events]

    print(f"=== {path}")
    lcd = hd.Lcd()
    st = AmpState()
    pending = False

    def offer(t):
        l1, l2 = screens(lcd)
        if st.update(l1, l2, int(t / 1000)):
            d = st.to_dict()
            print(f"  {t / 1000:9.1f} ms  {d['lcd'][0]} | {d['lcd'][1]}  ->  "
                  + json.dumps({k: d[k] for k in ("screen", "volume_db", "input", "bass_db",
                                                    "treble_db", "balance", "loudness", "speakers",
                                                    "firmware") if d[k] is not None}))

    last_t = None
    for t, rs, rw, full, nib in events:
        if pending and last_t is not None and t - last_t > QUIET_US:
            offer(last_t)
            pending = False
        last_t = t
        if rw:
            continue                    # leitura do busy flag: não muda a tela
        if rs:
            lcd.data(full)
        else:
            lcd.command(full)
        pending = True
    if pending:
        offer(last_t)                   # fim da captura: a tela pode estar incompleta
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("capturas", nargs="*")
    ap.add_argument("--sem-rw", action="store_true", help="fio do RW falhou na captura (ver hd44780_decode.py)")
    args = ap.parse_args()
    if not args.capturas:
        sys.exit(0 if self_test() else 1)
    for path in args.capturas:
        replay(path, args.sem_rw)


if __name__ == "__main__":
    main()
