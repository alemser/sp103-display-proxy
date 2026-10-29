"""Responde ao controlador do amp no lugar do display: "livre" (busy flag = 0) em toda leitura.

Com o display desligado do controlador (opção 3b, docs/proxy-ligacao.md), ninguém mais
responde às leituras. O controlador lê o busy flag antes de cada comando e de cada
caractere e, para isso, solta só o D7, que o resistor de 4,7 kΩ leva a 1 = "ocupado".
Sem resposta, ele pergunta de novo para sempre (docs/descobertas-protocolo.md).

Em cada leitura (RW = 1 na subida do E), o PIO puxa o D7 (GP12) para 0 até o E descer.

REGRA DE SEGURANÇA (a mesma do sniffer.py): o GP12 NUNCA vai a 1. O valor de saída fica
em 0 (set_init e exec abaixo) e só a direção muda. O D7 é do P0 do controlador, que só
sobe pelo pull-up: puxar para 0 é sempre seguro (~1 mA). Saída na força mínima (2 mA).

Criar DEPOIS do Sniffer: o Sniffer põe GP2..GP12 como entrada comum (Pin.IN) e isso
tiraria o GP12 do PIO.
"""

import rp2
from machine import Pin, mem32

E_PIN, RW_PIN, D7_PIN = 2, 4, 12
_PADS_BANK0 = 0x40038000
_DRIVE_MASK = 0x3 << 4


@rp2.asm_pio(set_init=rp2.PIO.IN_LOW)
def _answer():
    # jmp_pin = RW; set_base = D7. Na subida do E, RS e RW já estão no lugar (capturas).
    label("top")
    wait(1, gpio, E_PIN)        # E sobe
    jmp(pin, "read")            # RW = 1: é uma leitura
    wait(0, gpio, E_PIN)        # escrita: só espera o pulso acabar
    jmp("top")
    label("read")
    set(pindirs, 1)             # D7 em 0 = "livre"
    wait(0, gpio, E_PIN)        # E desce: o controlador já leu
    set(pindirs, 0)             # solta o D7 (o pull-up do amp o leva de volta a 1)


class Responder:
    def __init__(self, sm_id=4):
        # sm_id 4 = PIO1, máquina 0 (o sniffer usa o PIO0; o Wi-Fi, o PIO2).
        self.sm = rp2.StateMachine(sm_id, _answer, freq=150_000_000,
                                   set_base=Pin(D7_PIN), jmp_pin=Pin(RW_PIN))
        self.sm.exec("set(pins, 0)")
        self.sm.exec("set(pindirs, 0)")
        pad = _PADS_BANK0 + 4 + 4 * D7_PIN
        mem32[pad] = mem32[pad] & ~_DRIVE_MASK & ~1     # 2 mA, borda lenta
        self.sm.active(1)
