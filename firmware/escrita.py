"""Escrita no display do amp sem corte: mostra os nomes personalizados (names.json) no LCD do amp.

Como funciona (docs/opcoes-intercepcao.md, testes 1 a 4; planos em plano.py):
- PIO0, máquina 1 (_e_filter): filtra o E (os fios longos fazem a borda "tremer") e avisa o
  PIO1 a cada pulso de verdade (IRQ 4 do bloco seguinte).
- PIO1, máquina 0 (_steps): executa os passos do plano, um por vez, vindos por DMA. Cada passo
  espera a sua palavra no barramento e puxa fios para 0 (agora, ou na leitura seguinte).
- Depois de cada redesenho, o Python prepara o plano do próximo (a entrada atual, a tela atual).
- Quando o amp liga (Clear display), troca por meio segundo para _carve, que grava os desenhos
  próprios (as letras que não existem nas fontes, como o 'r' de "Air").

REGRA DE SEGURANÇA (como no sniffer.py): o Pico só PUXA para 0. O valor de saída dos pinos
fica sempre em 0 (mov(pins, null)); só a direção muda. Força mínima (2 mA). Ao parar, todos
os pinos voltam a ser entrada. Armadilhas do PIO: docs/opcoes-intercepcao.md.
"""

import time
import rp2
from array import array
from machine import Pin, mem32

import plano
from amp_state import INPUTS

ENABLED = True                  # False: o Pico só escuta (o display do amp fica original)
E_PIN, RS_PIN, RW_PIN, D0_PIN = 2, 3, 4, 5
CARVE_MS = 500                  # depois do Clear, tempo gravando os desenhos (2 gravações, 64 ms)
_PIO1_TXF0 = 0x50300000 + 0x010
_DREQ_PIO1_TX0 = 8
_PADS_BANK0 = 0x40038000
_DRIVE_MASK = 0x3 << 4
_PIO1_SM0_SHIFTCTRL = 0x50300000 + 0x0D0
_IN_COUNT = 10                  # E, RS, RW, D0..D6 (plano.TRIGGER_MASK)
_CGRAM_WORD = 0x40 << 2         # "Set CGRAM 0x40", lido a partir do GP3 (RS, RW, D0..D7)
_FIRST_GLYPH_BYTE = 8 * 6 + 2   # 1ª linha que pode mudar: desenho 6, linha 2 (as 0-1 já são vazias)


@rp2.asm_pio()
def _e_filter():
    # Avisa o PIO1 (IRQ 4) uma vez por pulso de verdade do E: em 1 por ~3 µs e, depois, em 0 por
    # ~1,7 µs antes do próximo (a regra do sniffer.py). irq(0x1C) = IRQ 4 do bloco SEGUINTE (RP2350).
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
    irq(0x1C)
    label("low")
    wait(0, gpio, 2)
    set(x, 31)
    label("low_wait")
    jmp(x_dec, "low_wait") [6]  # 32 x 8 ciclos = 1,7 µs
    jmp(pin, "low")             # subiu de novo: ainda é o mesmo pulso
    wrap()


