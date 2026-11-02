#!/usr/bin/env python3
"""Confere no computador o firmware/lcd1602.py: write_line(row, texto, old) manda só as
posições que mudaram e o display fica igual ao que mandaria a linha inteira.

Os pinos são de mentira: a cada descida do E, o meio byte (modo 4 bits) vai para a cópia
do HD44780 do hd44780.py, que guarda o que o display mostraria.

    python3 tools/test_lcd1602.py
"""

import os
import random
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

from hd44780 import Lcd   # noqa: E402


class Display:
    """O display do outro lado dos fios: junta os meios bytes e executa os bytes."""
    def __init__(self):
        self.lcd = Lcd()
        self.skip = 4                   # o resync manda 4 meios bytes sozinhos (0x3, 0x3, 0x3, 0x2)
        self.high = None
        self.bytes = 0
        self.pins = {}

    def falling_e(self):
        n = sum(self.pins.get(18 + i, 0) << i for i in range(4))
        if self.skip:
            self.skip -= 1
            return
        if self.high is None:
            self.high = n
            return
        b, self.high = (self.high << 4) | n, None
        self.bytes += 1
        if self.pins.get(16):
            self.lcd.data(b)
        else:
            self.lcd.command(b)


DISPLAY = Display()


class Pin:
    OUT = 1

    def __init__(self, n, mode=None, value=0):
        self.n = n
        DISPLAY.pins[n] = value

    def value(self, v):
        if self.n == 17 and DISPLAY.pins.get(17) and not v:
            DISPLAY.falling_e()
        DISPLAY.pins[self.n] = v


fake_time = types.ModuleType("time")
fake_time.sleep_us = fake_time.sleep_ms = lambda n: None
sys.modules["machine"] = types.SimpleNamespace(Pin=Pin)
sys.modules["time"] = fake_time
from lcd1602 import Lcd1602   # noqa: E402
del sys.modules["time"]

fails = 0


def check(ok, what):
    global fails
    fails += not ok
    print("%-5s %s" % ("ok" if ok else "FALHA", what))


def shown(row):
    return DISPLAY.lcd.lines()[row]


lcd = Lcd1602()
lcd.write_line(0, "Volume -28.75 dB")
lcd.write_line(1, "TUNER")
check(shown(0) == "Volume -28.75 dB" and shown(1) == "TUNER" + " " * 11, "linha inteira, sem old")

DISPLAY.bytes = 0
lcd.write_line(0, "Volume -30.00 dB", "Volume -28.75 dB")
check(shown(0) == "Volume -30.00 dB", "só o que mudou: o display fica certo")
check(DISPLAY.bytes == 6, "um endereço e 5 caracteres (-28.75 -> -30.00): %d bytes" % DISPLAY.bytes)

DISPLAY.bytes = 0
lcd.write_line(1, "TUNER", "TUNER" + " " * 11)
check(DISPLAY.bytes == 0, "nada mudou: nada vai para o display")

DISPLAY.bytes = 0
lcd.write_line(1, "TXNXR", "TUNER" + " " * 11)
check(shown(1) == "TXNXR" + " " * 11 and DISPLAY.bytes == 4,
      "um igual no meio é reescrito em vez de mudar o endereço: %d bytes" % DISPLAY.bytes)

random.seed(1)
old = [shown(0), shown(1)]
ok = True
for _ in range(500):
    row = random.randrange(2)
    new = "".join(random.choice("ab \x00\x04") if random.random() < 0.3 else c for c in old[row])
    lcd.write_line(row, new, old[row])
    old[row] = new
    ok = ok and shown(row) == new
check(ok, "500 linhas aleatórias: o display sempre igual ao texto")

print("\n%s" % ("tudo certo" if not fails else "%d falha(s)" % fails))
sys.exit(1 if fails else 0)
