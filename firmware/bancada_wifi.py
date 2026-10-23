"""Bancada, etapa 3: estado do amp na rede, com um "amp de mentira".

Um amp simulado desenha as telas do SP103 no display reserva, como o controlador
faria. Cada tela passa pelo leitor (amp_state), exatamente como vai acontecer
com o sniffer, e o estado é publicado em http://sp103.local/ (ou pelo IP).

Rodar pelo computador:  .venv/bin/mpremote run firmware/bancada_wifi.py
Ou sozinho, ao ligar o Pico: main.py importa este arquivo (ver main.py).
"""

import time
import random
import asyncio

import names
import sp103_screens as s
from amp_state import AmpState, INPUTS
from lcd1602 import Lcd1602
from web import Publisher, connect_wifi, keep_wifi

lcd = Lcd1602()
state = AmpState(names.load())
last_screen = ("", "")
pub = None


def draw(l1, l2):
    """Desenha no display a tela do amp, já com os nomes da tabela."""
    lcd.reset()                         # recupera o display de um mau contato (ver lcd1602.py)
    for code, rows in enumerate(s.CGRAM):
        lcd.define_char(code, rows)
    lcd.show(*names.rewrite(l1, l2, state.names))


def show(screen):
    """O "amp" desenhou uma tela: o leitor lê a original e o display mostra a reescrita,
    como vai ser no amp de verdade."""
    global last_screen
    last_screen = screen
    if state.update(screen[0], screen[1], time.ticks_ms()):
        pub.changed()
    draw(*screen)


def set_names(table):
    """Chamado pelo PUT /names: valida, guarda na flash e aplica na hora."""
    table = names.validate(table)
    names.save(table)
    if state.set_names(table, time.ticks_ms()):
        pub.changed()
    draw(*last_screen)


class FakeAmp:
    """Imita o controlador: guarda valores e desenha as mesmas telas que ele."""

    def __init__(self):
        self.volume = -28.75
        self.input = "PHONO"
        self.bass = 2
        self.treble = 0
        self.balance = (None, 0.0)
        self.loudness = False
        self.speakers = True

    async def power_on(self):
        show(s.boot())
        await asyncio.sleep(2)
        show(s.about())
        await asyncio.sleep(2)
        show(s.normal(self.volume, self.input))

    async def turn_volume(self, clicks):
        step = 1.25 if clicks > 0 else -1.25
        for _ in range(abs(clicks)):
            self.volume = min(0.0, max(-78.75, self.volume + step))
            show(s.volume_bar(self.volume))
            await asyncio.sleep(0.4)
        await asyncio.sleep(2)          # a barra volta sozinha ao nome da entrada
        show(s.normal(self.volume, self.input))

    async def select_input(self, name):
        self.input = name
        show(s.normal(self.volume, self.input))

    async def function_menu(self):
        """Os 5 menus do Function, mexendo num valor qualquer, e volta à tela normal."""
        self.bass = random.choice((-4, -2, 0, 2, 4, 6))
        self.treble = random.choice((-2, 0, 2))
        side = random.choice(("L", "R", None))
        self.balance = (side, 0.0) if side is None else (side, -1.25 * random.randint(1, 10))
        self.loudness = not self.loudness
        for screen in (s.tone("Bass", self.bass), s.tone("Treble", self.treble),
                       s.balance(*self.balance), s.choice("Loudness", self.loudness),
                       s.choice("Speakers", self.speakers)):
            show(screen)
            await asyncio.sleep(1.5)
        show(s.normal(self.volume, self.input))


async def demo():
    amp = FakeAmp()
    await amp.power_on()
    while True:
        await asyncio.sleep(4)
        await amp.turn_volume(random.choice((-4, -2, 2, 4)))
        await asyncio.sleep(4)
        await amp.select_input(random.choice(INPUTS))
        await asyncio.sleep(4)
        await amp.function_menu()


async def main():
    global pub
    ip = connect_wifi(on_attempt=lambda n: lcd.show("Connecting Wi-Fi", "attempt %d" % n))
    print("Wi-Fi ok. Open http://%s/  (or http://sp103.local/)" % ip)
    lcd.show("Wi-Fi ok", ip)
    pub = Publisher(state, on_names=set_names)
    await pub.serve()
    asyncio.create_task(keep_wifi())
    await asyncio.sleep(3)
    await demo()


asyncio.run(main())
