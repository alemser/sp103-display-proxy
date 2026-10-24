"""Variante do teste_desenho_pico.py (SO_MOSTRAR = True): o desenho 6 já está gravado no LCD; só o mostra no lugar do V.

    .venv/bin/mpremote run tools/teste_desenho_pico.py   (amp em STANDBY, fio do VSYS SOLTO, Pico no USB)

Deixe o amp em standby, rode o programa e, quando ele pedir, ligue o amp.

1. Ao ligar, o controlador grava os 8 desenhos próprios (CGRAM, 64 bytes seguidos, sem leituras
   do busy flag), duas vezes com 64 ms de intervalo. O desenho 6 tem as linhas 2 a 7 cheias
   (0x1F). O Pico espera o comando "Set CGRAM" (0x40), conta 50 bytes (desenhos 0 a 5 e as
   linhas 0 e 1 do desenho 6, que já são vazias) e, nas linhas 2 a 7, apaga pontos (zera fios
   de dados): o desenho vira um 'r' minúsculo.
2. Por 20 s depois disso, em cada redesenho, o Pico zera bits do 'V' de "Volume" (0x56 -> 0x06):
   o LCD mostra o desenho 6 no lugar do 'V', e a linha 1 fica "rolume". Depois, o 'V' volta no
   redesenho seguinte; o desenho 6 continua 'r' até o amp desligar.

Ruído no E: a borda do E "treme" com os fios longos (sniffer.py). Uma segunda máquina do PIO
(_e_filter) só avisa (IRQ 4) quando o E fica em 1 por ~3 µs: é por esses avisos que o programa
conta os bytes. (Contando as subidas, a contagem adiantava 3 a 7 bytes.)

Só fios de dados são puxados para 0 (D0-D4 no desenho, D4 e D6 no 'V'), com força mínima (2 mA).
"""

import time
import rp2
from machine import Pin, mem32

import sniffer
from hd44780 import RS, RW, DATA_SHIFT

TIMEOUT_S = 60
SHOW_S = 20
SO_MOSTRAR = True              # True: pula a gravação (o desenho já está no LCD) e só mostra
E_PIN, RS_PIN, RW_PIN, D0_PIN = 2, 3, 4, 5
_PADS_BANK0 = 0x40038000
_DRIVE_MASK = 0x3 << 4

GLYPH = 6
ORIGINAL = [0x1F if row >= 8 - GLYPH else 0x00 for row in range(8)]    # linhas 2-7 cheias
R_SHAPE = [0x00, 0x00, 0x16, 0x19, 0x10, 0x10, 0x10, 0x00]             # 'r' da fonte do HD44780
MASKS = [o & ~t for o, t in zip(ORIGINAL, R_SHAPE)]                     # pontos a apagar
FIRST_ROW = 8 - GLYPH                                                   # linhas antes: já vazias
assert all(t & ~o == 0 for o, t in zip(ORIGINAL, R_SHAPE)), "o desenho não cabe nas linhas cheias"
assert not any(MASKS[:FIRST_ROW])


def pack(rows):
    v = 0
    for i, m in enumerate(rows):
        v |= m << (5 * i)
    return v


# Palavra lida a partir do GP3 (RS, RW, D0..D7): o comando "Set CGRAM 0x40".
CGRAM_CMD = 0x40 << 2
CARVE = [CGRAM_CMD, 8 * GLYPH + FIRST_ROW, pack(MASKS[FIRST_ROW:])]
V_WORD = 1 | RS | (ord("V") << DATA_SHIFT)     # na subida do E, a partir do GP2 (formato do hd44780.py)


@rp2.asm_pio()
def _e_filter():
    # Avisa (IRQ 4) uma vez por pulso de verdade do E: em 1 por ~3 µs, e depois em 0 por ~1,7 µs
    # antes de aceitar o próximo (a mesma regra do sniffer.py). Sem a 2ª parte, um E que "pisca"
    # para 0 no meio do pulso (ele é fraco em 1) contava duas vezes.
    wait(0, gpio, 2)
    wrap_target()
    label("rise")
    wait(1, gpio, 2)
    set(x, 31)
    label("high")
    jmp(x_dec, "high") [13]     # 32 x 15 ciclos = 3,2 µs
    jmp(pin, "real")            # ainda em 1 (jmp_pin = E)?
    jmp("rise")                 # era um tremido
    label("real")
    irq(4)
    label("low")
    wait(0, gpio, 2)
    set(x, 31)
    label("low_wait")
    jmp(x_dec, "low_wait") [6]  # 32 x 8 ciclos = 1,7 µs
    jmp(pin, "low")             # subiu de novo: ainda é o mesmo pulso
    wrap()


