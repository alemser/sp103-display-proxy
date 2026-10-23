"""Bancada, etapa 1: mostra no display reserva todas as telas do SP103, uma a cada 2 s.

Rodar pelo computador:  .venv/bin/mpremote run firmware/demo_telas.py
(antes, copiar os módulos: .venv/bin/mpremote cp firmware/lcd1602.py firmware/sp103_screens.py :)
"""

import time
import sp103_screens as s
from lcd1602 import Lcd1602

lcd = Lcd1602()

SCREENS = [
    ("boas-vindas", s.boot()),
    ("modelo", s.about()),
    ("normal", s.normal(-28.75, "PHONO")),
    ("volume", s.volume_bar(-28.75)),
    ("bass", s.tone("Bass", 2)),
    ("bass", s.tone("Bass", -10)),
    ("treble", s.tone("Treble", 0)),
    ("balance", s.balance(None, 0)),
    ("balance R", s.balance("R", -10.0)),
    ("balance L", s.balance("L", -10.0)),
    ("loudness", s.choice("Loudness", False)),
    ("speakers", s.choice("Speakers", True)),
    ("CGRAM 0-7", ("".join(chr(i) for i in range(8)), "Turntable")),
]

while True:
    for name, (l1, l2) in SCREENS:
        print(name)
        # Reinicia a cada tela: se um mau contato embaralhar o display, a próxima tela já sai certa.
        lcd.reset()
        for code, rows in enumerate(s.CGRAM):
            lcd.define_char(code, rows)
        lcd.show(l1, l2)
        time.sleep(2)
