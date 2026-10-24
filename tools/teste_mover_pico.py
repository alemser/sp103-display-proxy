"""Teste 4 da escrita em paralelo: mover uma letra da linha 1 para a linha 2. (docs/opcoes-intercepcao.md)

    .venv/bin/mpremote run tools/teste_mover_pico.py    (amp LIGADO, fio do VSYS SOLTO, Pico no USB)

Quando o programa pedir, troque a entrada UMA vez. O Pico faz o 'o' de "Volume" aparecer na
primeira coluna da linha 2 ("oAB" em vez de "DAB"), e o "Volume" continua inteiro na linha 1
(a célula do 'o' não é reescrita, então fica com o 'o' de antes). O redesenho atrasado do
controlador (2 a 6 s depois) conserta a tela sozinho.

Passos, todos só PUXANDO fios para 0 (força mínima, 2 mA):
1. Na leitura do busy flag logo depois do 'V', puxa o RW e zera D1, D2 e D4. O controlador
   deixou o 'V' (0x56) nos fios e soltou o D7: o LCD recebe 0xD6 sem esses bits = 0xC0,
   "vá para a linha 2, coluna 1". (O controlador lê "ocupado" e pergunta de novo.)
2. No comando seguinte do controlador ("vá para a coluna 2", 0x81), zera os dados: o LCD
   recebe 0x00 e ignora (teste 2). O 'o' cai na linha 2, coluna 1.
3. No comando "vá para a linha 2, coluna 1" (0xC0), zera os dados de novo: a primeira letra
   do nome vai para uma coluna escondida, e o 'o' fica.
"""

import time
import rp2
from machine import Pin, mem32

import sniffer
from hd44780 import Bus, RS, RW, DATA_SHIFT, describe

TIMEOUT_S = 30
E_PIN, RW_PIN = 2, 4
_PADS_BANK0 = 0x40038000
_DRIVE_MASK = 0x3 << 4


def word(rs, data):
    """A palavra do barramento na subida do E (formato do hd44780.py), numa escrita."""
    return 1 | (RS if rs else 0) | (data << DATA_SHIFT)


def pins_mask(rw=False, data_bits=0):
    """Máscara dos fios puxados: bit 0 = RW (GP4), bits 1..8 = D0..D7 (GP5..GP12)."""
    return (1 if rw else 0) | (data_bits << 1)


NEXT_READ = 1 << 9              # puxar na próxima leitura (antes do E subir), e não já
STEPS = [
    (word(1, ord("V")), NEXT_READ | pins_mask(rw=True, data_bits=0x16)),   # 0xD6 -> 0xC0
    (word(0, 0x81), pins_mask(data_bits=0xFF)),                             # 0x81 -> 0x00
    (word(0, 0xC0), pins_mask(data_bits=0xFF)),                             # 0xC0 -> 0x00
]


@rp2.asm_pio(out_init=(rp2.PIO.IN_LOW,) * 9, in_shiftdir=rp2.PIO.SHIFT_LEFT,
             out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def _steps():
    # Cada passo vem da fila: (palavra que dispara, ação). A ação = máscara de 9 fios + o bit
    # NEXT_READ. Atenção: mov(pindirs, ...) não serve no MicroPython (vira mov(exec, ...)).
    wrap_target()
    pull(block)
    mov(y, osr)                 # palavra que dispara o passo
    label("find")
    wait(0, gpio, 2)
    wait(1, gpio, 2)            # E sobe: RS, RW e os dados já estão no lugar
    mov(isr, null)
    in_(pins, 11)
    mov(x, isr)
    jmp(x_not_y, "find")
    pull(block)
    out(x, 9)                   # x = máscara dos fios
    out(y, 1)                   # y = NEXT_READ
    jmp(not_y, "now")
    wait(0, gpio, 2)            # fim deste pulso
    wait(1, gpio, 4)            # RW sobe: começa a leitura do busy flag
    set(y, 31)
    label("delay")
    jmp(y_dec, "delay") [9]     # ~2 µs (passa o empurrão forte do 8051)
    jmp(pin, "late")            # o E já subiu: desiste (jmp_pin = E)
    label("now")
    mov(osr, x)
    out(pindirs, 9)             # PUXA os fios da máscara
    wait(1, gpio, 2)
    set(y, 31)
    label("hold")
    jmp(y_dec, "hold") [13]     # E em 1 por ~3 µs (ignora ruído na borda)
    wait(0, gpio, 2)            # o LCD lê na descida do E
    mov(osr, null)
    out(pindirs, 9)             # solta
    push(noblock)               # avisa: passo feito
    wrap()
    label("late")
    mov(isr, null)
    push(noblock)               # avisa: desistiu (0)
    label("stop")
    jmp("stop")


def main():
    sn = sniffer.Sniffer()
    sm = rp2.StateMachine(4, _steps, freq=150_000_000, in_base=Pin(E_PIN),
                          out_base=Pin(RW_PIN), jmp_pin=Pin(E_PIN))
    for n in range(RW_PIN, RW_PIN + 9):
        pad = _PADS_BANK0 + 4 + 4 * n
        mem32[pad] = mem32[pad] & ~_DRIVE_MASK & ~1     # 2 mA, borda lenta
    queue = [v for step in STEPS for v in step]
    words, done, late = [], 0, False
    try:
        sm.active(1)
        list(sn.read())
        print("Troque a entrada UMA vez agora (espero %d s)..." % TIMEOUT_S)
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < TIMEOUT_S * 1000:
            while queue and sm.tx_fifo() < 4:
                sm.put(queue.pop(0))                    # a fila do PIO só tem 4 lugares
            words.extend(sn.read())
            while sm.rx_fifo():
                if sm.get():
                    done += 1
                else:
                    late = True
            if late or done == len(STEPS):
                time.sleep_ms(50)
                words.extend(sn.read())
                break
            time.sleep_ms(1)
    finally:
        sm.active(0)
        for n in range(RW_PIN, RW_PIN + 9):
            Pin(n, Pin.IN, pull=None)                   # garante: tudo volta a ser só entrada
        sn.stop()

    print("\nPassos feitos: %d de %d%s" % (done, len(STEPS), " (o E subiu cedo: desistiu)" if late else ""))
    if not done:
        print("O controlador não redesenhou. O Pico não puxou nada.")
        return
    first = next((i for i, w in enumerate(words) if w & RS and not w & RW
                  and (w >> DATA_SHIFT) & 0xFF == ord("V")), 0)
    print("\nPalavras do começo do redesenho (>> = o Pico mexeu):")
    for i in range(max(0, first - 2), min(len(words), first + 12)):
        w = words[i]
        mine = not w & RS and not w & RW and (w >> DATA_SHIFT) & 0xFF in (0x00, 0xC0) and i > first
        print("  %s %s" % (">>" if mine else "  ", describe(w)))

    # O que o LCD deve mostrar: a linha 1 de antes (o 'o' não foi reescrito) + o efeito na linha 2.
    bus = Bus()
    for w in words[first - 2 if first >= 2 else 0:]:
        bus.feed(w)
    l1, l2 = bus.lcd.lines()
    print("\nPelo que o Pico viu, a linha 2 deve começar com %r (a linha 1 fica como estava)." % l2[:4])
    print("Olhe o display do amp e me conte. O redesenho atrasado conserta a tela em 2 a 6 s.")


main()
