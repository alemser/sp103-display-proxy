#!/usr/bin/env python3
"""Testa no computador os planos de escrita (firmware/plano.py), simulando o motor do PIO.

Gera os pulsos de um redesenho do controlador (R, C, R, D por caractere; na leitura ele solta só
o D7 e, se ler "ocupado", pergunta de novo), aplica os passos como o firmware/escrita.py faz
no PIO e entrega ao LCD (hd44780.Lcd) o que ele veria. Confere:

1. estável: o nome personalizado já está na tela, e vem um redesenho (o atrasado);
2. depois do original: a tela mostra o nome original (troca de entrada) e vem o redesenho;
3. volume: a linha 2 vira a barra; a guarda desiste e a tela sai como o controlador manda;
4. aposta errada: o plano é de uma entrada e o controlador desenha outra.

    python3 tools/test_plano.py                       # os nomes padrão (REGA, TAPE, Air)
    python3 tools/test_plano.py TUNER "Rega"          # um nome qualquer
    python3 tools/test_plano.py --passos TUNER REGA   # mostra os passos
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import plano   # noqa: E402
from amp_state import INPUTS   # noqa: E402
from hd44780 import Lcd, RS, RW, DATA_SHIFT   # noqa: E402
from sp103_screens import volume_line, volume_bar   # noqa: E402

DEFAULT = {"TUNER": "REGA", "TAPE/AUX": "TAPE"}
GLYPHS = {"r": 6}               # o desenho gravado ao ligar (teste 3)
VOLUMES = [-78.75, -40.0, -28.75, -5.0, 0.0]


class Engine:
    """O motor do PIO (firmware/escrita.py, _steps), pulso a pulso, com o tempo do LCD: RS e RW
    valem na subida do E (só contam se puxados ANTES do pulso), os dados na descida."""

    def __init__(self, plan):
        self.queue = list(plan.steps)
        self.misses = None
        self.pending = None         # ação para o próximo pulso (AFTER) ou a próxima leitura
        self.stale = False          # o pulso da ação adiada conta como falha para o passo seguinte
        self.aborted = False
        self.done = 0

    def _miss(self):
        if self.misses is None:
            self.misses = self.queue[0][1]
        if self.misses == 0:
            self.aborted = True
            return
        self.misses -= 1

    def pulse(self, w, latch):
        """w = o que o PIO lê no meio do pulso; latch = o byte que o controlador deixou nos fios.
        Devolve (o que o LCD vê, injetou?)."""
        if self.aborted or not self.queue:
            return w, False
        if self.pending is not None:
            a = self.pending
            if a & plano.THEN_END:
                if w & RW:                          # ainda é a leitura: espera ela acabar
                    self.read_seen = True
                    return w, False
                if not self.read_seen:
                    return w, False
            elif a & plano.THEN_READ and not w & RW:
                return w, False                     # ainda não é a leitura
            self.pending = None
            self.queue.pop(0)
            self.misses = None
            self.done += 1
            self.stale = True
            data_pull = (a >> 2) & 0xFF
            if w & RW and a & plano.M_RW:           # a leitura vira escrita (RS do controlador: 0)
                data = (latch | 0x80) & ~data_pull
                return 1 | (data << DATA_SHIFT), True
            out = w
            if a & plano.M_RS:
                out &= ~RS
            data = ((w >> DATA_SHIFT) & 0xFF) & ~data_pull
            return (out & ~(0xFF << DATA_SHIFT)) | (data << DATA_SHIFT), False
        if self.stale:                              # o PIO compara esse pulso já passado: falha
            self.stale = False
            self._miss()
            return w, False
        trig, _, action = self.queue[0]
        if w & plano.TRIGGER_MASK == trig & plano.TRIGGER_MASK:
            if action & plano.AFTER:
                self.pending = action
                self.read_seen = False
                return w, False
            self.queue.pop(0)
            self.misses = None
            self.done += 1
            # No meio do pulso o LCD já leu RS e RW (na subida): só os dados ainda mudam.
            if action & (plano.M_RS | plano.M_RW):
                raise AssertionError("plano puxa RS/RW no meio do pulso: o LCD não vê")
            return w & ~(((action >> 2) & 0xFF) << DATA_SHIFT), False
        self._miss()
        return w, False


def redraw(lcd, line1, line2, plan=None):
    """Um redesenho do controlador, com (ou sem) o motor. Devolve o motor."""
    eng = Engine(plan) if plan else None
    latch = 0x20
    for k in range(32):
        line, col = (line1, k) if k < 16 else (line2, k - 16)
        addr = (0x40 if k >= 16 else 0) + col
        for kind, value in (("R", None), ("C", 0x80 | addr), ("R", None), ("D", ord(line[col]))):
            while True:
                if kind == "R":
                    # O controlador solta só o D7; o LCD responde busy=0 e o contador de endereço.
                    w = 1 | RW | (((latch | 0x80) & (lcd.addr & 0x7F)) << DATA_SHIFT)
                else:
                    w = 1 | (RS if kind == "D" else 0) | (value << DATA_SHIFT)
                    latch = value
                seen, injected = eng.pulse(w, latch) if eng else (w, False)
                if not seen & RW:
                    data = (seen >> DATA_SHIFT) & 0xFF
                    (lcd.data if seen & RS else lcd.command)(data)
                # Leitura transformada em escrita com o bit 7 ligado: o controlador lê "ocupado"
                # e pergunta de novo (uma leitura a mais).
                if kind == "R" and injected and (seen >> DATA_SHIFT) & 0x80:
                    continue
                break
    return eng


def screen(lcd):
    return tuple(lcd.lines())


def lcd_with(line1, line2):
    lcd = Lcd()
    redraw(lcd, line1, line2)
    return lcd


def shown(name):
    """O que o LCD deve mostrar: as letras com desenho próprio viram o código do desenho."""
    return "".join(chr(GLYPHS[c]) if c in GLYPHS else c for c in plano.pad(name))


def check(original, name, verbose=False):
    bad = []
    pad = plano.pad
    for vol in VOLUMES:
        l1 = volume_line(vol)
        # 1 e 2: estável e depois do original.
        for before in (shown(name), pad(original)):
            lcd = lcd_with(l1, before)
            plan = plano.make(original, name, INPUTS, GLYPHS, current=lcd.lines()[1])
            if plan is None:
                return None, ["sem plano"]
            eng = redraw(lcd, l1, pad(original), plan)
            got = screen(lcd)
            if got != (l1, shown(name)):
                bad.append("vol %.2f, antes %r: %r (passos %d de %d, desistiu=%s)" % (
                    vol, before, got, eng.done, len(plan.steps), eng.aborted))
        # 3: volume (a linha 2 vira a barra).
        lcd = lcd_with(l1, shown(name))
        plan = plano.make(original, name, INPUTS, GLYPHS, current=lcd.lines()[1])
        bar1, bar2 = volume_bar(vol + 1.25 if vol < 0 else vol)
        redraw(lcd, bar1, bar2, plan)
        if screen(lcd) != (bar1, bar2):
            bad.append("barra, vol %.2f: %r" % (vol, screen(lcd)))
        # 4: aposta errada (o controlador desenha outra entrada).
        for other in INPUTS:
            if other == original or other in plan.risk:
                continue
            lcd = lcd_with(l1, shown(name))
            redraw(lcd, l1, pad(other), plan)
            if screen(lcd) != (l1, pad(other)):
                bad.append("aposta %s, veio %s: %r" % (original, other, screen(lcd)))
    return plan, bad


def main():
    args = sys.argv[1:]
    verbose = "--passos" in args
    args = [a for a in args if a != "--passos"]
    names = dict(zip(args[::2], args[1::2])) if args else DEFAULT
    fails = 0
    for original, name in names.items():
        plan, bad = check(original, name)
        if plan is None:
            print("%-9s -> %-16r SEM PLANO (não cabe)" % (original, name))
            fails += 1
            continue
        print("%-9s -> %-16r %s  (%d passos, guarda %d letra(s), desenhos %s)" % (
            original, name, "ok   " if not bad else "FALHA", len(plan.steps), plan.guard, plan.glyphs or "-"))
        for other in plan.risk:
            lcd = lcd_with(volume_line(-40), shown(name))
            redraw(lcd, volume_line(-40), plano.pad(other), plan)
            print("      risco: trocando de %s para %s, a linha 2 sai %r por 2 a 6 s" % (
                original, other, lcd.lines()[1].rstrip()))
        for b in bad[:6]:
            print("      " + b)
        fails += bool(bad)
        if verbose:
            print(plano.describe(plan))
    # Air só funciona com a guarda reduzida DAB/DVD. Esse modo é uma experiência
    # explícita; o firmware normal prefere deixar a tela original a arriscar ViD.
    if not args:
        unsafe = plano.make("DAB", "Air", INPUTS, GLYPHS, current=plano.pad("DAB"))
        print("DAB       -> 'Air'            %s" % ("BLOQUEADO (guarda insuficiente)" if unsafe is None else "FALHA"))
        fails += unsafe is not None
    print("\n%s" % ("tudo certo" if not fails else "%d com problema" % fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