@rp2.asm_pio(out_init=(rp2.PIO.IN_LOW,) * 10, out_shiftdir=rp2.PIO.SHIFT_RIGHT)
def _steps():
    # Fila (DMA): por passo, a palavra que dispara, as falhas permitidas e a ação (plano.py).
    # Pinos de saída: GP3..GP12 = RS, RW, D0..D7, com valor 0 (out_init; conferido no Pico): só a
    # direção muda. Sempre out_shiftdir=SHIFT_RIGHT e nunca mov(pindirs, ...) (no MicroPython vira
    # mov(exec, ...)). Usa as 32 instruções do PIO1.
    #
    # mov(x, pins) lê 10 fios a partir do GP2 (E, RS, RW, D0..D6): IN_COUNT = 10 (RP2350), ligado
    # pelo Writer. Sem o D7 (o "ocupado" do LCD, que muda no meio das leituras).
    #
    # Quando puxar: o LCD lê RS e RW na SUBIDA do E e os dados na DESCIDA; o pulso que dispara só
    # é visto ~3 µs depois da subida. Então "agora" só serve para dados. Para RS e RW, a ação espera:
    # AFTER (o pulso acabar), THEN_READ (o RW subir: começo da leitura do busy flag) e THEN_END (o
    # RW descer: fim da leitura), e puxa antes do pulso seguinte. Sem os 2 µs depois do RW subir:
    # o Pico (2 mA) segura o RW contra o empurrão de ~0,2 µs do 8051.
    wrap_target()
    pull(block)
    mov(y, osr)                 # a palavra que dispara
    pull(block)                 # as falhas permitidas (ficam no OSR)
    label("find")
    wait(1, irq, 4)             # um pulso de verdade (~3 µs depois da subida)
    mov(x, pins)
    jmp(x_not_y, "miss")
    pull(block)                 # a ação
    out(x, 10)                  # os fios a puxar
    out(y, 1)                   # AFTER
    jmp(not_y, "now")
    wait(0, gpio, 2)            # o pulso que disparou acaba
    out(y, 1)                   # THEN_READ
    jmp(not_y, "now")
    wait(1, gpio, 4)            # o RW sobe: começa a leitura do busy flag (o E sobe ~21 µs depois)
    out(y, 1)                   # THEN_END
    jmp(not_y, "now")
    wait(0, gpio, 4)            # o RW desce: a leitura acabou (o próximo pulso é a escrita)
    label("now")
    mov(osr, x)
    out(pindirs, 10)            # PUXA
    label("hold")
    wait(1, gpio, 2)            # o pulso (o atual, ou o seguinte)...
    wait(0, gpio, 2)            # ...acaba, e o E fica em 0 por ~1,7 µs
    set(y, 31)
    label("low")
    jmp(y_dec, "low") [6]
    jmp(pin, "hold")            # jmp_pin = E
    mov(osr, null)
    out(pindirs, 10)            # solta
    push(noblock)               # passo feito
    wrap()
    label("miss")
    mov(x, osr)
    jmp(x_dec, "more")
    label("stop")
    jmp("stop")                 # passou do limite de falhas: desiste até o Python rearmar
    label("more")
    mov(osr, x)
    jmp("find")


@rp2.asm_pio(out_init=(rp2.PIO.IN_LOW,) * 5, set_init=(rp2.PIO.IN_LOW,) * 5,
             in_shiftdir=rp2.PIO.SHIFT_LEFT, out_shiftdir=rp2.PIO.SHIFT_RIGHT, pull_thresh=30)
def _carve():
    # Fila: o comando "Set CGRAM 0x40", quantos bytes pular, quantas linhas - 1, as máscaras
    # (6 linhas de 5 bits por palavra; pull(ifempty) busca a próxima). Sem autopull.
    mov(pins, null)
    wrap_target()
    pull(block)
    mov(y, osr)
    label("find")
    wait(1, irq, 4)
    mov(isr, null)
    in_(pins, 10)               # RS, RW, D0..D7 (in_base = GP3)
    mov(x, isr)
    jmp(x_not_y, "find")
    pull(block)
    mov(y, osr)                 # bytes a pular
    label("skip")
    wait(1, irq, 4)
    jmp(y_dec, "skip")          # quando y chega a 0, este pulso é a 1ª linha
    pull(block)
    mov(y, osr)                 # linhas - 1
    out(null, 32)               # esvazia o OSR: as máscaras vêm pelo pull(ifempty)
    label("row")
    pull(ifempty, block)
    out(pindirs, 5)             # apaga os pontos desta linha (D0..D4)
    label("hold")
    wait(0, gpio, 2)
    set(x, 31)
    label("low")
    jmp(x_dec, "low") [6]
    jmp(pin, "hold")            # jmp_pin = E
    set(pindirs, 0)
    jmp(y_dec, "next")
    push(noblock)               # desenhos gravados
    wrap()
    label("next")
    wait(1, irq, 4)
    jmp("row")


