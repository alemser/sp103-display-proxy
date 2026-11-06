#!/usr/bin/env python3
"""Testa no computador os ajustes diretos (firmware/control.py), com um amp de mentira.

    python3 tools/test_control.py
"""

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

asyncio.sleep_ms = lambda ms: asyncio.sleep(0)   # sem espera de verdade nos testes

import control   # noqa: E402

ORDER = ("normal", "bass", "treble", "balance", "loudness", "speakers")


class FakeAmp:
    """Faz o papel do estado, do IR e do painel. glitch: cliques em que o amp também vai a PHONO."""

    def __init__(self, glitch=()):
        self.power, self.screen, self.input_id = "on", "normal", "cd"
        self.volume_db, self.bass_db, self.treble_db, self.balance = -40.0, 2, 0, 0
        self.loudness, self.speakers = False, True
        self.opened = False
        self.glitch = set(glitch)
        self.presses = 0
        self.keys = []

    def sending(self):
        return False

    def press(self):
        self.presses += 1
        self.screen = ORDER[(ORDER.index(self.screen) + 1) % len(ORDER)]
        if self.presses in self.glitch:
            self.input_id = "phono"

    def send(self, key):
        self.keys.append(key)
        sign = 1 if key == "volume_up" else -1
        if key.startswith("select_"):
            self.input_id = key[7:]
        elif key in ("bass", "treble"):
            self.screen = key
        elif self.screen in ("bass", "treble"):
            setattr(self, self.screen + "_db", getattr(self, self.screen + "_db") + 2 * sign)
        elif self.screen == "balance":
            self.balance += sign
        elif self.screen in ("loudness", "speakers"):
            setattr(self, self.screen, sign > 0)
        elif self.opened:
            self.volume_db += 1.25 * sign
        else:
            self.opened = True          # o primeiro toque só abre a tela do volume


def run(amp, **query):
    asyncio.run(control.Control(amp, amp, amp).run(query))


amp = FakeAmp()
run(amp, target="volume", dir="up")
assert amp.volume_db == -38.75 and amp.keys == ["volume_up", "volume_up"]
run(amp, target="volume", dir="down")
assert amp.volume_db == -40 and len(amp.keys) == 3

amp = FakeAmp()
run(amp, target="bass", dir="up")
assert amp.bass_db == 4 and amp.keys == ["bass", "volume_up"] and amp.volume_db == -40
run(amp, target="bass", dir="down")
assert amp.bass_db == 2 and amp.keys == ["bass", "volume_up", "volume_down"]

amp = FakeAmp()
run(amp, target="balance", dir="down")
assert amp.balance == -1 and amp.presses == 3 and amp.screen == "balance"

amp = FakeAmp()
run(amp, target="loudness", on="1")
assert amp.loudness is True and amp.keys == ["volume_up"]
run(amp, target="loudness", on="1")
assert amp.keys == ["volume_up"]    # já estava ligado: nada a mudar
run(amp, target="speakers", on="0")
assert amp.speakers is False and amp.keys[-1] == "volume_down"

# O clique que vai a PHONO: volta à entrada anterior e segue até o menu.
amp = FakeAmp(glitch=[2])
run(amp, target="loudness", on="1")
assert amp.input_id == "cd" and amp.loudness is True and "select_cd" in amp.keys

for query in ({"target": "x", "dir": "up"}, {"target": "bass"}, {"target": "bass", "dir": "x"},
              {"target": "loudness", "on": "2"}):
    try:
        run(FakeAmp(), **query)
        raise AssertionError(query)
    except ValueError as e:
        assert str(e) == "Unknown control"

# Uma tecla vale também em standby, e só as conhecidas passam.
amp = FakeAmp()
amp.power = "standby"
run(amp, target="key", name="power_toggle")
assert amp.keys == ["power_toggle"]
try:
    run(amp, target="key", name="x")
    raise AssertionError("tecla desconhecida")
except ValueError as e:
    assert str(e) == "Unknown key"

amp = FakeAmp()
amp.power = "standby"
try:
    run(amp, target="volume", dir="up")
    raise AssertionError("standby")
except ValueError as e:
    assert str(e) == "The amp isn't on"
assert amp.keys == []
print("tudo certo")
