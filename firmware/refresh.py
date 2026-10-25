"""Observação fechada da persistência, sem controlar o amplificador.

O Pico não é um segundo mestre do HD44780: ele só injeta durante uma escrita do
controlador. Portanto, "persistir" significa armar novamente o plano após cada
tela completa que o amplificador realmente redesenha. Este módulo não envia IR,
HTTP, nem qualquer comando ao amplificador ou a outro equipamento.

O resultado observado vem do modelo HD44780 alimentado pelo sniffer, não de uma
leitura elétrica de volta do LCD. A guarda estrita de plano.py continua sendo a
última barreira antes de qualquer injeção destrutiva.
"""

import time

import plano
from amp_state import lcd_text


def _ticks_ms():
    return time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.monotonic() * 1000)


def _ticks_diff(a, b):
    return time.ticks_diff(a, b) if hasattr(time, "ticks_diff") else a - b


class Refresh:
    """Acompanha uma entrada até que um redraw real confirme o texto.

    A primeira tela que revela uma troca já terminou quando o sniffer a
    reconhece. Não existe comando externo para fabricar outra: o escritor fica
    armado e a confirmação só chega no próximo redraw do controlador.
    """

    def __init__(self):
        self.input = None
        self.phase = "idle"
        self.error = None
        self.verified_redraws = 0
        self.last_plan = None
        self.requested_at = None
        self.redraws_seen = 0
        self.first_redraw_ms = None
        self.first_verified_ms = None
        self.last_actual_matches = None
        self.last_actual = None
        self.original_redraws = 0
        self.unexpected_redraws = 0
        self.integrity_errors = 0

    def status(self):
        return {"phase": self.phase, "input": self.input, "error": self.error,
                "verified_redraws": self.verified_redraws,
                "redraws_seen": self.redraws_seen,
                "first_redraw_ms": self.first_redraw_ms,
                "first_verified_ms": self.first_verified_ms,
                "last_actual_matches": self.last_actual_matches,
                "last_actual": self.last_actual,
                "last_plan": self.last_plan,
                "original_redraws": self.original_redraws,
                "unexpected_redraws": self.unexpected_redraws,
                "integrity_errors": self.integrity_errors}

    def request(self, input_name):
        """Começa a observar a entrada; nunca envia comandos ao amplificador."""
        if input_name is None:
            return False
        self.input = input_name
        self.phase = "waiting_redraw"
        self.error = None
        self.verified_redraws = 0
        self.last_plan = None
        self.requested_at = _ticks_ms()
        self.redraws_seen = 0
        self.first_redraw_ms = None
        self.first_verified_ms = None
        self.last_actual_matches = None
        self.last_actual = None
        self.original_redraws = 0
        self.unexpected_redraws = 0
        self.integrity_errors = 0
        return True

    def screen(self, screen, writer, lcd, input_name):
        """Observa uma tela completa. Não consome o evento nem impede o próximo plano."""
        if self.phase in ("idle", "cancelled"):
            return
        if input_name != self.input:
            self.phase = "cancelled"
            self.error = "entrada mudou antes da confirmação"
            return
        if screen != "normal":
            return

        # after_screen() será chamado logo depois pelo laço principal. writer.stop()
        # já foi chamado antes desta função, então last/result correspondem ao redraw.
        target = writer.names.get(self.input)
        if not target:
            return
        expected = plano.shown(target, writer.wanted)
        actual = lcd.lines()[1]
        self.last_actual = lcd_text(actual)
        self.last_plan = writer.result
        now = _ticks_ms()
        age_ms = _ticks_diff(now, self.requested_at) if self.requested_at is not None else None
        self.redraws_seen += 1
        if self.first_redraw_ms is None:
            self.first_redraw_ms = age_ms
        have_glyphs = writer.glyphs(lcd)
        glyphs_ok = True
        for ch in target:
            if ch in writer.wanted and ch not in have_glyphs:
                glyphs_ok = False
                break
        self.last_actual_matches = actual == expected
        if self.last_actual_matches and glyphs_ok:
            self.verified_redraws += 1
            if self.first_verified_ms is None:
                self.first_verified_ms = age_ms
            self.phase, self.error = "complete", None
        elif self.last_actual_matches:
            # Código DDRAM certo, mas o desenho CGRAM não foi confirmado: o texto
            # visível não pode ser considerado íntegro.
            self.integrity_errors += 1
            self.phase = "waiting_glyphs"
            self.error = "desenho CGRAM ainda não observado"
        else:
            if actual == plano.pad(self.input):
                self.original_redraws += 1
            else:
                self.unexpected_redraws += 1
            # O plano continua sendo rearmado pelo laço principal no próximo redraw.
            self.phase = "degraded" if self.phase == "complete" else "waiting_redraw"
            self.error = "linha 2 não confere após redraw"
