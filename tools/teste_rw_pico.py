"""Teste 1 da escrita em paralelo: o RW é fraco no 1? (docs/opcoes-intercepcao.md)

    .venv/bin/mpremote run tools/teste_rw_pico.py      (amp LIGADO, fio do VSYS SOLTO, Pico no USB)

Quando o programa pedir, gire o volume um passo. O Pico espera o controlador escrever um
caractere e, na leitura do busy flag seguinte (a que vem antes do "Set DDRAM addr"), puxa
o RW para 0 UMA vez só. Se o RW for fraco no 1, o LCD recebe uma escrita em vez de uma
leitura: um "Set DDRAM addr" inofensivo, porque logo depois o controlador manda o endereço
dele. A escuta (sniffer) mostra o que aconteceu.

Resultado no amp (2026-10-24): o RW desceu (é fraco no 1). O byte injetado foi o último
caractere com o bit 7 ligado ('V' 0x56 -> 0xD6): antes de ler o busy flag, o controlador
solta só o D7; os outros fios ficam presos no último byte.

Segurança (sem resistores em série):
- O Pico só PUXA para 0: valor de saída fixo em 0, troca só a direção do pino.
- Força de saída do GP4 no mínimo (2 mA): se o RW for forte, o Pico "perde" e a corrente
  fica em poucos mA, por ~20 µs.
- Puxa só se o E ainda estiver em 0, dois µs depois de o RW subir (as capturas mostram
  ~21 µs entre o RW subir e o E subir), e solta assim que o E desce.
"""

import time
import rp2
from machine import Pin, mem32

import sniffer
from hd44780 import RS, RW, DATA_SHIFT, describe

BANCADA = False                 # True: sem o amp, com o "amp de mentira" (só para testar o programa)
TIMEOUT_S = 30
E_PIN, RS_PIN, RW_PIN = 2, 3, 4
_PADS_BANK0 = 0x40038000        # RP2350: registro do pad do GPIO n em +4 + 4*n
_DRIVE_MASK = 0x3 << 4          # DRIVE: 0 = 2 mA


@rp2.asm_pio(set_init=rp2.PIO.IN_LOW)
def _pull_rw_once():
    set(pins, 0)                # valor de saída 0; a direção continua "entrada"
    set(pindirs, 0)
    pull(block)                 # espera o Python dar a largada
    label("find")
    wait(1, gpio, 2)            # E sobe
    wait(0, gpio, 2)            # E desce
    mov(isr, null)
    in_(pins, 1)                # RS (in_base = GP3) no instante da descida
    mov(x, isr)
    jmp(not_x, "find")          # RS=0: comando ou leitura; procura uma escrita de caractere
    wait(1, gpio, 4)            # RW sobe: começa a leitura do busy flag
    set(y, 31)
    label("delay")
    jmp(y_dec, "delay") [9]     # ~2 µs
    jmp(pin, "late")            # o E já subiu (jmp_pin = E): desiste
    set(pindirs, 1)             # PUXA o RW para 0
    label("hold")
    wait(1, gpio, 2)            # E sobe...
    set(y, 31)
    label("high")
    jmp(pin, "high_ok")
    jmp("hold")                 # ...mas caiu logo: ruído (sniffer.py), continua segurando
    label("high_ok")
    jmp(y_dec, "high") [13]     # E em 1 por ~3 µs: pulso de verdade
    wait(0, gpio, 2)            # o LCD lê na descida do E
    set(pindirs, 0)             # solta
    set(x, 1)
    jmp("report")
    label("late")
    set(x, 0)
    label("report")
    mov(isr, x)
    push(block)
    label("stop")
    jmp("stop")


