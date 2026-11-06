#!/usr/bin/env python3
"""Confere os bits de firmware/ir_codes.py contra o perfil do SP103 no groove-rig.

    python3 tools/test_ir.py
"""

import base64
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import ir_codes   # noqa: E402

PROFILE = os.path.expanduser("~/Projects/groove-rig/internal/catalog/profiles/acoustic_solutions_sp103.yaml")
TICK_US = 269 / 8.192           # unidade de tempo do Broadlink
LONG_US = 1000                  # acima disto, o espaço é um bit 1


def captured(body):
    """Os tempos em µs de um código do Broadlink, até o fim do primeiro aviso de repetição."""
    data = base64.b64decode(body)
    payload = data[4:4 + (data[2] | data[3] << 8)]
    times, i = [], 0
    while i < len(payload):
        value = payload[i]
        i += 1
        if value == 0:
            value = payload[i] << 8 | payload[i + 1]
            i += 2
        times.append(value * TICK_US)
    return times[:91]


with open(PROFILE) as f:
    codes = dict(re.findall(r"^  (\w+):\n\s+format: broadlink_ir\n\s+body: (\S+)", f.read(), re.M))

assert set(codes) == set(ir_codes.COMMANDS)
for name, body in codes.items():
    words = ir_codes.frame(name)
    # Pares de linha em 0 e solta: o PIO termina sempre esperando a próxima linha em 0.
    assert len(words) % 2 == 0
    want = captured(body)
    assert len(want) == len(words) - 1, name
    # Só os bits: os tempos do Broadlink são cerca de 5% mais longos que os do controle real.
    for i, (a, b) in enumerate(zip(words, want)):
        assert (a > LONG_US) == (b > LONG_US), (name, i, a, round(b))

print("tudo certo")