@rp2.asm_pio(out_init=(rp2.PIO.IN_LOW,) * 5, set_init=(rp2.PIO.IN_LOW,) * 5,
             in_shiftdir=rp2.PIO.SHIFT_LEFT, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def _carve():
    # Fila: o comando que dispara, quantos bytes pular, as máscaras (6 linhas x 5 bits).
    # Cada wait(1, irq, 4) espera um pulso de verdade do E (~3 µs depois da subida; o pulso
    # dura 10 µs ou mais, e o LCD só grava na descida).
    # Atenção: mov(pindirs, ...) não serve no MicroPython (vira mov(exec, ...)), e sem autopull
    # (com ele, pull() não faz nada se o OSR já estiver cheio, e a fila sai desalinhada).
    wrap_target()
    pull(block)
    mov(y, osr)
    label("find")
    wait(1, irq, 4)
    mov(isr, null)
    in_(pins, 10)               # RS, RW, D0..D7 (in_base = GP3)
    mov(x, isr)
    jmp(x_not_y, "find")        # espera o "Set CGRAM 0x40"
    pull(block)
    mov(y, osr)                 # bytes a pular
    label("skip")
    wait(1, irq, 4)
    jmp(y_dec, "skip")          # quando y chega a 0, este pulso é a 1ª linha a mudar
    pull(block)                 # as 6 máscaras
    set(y, 5)
    label("row")
    out(pindirs, 5)             # apaga os pontos desta linha
    wait(0, gpio, 2)            # o LCD grava na descida do E
    set(pindirs, 0)             # solta
    jmp(y_dec, "next")
    push(noblock)               # avisa: desenho feito
    wrap()
    label("next")
    wait(1, irq, 4)
    jmp("row")


@rp2.asm_pio(out_init=(rp2.PIO.IN_LOW,) * 8, in_shiftdir=rp2.PIO.SHIFT_LEFT,
             out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def _mask_v():
    # Em cada escrita do 'V', zera os bits da máscara (o Python põe uma máscara por vez).
    # out_shiftdir=SHIFT_RIGHT: out() pega os bits BAIXOS do OSR, onde está a máscara. O padrão
    # do MicroPython é SHIFT_LEFT (pega os bits do topo, aqui zeros): o Pico não puxava nada.
    mov(pins, null)             # valor de saída 0 nos 8 fios (a direção continua "entrada")
    pull(block)
    mov(y, osr)
    wrap_target()
    label("find")
    wait(0, gpio, 2)
    wait(1, gpio, 2)
    set(x, 31)
    label("high")
    jmp(x_dec, "high") [13]     # só vale se o E continuar em 1 por ~3 µs: um tremido antes do
    jmp(pin, "real")            # pulso (com o 'V' já nos fios) fazia o Pico puxar e soltar cedo
    jmp("find")
    label("real")
    mov(isr, null)
    in_(pins, 11)               # E, RS, RW, D0..D7 (in_base = GP2)
    mov(x, isr)
    jmp(x_not_y, "find")
    pull(block)
    out(pindirs, 8)             # ainda faltam 7 µs ou mais para a descida
    set(x, 31) [31]
    mov(isr, null)
    in_(pins, 11)               # lê o barramento ENQUANTO puxa (para conferir)
    label("hold")
    wait(0, gpio, 2)            # segura até o E ficar em 0 por ~1,7 µs: se ele "piscar" no meio
    set(x, 31)                  # do pulso (ruído no fio, que o LCD não vê), não pode soltar ainda
    label("low")
    jmp(x_dec, "low") [6]
    jmp(pin, "hold")            # jmp_pin = E
    mov(osr, null)
    out(pindirs, 8)
    push(noblock)               # avisa, com o barramento lido enquanto puxava
    wrap()


def weak(first, count):
    for n in range(first, first + count):
        pad = _PADS_BANK0 + 4 + 4 * n
        mem32[pad] = mem32[pad] & ~_DRIVE_MASK & ~1     # 2 mA, borda lenta


def release():
    for n in range(RW_PIN, D0_PIN + 8):
        Pin(n, Pin.IN, pull=None)


def show_glyph(words):
    """Os bytes do desenho 6 que o sniffer viu (na descida do E), em cada gravação da CGRAM."""
    loads, cur = [], None
    for w in words:
        if not w & (RS | RW) and (w >> DATA_SHIFT) & 0xFF == 0x40:
            cur = []
            loads.append(cur)
        elif cur is not None and w & RS and not w & RW:
            cur.append((w >> DATA_SHIFT) & 0xFF)
    for n, load in enumerate(loads, 1):
        rows = load[8 * GLYPH:8 * GLYPH + 8]
        print("  gravação %d, desenho %d:" % (n, GLYPH))
        for r in rows:
            print("    %s  %02X" % ("".join("#" if r & (0x10 >> b) else "." for b in range(5)), r))


def main():
    sn = sniffer.Sniffer()
    pio1 = rp2.PIO(1)
    flt = rp2.StateMachine(5, _e_filter, freq=150_000_000, jmp_pin=Pin(E_PIN))
    sm = rp2.StateMachine(4, _carve, freq=150_000_000, in_base=Pin(RS_PIN), out_base=Pin(D0_PIN),
                          set_base=Pin(D0_PIN))
    weak(D0_PIN, 8)
    words, carved, shown, t_carve, t_show = [], 0, 0, None, None
    try:
        sm.active(1)
        flt.active(1)
        for v in CARVE:
            sm.put(v)
        list(sn.read())
        print("Ligue o amp agora (espero %d s)..." % TIMEOUT_S)
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < TIMEOUT_S * 1000:
            words.extend(sn.read())
            if t_show is None and sm.rx_fifo():
                sm.get()
                carved += 1
                t_carve = time.ticks_ms()
                print("desenho gravado (%d)" % carved)
                for v in CARVE:
                    sm.put(v)                           # a 2ª gravação vem 64 ms depois
            if carved and t_show is None and time.ticks_diff(time.ticks_ms(), t_carve) > 1500:
                # Troca de programa: agora, mostrar o desenho no lugar do 'V', por SHOW_S segundos.
                sm.active(0)
                flt.active(0)
                pio1.remove_program()
                release()
                sm = rp2.StateMachine(4, _mask_v, freq=150_000_000, in_base=Pin(E_PIN),
                                      out_base=Pin(D0_PIN), jmp_pin=Pin(E_PIN))
                weak(D0_PIN, 8)
                sm.active(1)
                sm.put(V_WORD)
                sm.put(0x50)                            # puxa D4 e D6: 'V' 0x56 -> 0x06 (desenho 6)
                t_show = time.ticks_ms()
                print("mostrando o desenho no lugar do 'V' por %d s..." % SHOW_S)
            if SO_MOSTRAR and t_show is None and not carved:
                carved, t_carve = 1, time.ticks_add(time.ticks_ms(), -2000)
                print("(só mostrar: gire o volume um passo)")
            if t_show is not None:
                while sm.rx_fifo():
                    seen = sm.get()
                    print("  o Pico puxou na escrita do 'V'; o barramento enquanto puxava: %02X" % (
                        (seen >> DATA_SHIFT) & 0xFF))
                    shown += 1
                    sm.put(0x50)                        # a máscara para o próximo redesenho
                if time.ticks_diff(time.ticks_ms(), t_show) > SHOW_S * 1000:
                    break
            time.sleep_ms(1)
    finally:
        sm.active(0)
        flt.active(0)
        release()
        sn.stop()

    print("\nGravações do desenho: %d. Redesenhos com o desenho no lugar do 'V': %d." % (carved, shown))
    show_glyph(words)
    first = [(w >> DATA_SHIFT) & 0xFF for i, w in enumerate(words[1:], 1)
             if w & RS and not w & RW and not words[i - 2] & (RS | RW) and (words[i - 2] >> DATA_SHIFT) & 0xFF == 0x80]
    print("  1º caractere da linha 1 em cada redesenho (o Pico viu): %s" % " ".join("%02X" % b for b in first[-6:]))
    print("  (56 = 'V' normal; 06 = o desenho 6 no lugar do 'V')")
    if not carved:
        print("O amp não ligou (ou o Pico não viu o \"Set CGRAM\"). O Pico não puxou nada.")


main()