def fake_amp_screen(pad):
    """Só no modo BANCADA: escreve 3 caracteres como o teste_sniffer_pico.py (só puxando para 0).
    O RW fica com o pull-up interno (sempre 1), sem Pin.init: o pino continua com o PIO."""
    mem32[pad] = (mem32[pad] | 1 << 3) & ~(1 << 2)     # pull-up ligado, pull-down desligado
    pins = [Pin(sniffer.BUS_BASE + i) for i in range(sniffer.BUS_PINS)]

    def level(pin, v):
        if v:
            pin.init(Pin.IN, pull=Pin.PULL_UP)
        else:
            pin.init(Pin.OUT, value=0)

    def pulse(rs, value):
        level(pins[1], rs)
        for i in range(8):
            level(pins[3 + i], (value >> i) & 1)
        time.sleep_us(50)
        level(pins[0], 1)
        time.sleep_us(50)
        level(pins[0], 0)
        time.sleep_us(50)

    level(pins[0], 0)
    for col, c in enumerate("SP1"):
        pulse(0, 0xFF)          # leitura: barramento solto, dados em 1
        pulse(0, 0x80 | col)
        pulse(0, 0xFF)
        pulse(1, ord(c))
    for i, p in enumerate(pins):
        if i != 2:
            p.init(Pin.IN, pull=None)
    mem32[pad] &= ~(1 << 3)


def main():
    sn = sniffer.Sniffer()
    # Máquina 4 = PIO1: o sniffer (com o filtro) ocupa boa parte das 32 instruções do PIO0.
    sm = rp2.StateMachine(4, _pull_rw_once, freq=150_000_000, set_base=Pin(RW_PIN),
                          in_base=Pin(RS_PIN), jmp_pin=Pin(E_PIN))
    pad = _PADS_BANK0 + 4 + 4 * RW_PIN
    mem32[pad] = mem32[pad] & ~_DRIVE_MASK & ~1     # 2 mA, borda lenta
    words = []
    result = None
    try:
        sm.active(1)
        list(sn.read())                             # descarta o que veio antes
        sm.put(1)                                   # largada
        if BANCADA:
            fake_amp_screen(pad)
        else:
            print("Gire o volume UM passo agora (espero %d s)..." % TIMEOUT_S)
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < TIMEOUT_S * 1000:
            words.extend(sn.read())
            if result is None and sm.rx_fifo():
                result = sm.get()
                t_end = time.ticks_ms()
            if result is not None and time.ticks_diff(time.ticks_ms(), t_end) > 100:
                break
            time.sleep_ms(1)
    finally:
        sm.active(0)
        Pin(RW_PIN, Pin.IN, pull=None)              # garante: RW volta a ser só entrada
        sn.stop()

    if result is None:
        print("Nada aconteceu: nenhuma escrita de caractere em %d s. O Pico não puxou nada." % TIMEOUT_S)
        return
    if result == 0:
        print("O E subiu antes do esperado: o Pico desistiu e não puxou nada. Rode de novo.")
        return

    # O controlador sempre lê o busy flag logo depois de um caractere. Um comando (RW=0, RS=0)
    # logo depois de um caractere é a escrita que o Pico provocou.
    hit = [i for i in range(1, len(words))
           if words[i - 1] & RS and not words[i - 1] & RW and not words[i] & (RW | RS)]
    first_data = next((i for i, w in enumerate(words) if w & RS and not w & RW), 0)
    show_from = max(0, (hit[0] if hit else first_data) - 3)
    print("\nPalavras em volta do ponto do teste:")
    for i in range(show_from, min(len(words), show_from + 10)):
        print("  %s %s" % (">>" if i in hit else "  ", describe(words[i])))
    print()
    if hit:
        w = words[hit[0]]
        print("RESULTADO: o RW DESCEU. Ele é fraco no 1. Byte injetado: 0x%02X (o último byte,"
              " com o bit 7 em 1)." % ((w >> DATA_SHIFT) & 0xFF))
    else:
        print("RESULTADO: o RW NÃO desceu. Ele parece forte no 1: injetar comandos não é seguro.")
        print("(O Pico puxou com 2 mA por ~20 µs; isso não estraga nada.)")


main()
