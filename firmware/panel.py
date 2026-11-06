"""Aperta o botão Function da frente do amp, por dentro.

Ligação (docs/proxy-ligacao.md):

    GP0 = perna 6 do controlador     GP1 = perna 13 do controlador

O controlador pulsa a perna 6 e lê a perna 13: com o botão apertado, a perna 13 cai junto com a 6
(captura de 2026-11-06). O PIO imita isso: dentro de cada pulso longo do GP0, puxa o GP1 para 0.

REGRA DE SEGURANÇA: o GP0 nunca é saída. O GP1 nunca vai a 1: o valor de saída fica em 0 e só a
direção muda, a 2 mA. A perna 13 sobe por um resistor de 4,7 kΩ, então puxar custa cerca de 1 mA.

Em cerca de 1 clique a cada 8, o amp também escolhe a entrada PHONO. O control.py corrige isso.
"""

import time

import rp2
from machine import Pin, mem32

PIN_SCAN, PIN_READ = 0, 1
PRESS_MS = 60
_PADS_BANK0 = 0x40038000
_DRIVE_MASK = 0x3 << 4


@rp2.asm_pio(set_init=rp2.PIO.IN_LOW)
def _mirror():
    # A 10 MHz. Os pulsos da perna 6 duram 25 a 30 µs, com alguns de 5 a 10 µs. Só os longos contam, e
    # a perna 13 sobe antes do fim do pulso.
    wait(0, gpio, 0)            # perna 6 em 0
    set(x, 31)
    label("settle")
    jmp(x_dec, "settle") [3]    # 12,8 µs
    jmp(pin, "done")            # já subiu: pulso curto
    set(pindirs, 1)             # perna 13 em 0
    set(x, 24)
    label("hold")
    jmp(x_dec, "hold") [3]      # 10 µs
    set(pindirs, 0)
    label("done")
    wait(1, gpio, 0)


class Panel:
    def __init__(self, sm_id=6):
        # sm_id 6 = PIO1, máquina 2 (0 é do busy.py e 1 é do ir.py).
        Pin(PIN_SCAN, Pin.IN, pull=None)
        Pin(PIN_READ, Pin.IN, pull=None)
        self.sm = rp2.StateMachine(sm_id, _mirror, freq=10_000_000, set_base=Pin(PIN_READ),
                                   jmp_pin=Pin(PIN_SCAN))
        self.sm.exec("set(pins, 0)")
        self.sm.exec("set(pindirs, 0)")
        pad = _PADS_BANK0 + 4 + 4 * PIN_READ
        mem32[pad] = mem32[pad] & ~_DRIVE_MASK & ~1     # 2 mA, borda lenta

    def press(self):
        self.sm.active(1)
        time.sleep_ms(PRESS_MS)
        self.sm.active(0)
        self.sm.exec("set(pindirs, 0)")
