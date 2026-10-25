#!/usr/bin/env python3
"""Testes da política de refresh fechado, sem Wi-Fi nem hardware."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

from refresh import Refresh  # noqa: E402


class Writer:
    def __init__(self, result="complete"):
        self.result = result
        self.armed = 0
        self.stopped = 0

    def after_screen(self, lcd, input_name):
        assert input_name == "TUNER"
        self.armed += 1

    def stop(self):
        self.stopped += 1


def main():
    w = Writer()
    r = Refresh(rig=object())
    r.phase, r.input = "waiting_bar", "TUNER"
    assert r.screen("volume", w, object(), "TUNER")
    assert (r.phase, w.armed) == ("armed", 1)
    assert r.screen("normal", w, object(), "TUNER")
    assert (r.phase, w.stopped) == ("complete", 1)

    w = Writer("aborted")
    r = Refresh(rig=object())
    r.phase, r.input = "armed", "TUNER"
    assert r.screen("normal", w, object(), "TUNER")
    assert r.phase == "failed" and r.error == "write plan aborted"
    print("refresh: ok")


if __name__ == "__main__":
    main()
