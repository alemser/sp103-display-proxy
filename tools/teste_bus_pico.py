"""Teste da página /bus na bancada, sem o amp: .venv/bin/mpremote run tools/teste_bus_pico.py

Roda o programa da escuta (o escuta.py que está no Pico) e, junto, um "amp de mentira" que
escreve uma tela de volume nos pinos GP2..GP12 a cada 2 s, seguindo a mesma regra do
teste_sniffer_pico.py: o Pico só PUXA para 0, e o nível 1 vem do pull-up interno.
Enquanto roda, abra http://sp103.local/bus, baixe o CSV e leia com tools/ler_bus.py.
Ctrl-C para parar.

Rode com o amp FORA DA TOMADA (ou com os fios do amp desligados do Pico).
"""

import time
import asyncio
from machine import Pin

import sniffer

pins = []


def level(pin, v):
    if v:
        pin.init(Pin.IN, pull=Pin.PULL_UP)      # solta: o pull-up leva a 1
    else:
        pin.init(Pin.OUT, value=0)              # puxa para 0


def pulse(rs, rw, value):
    E, RS, RW, D = pins[0], pins[1], pins[2], pins[3:]
    level(RS, rs)
    level(RW, rw)
    for i in range(8):
        level(D[i], (value >> i) & 1)
    time.sleep_us(50)
    level(E, 1)
    time.sleep_us(50)
    level(E, 0)
    time.sleep_us(50)


def write_line(addr, text):
    for col, c in enumerate(text):
        pulse(0, 1, 0x00)                       # leitura do busy flag, como o controlador faz
        pulse(0, 0, 0x80 | (addr + col))
        pulse(0, 1, 0x00)
        pulse(1, 0, ord(c))


async def fake_amp():
    await asyncio.sleep(5)                      # o escuta.py já ligou o sniffer
    for n in range(sniffer.BUS_BASE, sniffer.BUS_BASE + sniffer.BUS_PINS):
        pins.append(Pin(n, Pin.OUT, value=0))
    print("fake amp: power on")
    pulse(0, 0, 0x01)                           # Clear display, como o amp ao ligar
    volume = -30.0
    step = 1.25
    while True:
        write_line(0x00, "Volume %6.2f dB" % volume)
        write_line(0x40, "PHONO           ")
        volume += step
        if not -40 < volume < -20:
            step = -step
        await asyncio.sleep(2)


asyncio.create_task(fake_amp())                 # roda junto com o asyncio.run() do escuta.py
try:
    import escuta                               # noqa: F401  (o programa roda ao ser importado)
finally:
    for p in pins:
        p.init(Pin.IN, pull=None)
