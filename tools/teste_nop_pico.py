"""Teste 2 da escrita em paralelo: o LCD ignora o comando 0x00? (docs/opcoes-intercepcao.md)

    .venv/bin/mpremote run tools/teste_nop_pico.py     (amp LIGADO, fio do VSYS SOLTO, Pico no USB)

Quando o programa pedir, troque a entrada UMA vez (por exemplo, de TUNER para CD). O Pico
espera o comando do controlador "vá para a linha 2, coluna 1" (0xC0) e zera os 8 fios de
dados durante esse pulso: o LCD recebe 0x00, que não é nenhum comando.

- Se o LCD ignorar o 0x00, ele continua no endereço seguinte ao da última letra (a coluna
  17 da linha 1, escondida), e a primeira letra da linha 2 fica a da entrada anterior
  ("TD" em vez de "CD"). Girar o volume um passo conserta a tela.
- Se a tela mostrar outra coisa, o LCD fez algo com o 0x00: os truques C e D não servem.

Segurança: só os fios de dados (D0-D7) são puxados para 0, e só durante um pulso do E. Os
bits em 1 vêm dos pull-ups de 4,7 kOhm (~1 mA). Força de saída no mínimo (2 mA).
"""

import time
import rp2
from machine import Pin, mem32

import sniffer
from hd44780 import Bus, RS, RW, DATA_SHIFT, describe

TIMEOUT_S = 30
E_PIN, D0_PIN = 2, 5
TARGET = 1 | (0xC0 << DATA_SHIFT)       # E=1, RS=0, RW=0, dados 0xC0 (na subida do E)
_PADS_BANK0 = 0x40038000
_DRIVE_MASK = 0x3 << 4


@rp2.asm_pio(out_init=(rp2.PIO.IN_LOW,) * 8, in_shiftdir=rp2.PIO.SHIFT_LEFT)
def _null_once():
    # Atenção: no MicroPython, mov(pindirs, ...) vira mov(exec, ...) e o PIO executa o valor como
    # instrução (0 = "pule para o endereço 0"). A direção dos pinos só muda com out(pindirs, n).
    mov(pins, null)             # valor de saída 0 nos 8 fios; a direção continua "entrada"
    pull(block)                 # a palavra procurada (o Python dá a largada)
    mov(y, osr)
    label("find")
    wait(0, gpio, 2)
    wait(1, gpio, 2)            # E sobe: o controlador já pôs RS, RW e os dados
    mov(isr, null)
    in_(pins, 11)               # E, RS, RW, D0..D7 (in_base = GP2)
    mov(x, isr)
    jmp(x_not_y, "find")
    mov(osr, invert(null))
    out(pindirs, 8)             # PUXA D0..D7 para 0: o LCD vai ler 0x00
    label("hold")
    wait(1, gpio, 2)
    set(x, 31)
    label("high")
    jmp(pin, "high_ok")
    jmp("hold")                 # ruído na borda (ver sniffer.py): continua segurando
    label("high_ok")
    jmp(x_dec, "high") [13]     # E em 1 por ~3 µs: pulso de verdade
    wait(0, gpio, 2)            # o LCD lê na descida do E
    mov(osr, null)
    out(pindirs, 8)             # solta
    push(block)
    label("stop")
    jmp("stop")


def main():
    sn = sniffer.Sniffer()
    # Máquina 4 = PIO1 (o sniffer ocupa o PIO0). Os fios GP5..GP12 passam a ser do PIO1, mas o
    # sniffer continua lendo todos eles.
    sm = rp2.StateMachine(4, _null_once, freq=150_000_000, in_base=Pin(E_PIN),
                          out_base=Pin(D0_PIN), jmp_pin=Pin(E_PIN))
    for n in range(D0_PIN, D0_PIN + 8):
        pad = _PADS_BANK0 + 4 + 4 * n
        mem32[pad] = mem32[pad] & ~_DRIVE_MASK & ~1     # 2 mA, borda lenta
    words = []
    done = False
    try:
        sm.active(1)
        list(sn.read())
        sm.put(TARGET)
        print("Troque a entrada UMA vez agora (espero %d s)..." % TIMEOUT_S)
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < TIMEOUT_S * 1000:
            words.extend(sn.read())
            if not done and sm.rx_fifo():
                sm.get()
                done = True
                t_end = time.ticks_ms()
            if done and time.ticks_diff(time.ticks_ms(), t_end) > 100:
                break
            time.sleep_ms(1)
    finally:
        sm.active(0)
        for n in range(D0_PIN, D0_PIN + 8):
            Pin(n, Pin.IN, pull=None)                   # garante: dados voltam a ser só entrada
        sn.stop()

    if not done:
        print("Nada aconteceu: o controlador não redesenhou em %d s. O Pico não puxou nada." % TIMEOUT_S)
        return

    # O comando nulo é a marca do teste (o controlador nunca manda 0x00).
    hit = [i for i, w in enumerate(words)
           if not w & (RS | RW) and (w >> DATA_SHIFT) & 0xFF == 0x00]
    print("\nPalavras em volta do ponto do teste:")
    start = max(0, (hit[0] if hit else 0) - 4)
    for i in range(start, min(len(words), start + 9)):
        print("  %s %s" % (">>" if i in hit else "  ", describe(words[i])))
    if not hit:
        print("\nRESULTADO: o comando não virou 0x00 (os fios de dados não desceram?). Confira a ligação.")
        return
    after = next((words[i] for i in range(hit[0] + 1, len(words))
                  if words[i] & RS and not words[i] & RW), None)
    print("\nO Pico trocou o comando 0xC0 por 0x00. A letra seguinte do controlador foi %s."
          % (repr(chr((after >> DATA_SHIFT) & 0xFF)) if after else "?"))
    print("Olhe o display do amp: se a PRIMEIRA letra da linha 2 ficou a da entrada anterior")
    print("(e o resto certo), o LCD ignora o 0x00. Gire o volume um passo para consertar a tela.")


main()
