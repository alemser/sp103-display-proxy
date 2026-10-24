"""Diagnóstico (só escuta): o que o Pico lê na SUBIDA do E, comparado com a DESCIDA?

    .venv/bin/mpremote run tools/diag_subida_pico.py     (amp LIGADO; gire o volume um passo)

Usado para entender por que o teste_nop_pico.py não reconheceu o comando 0xC0. Dois
sniffers ao mesmo tempo: o normal (PIO0, lê na descida do E, com filtro de ruído) e um
segundo (PIO1, lê na subida do E, sem filtro). Mostra os comandos de endereço de cada um.
Nenhum fio é puxado.
"""

import time
import rp2

import sniffer
from hd44780 import RS, RW, DATA_SHIFT, describe

WAIT_S = 20


@rp2.asm_pio(in_shiftdir=rp2.PIO.SHIFT_LEFT)
def _rise():
    wait(0, pin, 0)
    wait(1, pin, 0)             # E sobe: lê na hora
    in_(pins, 11)
    push(noblock)


def commands(words):
    return [w for w in words if not w & (RS | RW)]


fall = sniffer.Sniffer(sm_id=0)
normal = sniffer._sniff
sniffer._sniff = _rise          # o mesmo Sniffer (DMA + buffer circular), com o programa da subida
rise = sniffer.Sniffer(sm_id=4)
sniffer._sniff = normal
a, b = [], []
try:
    print("Gire o volume UM passo agora (espero %d s)..." % WAIT_S)
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < WAIT_S * 1000:
        a.extend(fall.read())
        b.extend(rise.read())
        time.sleep_ms(1)
finally:
    fall.stop()
    rise.stop()

print("\nPalavras: descida %d, subida %d (o normal é a subida ter igual ou mais, por causa do ruído)"
      % (len(a), len(b)))
ca, cb = commands(a), commands(b)
print("Comandos na descida (%d):" % len(ca), " ".join("%02X" % ((w >> DATA_SHIFT) & 0xFF) for w in ca[:34]))
print("Comandos na subida  (%d):" % len(cb), " ".join("%02X" % ((w >> DATA_SHIFT) & 0xFF) for w in cb[:34]))
print("\nPrimeiras 12 palavras na subida:")
for w in b[:12]:
    print("  E=%d RS=%d RW=%d  %s" % (w & 1, (w & RS) > 0, (w & RW) > 0, describe(w)))
