"""Etapa 6: o Pico no meio, entre o controlador do amp e o display (opção 3b).

O display do amp foi dessoldado nos pinos 4..14 (docs/proxy-ligacao.md):
- lado do controlador: GP2..GP12 (E, RS, RW, D0..D7), como na escuta. O Pico só lê
  (sniffer.py) e responde "livre" às leituras do busy flag (busy.py), puxando o D7 para 0;
- lado do display: GP16..21 (RS, E, D4..D7), modo 4 bits, RW do display no GND (lcd1602.py).

Cada tela completa do controlador é reconstruída (hd44780.py), vai para o leitor
(amp_state) e é desenhada no display do amp já com os textos personalizados
(names.rewrite). Os desenhos próprios (CGRAM) e o "display on/off" seguem os do controlador.

Com o VU ligado na página (vu.py), as duas linhas viram as barras L e R enquanto houver
música; cada redesenho do controlador traz a tela do amp de volta por 3 s.

Publica o estado em http://sp103.local/ (ou pelo IP), com /bus e atualização pelo Wi-Fi,
como a escuta. Sem Wi-Fi, o display continua funcionando.

Rodar pelo computador:  .venv/bin/mpremote run firmware/proxy.py
Ou sozinho, ao ligar o Pico: main.py importa escuta.py, que importa este arquivo.
"""

# Primeiro de tudo: o controlador fica parado, perguntando "ocupado?", até o Pico
# responder. O Sniffer vem antes do Responder (ver busy.py).
from sniffer import Sniffer
sniffer = Sniffer()
import busy
responder = busy.Responder()

import time
import asyncio

import names
import ota
import sp103_screens as s
import vu as vu_meter
from amp_state import AmpState
from buslog import BusLog
from hd44780 import Bus, RW
from lcd1602 import Lcd1602
from web import Publisher, wifi_task

# Uma tela está completa quando o controlador fica este tempo sem escrever
# (ele redesenha as duas linhas em cerca de 8,5 ms, com uma escrita a cada ~115 µs).
QUIET_US = 2000
REFRESH_MS = 30_000                     # redesenha tudo de vez em quando (ruído nos fios)
AMP_HOLD_MS = 3000                      # com o VU ligado, a tela do amp fica 3 s depois de cada redesenho
CLOCK_EVERY_S = 6 * 3600                # acerta o relógio pela internet a cada 6 h
D7 = 1 << 10                            # o D7 na palavra do sniffer (hd44780.py)

lcd = Lcd1602()                         # já limpa o display
texts = names.load()                    # textos personalizados (names.py)
state = AmpState(texts["inputs"])
bus = Bus()
# O Pico pode ligar depois do controlador ter gravado os desenhos (ao ligar o amp):
# começa com os das capturas, e o modelo troca se o controlador gravar outros.
bus.lcd.cgram[:] = bytes(b for rows in s.CGRAM for b in rows)
log = BusLog(bus)
pub = None
wifi_ok = False
listen_ticks = 0                        # voltas da escuta: mostra que ela não travou
busy_high = 0                           # leituras em que o controlador viu "ocupado"
answered = False                        # já houve uma leitura com "livre" (o Responder no ar)
shown = [None, None]                    # o que está no display do amp agora
shown_cgram = None
shown_on = None
last_full = time.ticks_ms()
vu = vu_meter.Vu()
vu.configure(texts["vu"])
vu_mode = False                         # o display mostra o VU (e os desenhos dele)
amp_until = time.ticks_ms()             # até aqui, a tela do amp tem a vez


def draw(full=False):
    """Põe no display do amp a tela do controlador, com os textos personalizados.
    Só manda o que mudou; full=True resincroniza e reescreve tudo (sem apagar a tela)."""
    global shown_cgram, shown_on, last_full, vu_mode
    vu_mode = False
    m = bus.lcd
    if full:
        lcd.resync()
        shown[0] = shown[1] = shown_cgram = shown_on = None
        last_full = time.ticks_ms()
    cgram = bytes(m.cgram)
    if cgram != shown_cgram:
        for code in range(8):
            lcd.define_char(code, cgram[8 * code:8 * code + 8])
        shown_cgram = cgram
    line1, line2 = m.lines()
    for row, text in enumerate(names.rewrite(line1, line2, texts)):
        if text != shown[row]:
            lcd.write_line(row, text)
            shown[row] = text
    if m.display_on != shown_on:
        lcd.display(m.display_on)
        shown_on = m.display_on


