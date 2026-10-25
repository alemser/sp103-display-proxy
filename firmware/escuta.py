"""Etapa 4: escuta o barramento do LCD do amp e publica o estado na rede.

O Pico só ESCUTA: GP2..GP12 ficam como entrada (sniffer.py) e o display do amp
funciona igual a sempre. Cada tela completa vai para o leitor (amp_state) e o
estado é publicado em http://sp103.local/ (ou pelo IP).

O display reserva (GP16..21), se estiver ligado, mostra uma cópia da tela do amp
já com os textos personalizados: uma prévia do que a etapa 6 vai fazer no display do amp.

Escreve no display do amp os nomes personalizados que cabem (escrita.py, plano.py), só
puxando fios para 0. Para desligar: ENABLED = False em escrita.py.

Também em http://sp103.local/bus: estatísticas do barramento e download das últimas
palavras lidas (buslog.py). E aceita atualização pelo Wi-Fi (ota.py, tools/enviar.py).

Ligação: docs/ligacao-analisador.md (os mesmos fios das capturas).
Rodar pelo computador:  .venv/bin/mpremote run firmware/escuta.py
Ou sozinho, ao ligar o Pico: main.py importa este arquivo.
"""

import time
import asyncio

import escrita
import names
import ota
import refresh
import sp103_screens as s
from amp_state import AmpState
from buslog import BusLog
from hd44780 import Bus
from lcd1602 import Lcd1602
from sniffer import Sniffer
from web import Publisher, wifi_task

# Uma tela está completa quando o controlador fica este tempo sem escrever
# (ele redesenha as duas linhas em cerca de 8,5 ms, com uma escrita a cada ~115 µs).
QUIET_US = 2000
CLOCK_EVERY_S = 6 * 3600                # acerta o relógio pela internet a cada 6 h

lcd = Lcd1602()
texts = names.load()                    # textos personalizados (names.py)
state = AmpState(texts["inputs"])
bus = Bus()
log = BusLog(bus)
sniffer = Sniffer()
writer = escrita.Writer()
writer.configure(texts["inputs"])
refresher = refresh.Refresh()
last_screen = None                      # a última tela completa do amp
pub = None
wifi_ok = False
listen_ticks = 0                        # voltas da escuta: mostra que ela não travou
notice_until = None                     # enquanto houver um aviso no display, as telas esperam
rearm_pending = False                   # PUT /names pediu um rearme fora do redraw


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
    global texts, rearm_pending
    texts = names.validate(cfg)
    names.save(texts)
    if state.set_names(texts["inputs"], time.ticks_ms()):
        pub.changed()
    writer.configure(texts["inputs"])
    if state.screen == "normal" and state.input in writer.names \
            and writer.feasible.get(state.input) is not None:
        refresher.request(state.input)
    # Não rearma aqui: o plano pode estar no meio de um redraw. O laço da
    # escuta espera o barramento ficar quieto e arma com os textos novos.
    rearm_pending = True
    draw()


async def listen():
    global last_screen, listen_ticks, rearm_pending
    quiet_since = time.ticks_us()
    clears = 0
    while True:
        n = 0
        ms = time.ticks_ms()
        for word in sniffer.read():
            bus.feed(word)
            log.add(ms, word)
            n += 1
        log.poll(ms, n)
        listen_ticks += 1
        if bus.clears != clears:
            # O amp ligou: os desenhos próprios são gravados daqui a 2 e 64 ms. Visto a cada
            # lote (não só no fim da tela) para dar tempo de o escrita.py pegar a gravação.
            clears = bus.clears
            print("amp: power on (display reset)")
            writer.power_on()
        writer.poll()
        now = time.ticks_us()
        if n:
            quiet_since = now
        quiet = time.ticks_diff(now, quiet_since) > QUIET_US
        if not n and bus.pending and quiet:
            # A tela que o LCD mostra pode ter o nome personalizado; o leitor recebe a original.
            screen = writer.original(bus.take())
            input_changed = False
            if screen != last_screen:
                last_screen = screen
                print("amp: %r | %r" % screen)
                old_input = state.input
                changed = state.update(screen[0], screen[1], time.ticks_ms())
                input_changed = state.input != old_input
                if changed:
                    pub.changed()
                draw()
            log.screen(ms, state.screen != "unknown")
            # Fecha o plano do redraw recém-observado antes de verificar o resultado.
            # A observação da entrada nova começa com a primeira tela completa;
            # só um redraw posterior pode confirmar a escrita nessa topologia.
            writer.stop()
            if state.screen == "normal" and input_changed \
                    and state.input in writer.names \
                    and writer.feasible.get(state.input) is not None:
                refresher.request(state.input)
            refresher.screen(state.screen, writer, bus.lcd, state.input)
            writer.after_screen(bus.lcd, state.input)
            rearm_pending = False
        elif not n and quiet and rearm_pending \
                and writer.carve_until is None:
            # PUT /names: arma só com o barramento parado, nunca no meio de um
            # redraw, e aproveita a tela completa que o modelo tem.
            rearm_pending = False
            writer.stop()
            writer.after_screen(bus.lcd, state.input)
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
    global wifi_ok
    wifi_ok = ok
    # Só avisa no display se a primeira tentativa falhar; depois segue tudo normal, sem rede.
    if not ok:
        asyncio.create_task(notice("Wi-Fi failed", "offline mode"))
    else:
        asyncio.create_task(clock_task())


async def clock_task():
    """Acerta o relógio pela internet (NTP), para o registro do barramento ter horário."""
    import ntptime
    while True:
        try:
            ntptime.settime()                   # o relógio do Pico fica em UTC
            # time.time() só tem segundos: espera o segundo virar para casar com o ticks_ms.
            t0 = time.time()
            while time.time() == t0:
                await asyncio.sleep_ms(5)
            log.set_clock(time.time(), time.ticks_ms())
            print("clock set (UTC):", time.gmtime()[:6])
            await asyncio.sleep(CLOCK_EVERY_S)
        except Exception as e:                  # sem internet: tenta de novo em 1 min
            print("clock:", e)
            await asyncio.sleep(60)


async def confirm_update():
    """Versão nova em teste (ota.py): confirma quando ela se mostra saudável. Sem isso,
    o main.py volta para a versão anterior. Saudável = a escuta roda, o Wi-Fi conectou e
    a página respondeu a alguém (o tools/enviar.py pergunta a cada 2 s), por 20 s seguidos."""
    if not ota.in_trial():
        return
    start = time.ticks_ms()
    seen = listen_ticks
    while True:
        await asyncio.sleep(2)
        alive = listen_ticks != seen
        seen = listen_ticks
        if not (alive and wifi_ok and pub.served):
            start = time.ticks_ms()
        elif time.ticks_diff(time.ticks_ms(), start) > 20000:
            ota.confirm()
            return


async def main():
    global pub
    pub = Publisher(state, get_names=lambda: texts, set_names=set_texts,
                    names_extra=lambda: {"amp": writer.status(bus.lcd), "refresh": refresher.status()},
                    routes={"/update": ota.handle, "/bus": log.handle})
    log.clear(time.ticks_ms())
    draw()
    asyncio.create_task(wifi_task(wifi_result))
    await asyncio.sleep(0.1)            # o Wi-Fi liga antes do servidor abrir o socket
    await pub.serve()                   # atende assim que houver rede
    asyncio.create_task(confirm_update())
    await listen()                      # a escuta começa na hora, com ou sem Wi-Fi


asyncio.run(main())
