"""Teste do sniffer no próprio Pico, sem o amp: .venv/bin/mpremote run tools/teste_sniffer_pico.py

Simula o controlador escrevendo "Volume -28.75 dB" / "PHONO" nos pinos GP2..GP12,
seguindo a mesma regra das experiências: o Pico só PUXA para 0. O nível 1 vem do
pull-up interno (~50 kΩ). (O pull-down não serve: pela errata E9 do RP2350, ele não
consegue baixar um pino que já esteve em 1.)

Rode com o amp FORA DA TOMADA (ou com os fios do amp desligados do Pico): com o amp
ligado, o teste falha, porque o amp manda nos níveis.
"""

import time
from machine import Pin

import sniffer
from hd44780 import Bus

pins = [Pin(sniffer.BUS_BASE + i, Pin.OUT, value=0) for i in range(sniffer.BUS_PINS)]
E, RS, RW = pins[0], pins[1], pins[2]
D = pins[3:]


def level(pin, v):
    if v:
        pin.init(Pin.IN, pull=Pin.PULL_UP)      # solta: o pull-up leva a 1
    else:
        pin.init(Pin.OUT, value=0)              # puxa para 0


def pulse(rs, rw, value):
    level(RS, rs)
    level(RW, rw)
    for i in range(8):
        level(D[i], (value >> i) & 1)
    time.sleep_us(50)                   # pull-up de 50 kΩ: o nível 1 demora uns µs para assentar
    level(E, 1)
    time.sleep_us(50)
    level(E, 0)
    time.sleep_us(50)


def write_line(addr, text):
    for col, c in enumerate(text):
        pulse(0, 1, 0x00)               # leitura do busy flag, como o controlador faz
        pulse(0, 0, 0x80 | (addr + col))
        pulse(0, 1, 0x00)
        pulse(1, 0, ord(c))


sn = sniffer.Sniffer()
bus = Bus()
print("DMA ativo:", sn.dma.active(), " count=0x%08X" % sn.dma.count)

pulse(0, 0, 0x01)                       # Clear
write_line(0x00, "Volume -28.75 dB")
write_line(0x40, "PHONO           ")
time.sleep_ms(5)
n = 0
for w in sn.read():
    bus.feed(w)
    n += 1
print("palavras:", n, " escritas:", bus.writes, " leituras:", bus.reads, " clear:", bus.clears)
print("tela:", bus.take())
print("DMA ainda ativo depois de", n, "transferências:", sn.dma.active(), " count=0x%08X" % sn.dma.count)
ok = bus.lcd.lines() == ("Volume -28.75 dB", "PHONO           ") and n == 1 + 32 * 4

# Mais 80 linhas (5120 palavras): o buffer circular (4096) dá a volta sem perder nada.
total = 0
for k in range(80):
    write_line(0x40, ("TUNER", "CD")[k % 2] + " " * (16 - (5, 2)[k % 2]))
    for w in sn.read():
        bus.feed(w)
        total += 1
print("depois de 80 linhas: palavras", total, " tela:", bus.take())
ok = ok and total == 80 * 16 * 4 and bus.lcd.lines()[1] == "CD              "
print("RESULTADO:", "OK" if ok else "FALHOU")

for p in pins:
    p.init(Pin.IN, pull=None)
sn.stop()