def show_vu(full=False):
    """Põe o VU no display. Os desenhos do VU tomam o lugar dos do controlador;
    o draw() seguinte grava os do controlador de volta (o shown_cgram muda)."""
    global shown_cgram, last_full, vu_mode
    vu_mode = True
    if full:
        lcd.resync()
        shown[0] = shown[1] = shown_cgram = None
        last_full = time.ticks_ms()
    if shown_cgram != vu.glyphs:
        for code in range(8):
            lcd.define_char(code, vu.glyphs[8 * code:8 * code + 8])
        shown_cgram = vu.glyphs
    for row, text in enumerate(vu.lines()):
        if text != shown[row]:
            lcd.write_line(row, text)
            shown[row] = text


def set_texts(cfg):
    """Chamado pelo PUT /names: valida, guarda na flash e aplica na hora."""
    global texts
    texts = names.validate(cfg)
    names.save(texts)
    if state.set_names(texts["inputs"], time.ticks_ms()):
        pub.changed()
    vu.configure(texts["vu"])
    draw()


def status():
    return {"proxy": {"reads": bus.reads, "writes": bus.writes, "busy_high": busy_high},
            "vu": vu.status(time.ticks_ms()),
            "vu_glyphs": {name: list(g) for name, g in (("bars", vu_meter.GLYPHS),
                                                        ("deck", vu_meter.DECK_GLYPHS),
                                                        ("scale", vu_meter.SCALE_GLYPHS))}}


async def listen():
    global listen_ticks, busy_high, answered, amp_until
    quiet_since = time.ticks_us()
    clears = 0
    clears_seen = 0                     # o bus.clears na tela anterior
    while True:
        n = 0
        ms = time.ticks_ms()
        for word in sniffer.read():
            if word & RW:
                # Antes do primeiro "livre", o "ocupado" é só o Pico ainda ligando (o sniffer
                # começa uns ms antes do Responder). Depois, é falha do Responder: deve ficar em 0.
                if not word & D7:
                    answered = True
                elif answered:
                    busy_high += 1
            bus.feed(word)
            log.add(ms, word)
            n += 1
        log.poll(ms, n)
        listen_ticks += 1
        if bus.clears != clears:
            clears = bus.clears
            print("amp: power on (display reset)")
        now = time.ticks_us()
        if n:
            quiet_since = now
        quiet = time.ticks_diff(now, quiet_since) > QUIET_US
        if not n and bus.pending and quiet:
            screen = bus.take()
            amp_until = time.ticks_add(ms, AMP_HOLD_MS)
            draw()
            cleared, clears_seen = bus.clears != clears_seen, bus.clears
            if state.update(screen[0], screen[1], time.ticks_ms(), cleared):
                print("amp: %r | %r" % screen)
                pub.changed()
            log.screen(ms, state.screen != "unknown")
        elif not n and quiet and time.ticks_diff(ms, last_full) > REFRESH_MS:
            if vu_mode:
                show_vu(full=True)
            else:
                draw(full=True)
        # VU: só com música, quadros chegando, o display ligado e a tela do amp fora da vez.
        # Um erro no VU o desliga e mantém o display do amp: com o VU salvo ligado, um erro
        # que derrubasse o programa faria o Pico reiniciar sem parar.
        try:
            new_frame = vu.poll(ms)
            want_vu = vu.active(ms) and time.ticks_diff(ms, amp_until) >= 0 and bus.lcd.display_on
            if want_vu and not bus.pending and (new_frame or not vu_mode):
                show_vu()
            elif vu_mode and not want_vu:
                draw()
        except Exception as e:
            print("vu: turned off after an error:", repr(e))
            vu.error = repr(e)
            vu.on = False
            vu.close()
            draw(full=True)
        await asyncio.sleep_ms(1)


def wifi_result(ok, info):
    global wifi_ok
    wifi_ok = ok
    if not ok:
        print("Wi-Fi failed: offline mode")     # o display do amp não mostra avisos
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
    pub = Publisher(state, get_names=lambda: texts, set_names=set_texts, names_extra=status,
                    routes={"/update": ota.handle, "/bus": log.handle})
    log.clear(time.ticks_ms())
    asyncio.create_task(wifi_task(wifi_result))
    await asyncio.sleep(0.1)            # o Wi-Fi liga antes do servidor abrir o socket
    await pub.serve()                   # atende assim que houver rede
    asyncio.create_task(confirm_update())
    await listen()                      # a escuta começa na hora, com ou sem Wi-Fi


asyncio.run(main())
