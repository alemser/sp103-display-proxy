"""Escuta o barramento do LCD do amp com o PIO, sem nunca mandar sinal para ele.

Ligação (a mesma das capturas, docs/ligacao-analisador.md):

    GP2 = E   GP3 = RS   GP4 = RW   GP5..GP12 = D0..D7   (+ GND no pino 1 do LCD)

REGRA DE SEGURANÇA: GP2..GP12 recebem 5 V do amp e não há resistores em série.
Eles NUNCA podem ser saída com valor 1: isso brigaria com o controlador.
Aqui todos ficam como entrada. As experiências futuras só podem PUXAR para 0
(valor de saída fixo em 0, trocando apenas a direção do pino).

Como funciona: a cada descida do E (é quando o LCD lê o byte), o PIO lê os 11 fios
e manda a palavra para a fila. Um canal de DMA copia a fila, sem parar, para um
buffer circular na memória. Assim nada se perde enquanto o Python está ocupado
com o Wi-Fi; read() devolve as palavras novas (formato em hd44780.py).
"""

import rp2
import uctypes
from array import array
from machine import Pin

BUS_BASE = 2                    # GP2: primeiro fio do barramento (E)
BUS_PINS = 11                   # E, RS, RW, D0..D7
RING_BITS = 14                  # buffer circular de 2^14 bytes = 4096 palavras (umas 30 telas)

# Endereços do RP2350 (datasheet, seções DMA e PIO).
_PIO_BASE = (0x50200000, 0x50300000, 0x50400000)
_RXF0 = 0x020                   # fila de saída (RX) da máquina 0; as outras seguem de 4 em 4
_DREQ_PIO_RX0 = (4, 12, 20)     # pedido de DMA "a fila RX tem dado"
_ENDLESS = 0xF0000001           # TRANS_COUNT com MODE = 0xF: o DMA não para nunca (a contagem não pode ser 0)


@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_LEFT)
def _sniff():
    # Filtro de ruído: com fios longos, a borda do E "treme" e parece um pulso a mais. Os pulsos
    # reais do amp duram 10 µs ou mais (capturas); o ruído, 1 µs ou menos. Só vale um pulso que
    # fique em 1 por ~3 µs, seguido de E em 0 por ~1,7 µs. (A 150 MHz; jmp_pin = E.)
    label("idle")
    wait(1, pin, 0)             # E sobe
    set(x, 31)
    label("high")
    jmp(pin, "high_ok")
    jmp("idle")                 # caiu cedo demais: era ruído
    label("high_ok")
    jmp(x_dec, "high") [13]     # 32 x 15 ciclos = 3,2 µs
    wait(0, pin, 0)             # E desce: o LCD leu o byte; RS, RW e dados ainda estão estáveis
    in_(pins, 11)
    push(noblock)               # fila cheia (não deve acontecer, o DMA esvazia): perde a palavra
    label("low_restart")
    wait(0, pin, 0)
    set(x, 31)
    label("low")
    jmp(pin, "low_restart")     # subiu de novo logo: ruído na descida, espera descer outra vez
    jmp(x_dec, "low") [6]       # 32 x 8 ciclos = 1,7 µs


class Sniffer:
    def __init__(self, sm_id=0):
        # sm_id 0 = PIO0, máquina 0. (O chip de Wi-Fi usa a máquina 8, no PIO2.)
        for n in range(BUS_BASE, BUS_BASE + BUS_PINS):
            Pin(n, Pin.IN, pull=None)   # só entrada, sem pull (o amp já define todos os níveis)

        size = 1 << RING_BITS
        # O DMA circular exige um buffer alinhado ao tamanho: reservamos o dobro e usamos
        # a parte alinhada.
        self._buf = array("I", bytes(2 * size))
        start = uctypes.addressof(self._buf)
        self._first = ((-start) % size) // 4
        self._base = start + self._first * 4
        self._mask = size // 4 - 1
        self._rd = 0

        self.sm = rp2.StateMachine(sm_id, _sniff, freq=150_000_000, in_base=Pin(BUS_BASE),
                                   jmp_pin=Pin(BUS_BASE))
        pio, sm = divmod(sm_id, 4)
        self.dma = rp2.DMA()
        ctrl = self.dma.pack_ctrl(size=2, inc_read=False, inc_write=True,
                                  ring_size=RING_BITS, ring_sel=True,
                                  treq_sel=_DREQ_PIO_RX0[pio] + sm)
        self.dma.config(read=_PIO_BASE[pio] + _RXF0 + 4 * sm, write=self._base,
                        count=_ENDLESS, ctrl=ctrl, trigger=True)
        self.sm.active(1)

    def read(self):
        """As palavras que chegaram desde a última chamada (gerador)."""
        wr = ((self.dma.write - self._base) >> 2) & self._mask
        buf, first, mask, rd = self._buf, self._first, self._mask, self._rd
        while rd != wr:
            yield buf[first + rd]
            rd = (rd + 1) & mask
        self._rd = rd

    def stop(self):
        self.sm.active(0)
        self.dma.active(0)
        self.dma.close()
