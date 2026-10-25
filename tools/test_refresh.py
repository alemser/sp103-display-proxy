#!/usr/bin/env python3
"""Checagens da confirmação/rearme sem Wi-Fi nem hardware."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import refresh as refresh_module  # noqa: E402
import plano  # noqa: E402
from refresh import Refresh  # noqa: E402


class Writer:
    names = {"TUNER": "REGA"}
    wanted = {}
    result = "complete"

    def glyphs(self, lcd):
        return {}


class Lcd:
    def __init__(self, row2):
        self.row2 = (row2 + " " * 16)[:16]

    def lines(self):
        return "Volume -40.00 dB", self.row2


class FakeClock:
    def __init__(self):
        self.now = 1000

    def ticks_ms(self):
        return self.now

    @staticmethod
    def ticks_diff(a, b):
        return a - b


def main():
    r = Refresh()
    r.request("TUNER")
    w = Writer()

    # A confirmação vem da linha 2 modelada, não do número de passos ou de uma
    # ação externa. Cada repaint correto conta e mantém o ciclo concluído.
    r.screen("normal", w, Lcd("REGA"), "TUNER")
    assert r.phase == "complete" and r.verified_redraws == 1
    r.screen("normal", w, Lcd("REGA"), "TUNER")
    assert r.phase == "complete" and r.verified_redraws == 2

    # Um repaint que apaga o nome degrada a confirmação; o escritor continuará
    # sendo rearmado pelo laço principal.
    r.screen("normal", w, Lcd("TUNER"), "TUNER")
    assert r.phase == "degraded" and r.error == "linha 2 não confere após redraw"

    # Nunca atribui uma tela de outra entrada à transação anterior.
    r.screen("normal", w, Lcd("DVD"), "DVD")
    assert r.phase == "cancelled"

    # O Pico reconhece a tela original depois do primeiro toque e precisa esperar
    # um novo redraw real para escrever. A telemetria separa esse primeiro redraw
    # da primeira tela que realmente confirmou o nome, sem acionar outro sistema.
    clock = FakeClock()
    old = {name: getattr(refresh_module, name)
           for name in ("_ticks_ms", "_ticks_diff")}
    for name, method in (("_ticks_ms", clock.ticks_ms),
                         ("_ticks_diff", clock.ticks_diff)):
        setattr(refresh_module, name, method)
    try:
        r = Refresh()
        r.request("TUNER")
        status = r.status()
        assert status["phase"] == "waiting_redraw"
        assert "fallback_enabled" not in status and "input_id" not in status
        assert "trace" not in status and "prearm" not in status

        clock.now = 1200
        r.screen("normal", w, Lcd("TUNER"), "TUNER")
        status = r.status()
        assert status["phase"] == "waiting_redraw"
        assert status["redraws_seen"] == 1 and status["first_redraw_ms"] == 200
        assert status["last_actual_matches"] is False
        assert status["last_actual"] == "TUNER" + " " * 11

        clock.now = 1700
        r.screen("normal", w, Lcd("REGA"), "TUNER")
        status = r.status()
        assert status["phase"] == "complete" and status["verified_redraws"] == 1
        assert status["first_verified_ms"] == 700

        # As métricas separam a tela original do controlador de uma tela inesperada.
        r = Refresh()
        r.request("TUNER")
        r.screen("normal", w, Lcd("TUNER"), "TUNER")
        assert r.original_redraws == 1 and r.unexpected_redraws == 0
        r.screen("normal", w, Lcd("CD"), "TUNER")
        assert r.unexpected_redraws == 1

        # Código DDRAM certo com desenho CGRAM ausente é erro de integridade:
        # não se pode afirmar que a letra visível está certa.
        class GlyphWriter(Writer):
            names = {"TUNER": "Re"}
            wanted = {"e": 6}

            def glyphs(self, lcd):
                return {}

        gw = GlyphWriter()
        r = Refresh()
        r.request("TUNER")
        r.screen("normal", gw, Lcd(plano.shown("Re", gw.wanted)), "TUNER")
        assert r.last_actual_matches is True
        assert r.phase == "waiting_glyphs" and r.integrity_errors == 1

    finally:
        for name, value in old.items():
            setattr(refresh_module, name, value)

    print("refresh: ok")


if __name__ == "__main__":
    main()
