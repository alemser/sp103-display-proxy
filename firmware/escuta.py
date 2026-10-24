"""Etapa 4: escuta o barramento do LCD do amp e publica o estado na rede.

O Pico só ESCUTA: GP2..GP12 ficam como entrada (sniffer.py) e o display do amp
funciona igual a sempre. Cada tela completa vai para o leitor (amp_state) e o
estado é publicado em http://sp103.local/ (ou pelo IP).

O display reserva (GP16..21), se estiver ligado, mostra uma cópia da tela do amp
já com os textos personalizados: uma prévia do que a etapa 6 vai fazer no display do amp.

Ligação: docs/ligacao-analisador.md (os mesmos fios das capturas).
Rodar pelo computador:  .venv/bin/mpremote run firmware/escuta.py
Ou sozinho, ao ligar o Pico: main.py importa este arquivo.
"""

import time
import asyncio

import names
import sp103_screens as s
from amp_state import AmpState
from hd44780 import Bus
from lcd1602 import Lcd1602
from sniffer import Sniffer
from web import Publisher, wifi_task

# Uma tela está completa quando o controlador fica este tempo sem escrever
# (ele redesenha as duas linhas em cerca de 8,5 ms, com uma escrita a cada ~115 µs).
QUIET_US = 2000

lcd = Lcd1602()
texts = names.load()                    # textos personalizados (names.py)
state = AmpState(texts["inputs"])
bus = Bus()
sniffer = Sniffer()
last_screen = None                      # a última tela completa do amp
pub = None
notice_until = None                     # enquanto houver um aviso no display, as telas esperam


def draw():
    """Desenha no display reserva a tela do amp, já com os textos personalizados."""
    if notice_until is not None:
        return                          # aviso na tela: notice() redesenha quando acabar
    lcd.reset()                         # recupera o display de um mau contato (ver lcd1602.py)
    if last_screen is None:
        lcd.show("SP103 listener", "waiting for amp")
        return
    for code, rows in enumerate(s.CGRAM):
        lcd.define_char(code, rows)
    lcd.show(*names.rewrite(last_screen[0], last_screen[1], texts))


def set_texts(cfg):
    """Chamado pelo PUT /names: valida, guarda na flash e aplica na hora."""
    global texts
    texts = names.validate(cfg)
    names.save(texts)
    if state.set_names(texts["inputs"], time.ticks_ms()):
        pub.changed()
    draw()


async def listen():
    global last_screen
    quiet_since = time.ticks_us()
    clears = 0
    while True:
        n = 0
        for word in sniffer.read():
            bus.feed(word)
            n += 1
        now = time.ticks_us()
        if n:
            quiet_since = now
        elif bus.pending and time.ticks_diff(now, quiet_since) > QUIET_US:
            screen = bus.take()
            if bus.clears != clears:
                clears = bus.clears
                print("amp: power on (display reset)")
            if screen != last_screen:
                last_screen = screen
                print("amp: %r | %r" % screen)
                if state.update(screen[0], screen[1], time.ticks_ms()):
                    pub.changed()
                draw()
        await asyncio.sleep_ms(1)


async def notice(line1, line2, seconds=3):
    """Mostra um aviso por alguns segundos e depois volta à tela do amp."""
    global notice_until
    notice_until = True
    lcd.reset()
    lcd.show(line1, line2)
    await asyncio.sleep(seconds)
    notice_until = None
    draw()


def wifi_result(ok, info):
    # Só avisa no display se a primeira tentativa falhar; depois segue tudo normal, sem rede.
    if not ok:
        asyncio.create_task(notice("Wi-Fi failed", "offline mode"))


async def main():
    global pub
    pub = Publisher(state, get_names=lambda: texts, set_names=set_texts)
    draw()
    asyncio.create_task(wifi_task(wifi_result))
    await asyncio.sleep(0.1)            # o Wi-Fi liga antes do servidor abrir o socket
    await pub.serve()                   # atende assim que houver rede
    await listen()                      # a escuta começa na hora, com ou sem Wi-Fi


asyncio.run(main())