def _weak(first, count):
    for n in range(first, first + count):
        pad = _PADS_BANK0 + 4 + 4 * n
        mem32[pad] = mem32[pad] & ~_DRIVE_MASK & ~1     # 2 mA, borda lenta


def _release():
    for n in range(RS_PIN, D0_PIN + 8):
        Pin(n, Pin.IN, pull=None)


class Writer:
    def __init__(self):
        self.filter = rp2.StateMachine(1, _e_filter, freq=150_000_000, jmp_pin=Pin(E_PIN))
        self.filter.active(1)
        self.sm = None
        self.prog = None
        self.dma = rp2.DMA()
        self.buf = None
        self.names = {}
        self.wanted = {}            # desenhos escolhidos: {letra: código}
        self.feasible = {}          # {entrada: Plan ou None}, com os desenhos escolhidos
        self.cache = {}
        self.carve_until = None
        self.armed = None           # (entrada, nº de passos) do plano armado
        self.done = 0               # passos feitos no último plano
        self.last = None            # (entrada, passos feitos, passos do plano) do último redesenho
        self.result = "idle"        # idle, armed, complete, aborted, carving

    # --- configuração (nomes da página) ---

    def configure(self, inputs_names):
        """{original: personalizado} da página (names.json). Escolhe os desenhos e confere."""
        self.names = {o: t for o, t in inputs_names.items() if t and t != o}
        self.wanted, self.feasible = plano.choose(self.names, INPUTS)
        self.cache = {}

    def status(self, lcd=None):
        """Para a página: {entrada: texto} (em inglês, como a página)."""
        out = {}
        have = self.glyphs(lcd) if lcd else {}
        for o in self.names:
            p = self.feasible.get(o)
            if not ENABLED:
                out[o] = "amp display: writing is off"
            elif p is None:
                out[o] = "amp display: doesn't fit (spare display only)"
            else:
                need = [c for c in self.names[o] if c in self.wanted]
                msg = "amp display: ok"
                if need and any(c not in have for c in need):
                    msg += " after the amp is switched on with the Pico running (custom letter %s)" % (
                        "".join(sorted(set(need))))
                if p.risk:
                    msg += "; switching to %s may show it wrong for 2-6 s" % "/".join(p.risk)
                if self.last and self.last[0] == o:
                    msg += "; last plan: %d/%d (%s)" % (self.last[1], self.last[2], self.result)
                out[o] = msg
        return out

    def original(self, screen):
        """A tela como o controlador a mandou: o nome personalizado na linha 2 volta a ser o
        original (para o leitor de telas, amp_state, reconhecer a entrada)."""
        line1, line2 = screen
        for o, t in self.names.items():
            if line2 in (plano.pad(t), plano.shown(t, self.wanted)):
                return line1, plano.pad(o)
        return screen

    def glyphs(self, lcd):
        """Os desenhos escolhidos que o LCD tem gravados agora (conferidos na cópia do LCD)."""
        have = {}
        for ch, code in self.wanted.items():
            rows = plano.glyph_rows(ch, code)
            if rows and bytes(lcd.cgram[8 * code:8 * code + 8]) == bytes(rows):
                have[ch] = code
        return have

    # --- motor ---

    def _start(self, prog, **pins):
        self.stop()
        if self.prog is not None and self.prog is not prog:
            rp2.PIO(1).remove_program(self.prog)    # o PIO1 só cabe um dos dois programas
        self.prog = prog
        self.sm = rp2.StateMachine(4, prog, freq=150_000_000, in_base=Pin(pins["in_base"]),
                                   out_base=Pin(pins["out_base"]), jmp_pin=Pin(E_PIN),
                                   **({"set_base": Pin(pins["out_base"])} if prog is _carve else {}))
        _weak(RS_PIN, 10)
        if prog is _steps:
            v = mem32[_PIO1_SM0_SHIFTCTRL]
            mem32[_PIO1_SM0_SHIFTCTRL] = (v & ~0x1F) | _IN_COUNT    # mov(x, pins) vê só 10 fios

    def _feed(self, words):
        self.buf = array("I", words)
        ctrl = self.dma.pack_ctrl(size=2, inc_read=True, inc_write=False, treq_sel=_DREQ_PIO1_TX0)
        self.dma.config(read=self.buf, write=_PIO1_TXF0, count=len(words), ctrl=ctrl, trigger=True)

    def stop(self):
        if self.sm is not None:
            self.sm.active(0)
        self.dma.active(0)
        _release()                  # pinos de volta a entrada (mesmo se parou segurando)
        if self.armed:
            self.last = (self.armed[0], self.done, self.armed[1])
            self.result = "complete" if self.done == self.armed[1] else "aborted"
        self.armed = None

    def poll(self):
        """Chamar sempre (laço da escuta): conta os passos feitos e encerra a gravação."""
        while self.sm is not None and self.sm.rx_fifo():
            self.sm.get()
            self.done += 1
            if self.carve_until is not None:
                self._feed(self._carve_words())     # pode vir outra gravação (64 ms depois)
        if self.carve_until is not None and time.ticks_diff(time.ticks_ms(), self.carve_until) > 0:
            self.carve_until = None
            print("escrita: %d gravação(ões) de desenhos" % self.done)
            self.stop()

    def power_on(self):
        """O amp acabou de ligar (Clear): grava os desenhos escolhidos, se houver."""
        if not ENABLED or not self.wanted:
            self.stop()
            return
        self._start(_carve, in_base=RS_PIN, out_base=D0_PIN)
        self.done = 0
        self.result = "carving"
        self._feed(self._carve_words())
        self.sm.active(1)
        self.carve_until = time.ticks_add(time.ticks_ms(), CARVE_MS)

    def _carve_words(self):
        masks = []
        for byte in range(_FIRST_GLYPH_BYTE, 64):
            code, row = divmod(byte, 8)
            full = 0x1F if row >= 8 - code else 0
            want = full
            for ch, k in self.wanted.items():
                if k == code:
                    want = plano.glyph_rows(ch, k)[row]
            masks.append(full & ~want)
        words = [_CGRAM_WORD, _FIRST_GLYPH_BYTE, len(masks) - 1]
        for i in range(0, len(masks), 6):
            v = 0
            for j, m in enumerate(masks[i:i + 6]):
                v |= m << (5 * j)
            words.append(v)
        return words

    def after_screen(self, lcd, current_input):
        """Depois de cada redesenho: arma o plano do próximo (aposta: a entrada não muda)."""
        if self.carve_until is not None:
            return
        self.stop()
        name = self.names.get(current_input)
        if not ENABLED or not name:
            return
        line1, line2 = lcd.lines()
        # As letras emprestadas da linha 1 ficam na tela de antes: só se ela for a de volume.
        if any(line1[c] != plano.LINE1_TEXT[c] for c in plano.LINE1_STATIC):
            return
        have = self.glyphs(lcd)
        key = (current_input, name, tuple(sorted(have.items())), line2)
        plan = self.cache.get(key)
        if key not in self.cache:
            plan = plano.make(current_input, name, INPUTS, have, current=line2)
            if len(self.cache) > 32:
                self.cache = {}
            self.cache[key] = plan
        if plan is None:
            return
        self._start(_steps, in_base=E_PIN, out_base=RS_PIN)
        self.done = 0
        self._feed(plan.words())
        self.sm.active(1)
        self.armed = (current_input, len(plan.steps))
        self.result = "armed"
