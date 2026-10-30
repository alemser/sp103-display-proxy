"""Etapa 6: o Pico no meio, entre o controlador do amp e o display (opção 3b).

O display do amp foi dessoldado nos pinos 4..14 (docs/proxy-ligacao.md):
- lado do controlador: GP2..GP12 (E, RS, RW, D0..D7), como na escuta. O Pico só lê
  (sniffer.py) e responde "livre" às leituras do busy flag (busy.py), puxando o D7 para 0;
- lado do display: GP16..21 (RS, E, D4..D7), modo 4 bits, RW do display no GND (lcd1602.py).

Cada tela completa do controlador é reconstruída (hd44780.py), vai para o leitor
(amp_state) e é desenhada no display do amp já com os textos personalizados
(names.rewrite). Os desenhos próprios (CGRAM) e o "display on/off" seguem os do controlador.

Com o VU ligado na página (vu.py), as duas linhas viram as barras L e R enquanto houver
música; cada redesenho do controlador traz a tela do amp de volta por 3 s. Com as telas de
informação ligadas (info.py recebe, screens.py escolhe), o display mostra também o que
está tocando, o fim do lado, a agulha e o relógio no standby.

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

import info as info_feed
import names
import ota
import screens as screens_mod
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
PICK_MS = 100                           # escolhe a tela no máximo a cada 100 ms (ou a cada quadro/pacote)
OWN_REDRAW_MS = 250                     # uma tela de informação é recalculada a cada 250 ms (relógios, rolagem)
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
info = info_feed.Info()
screens = screens_mod.Screens(info)
own = None                              # a tela própria no display ("vu", "track"...); None = a do amp
own_at = time.ticks_ms()                # quando ela foi desenhada
amp_until = time.ticks_ms()             # até aqui, a tela do amp tem a vez


def configure_feeds(cfg):
    """Aplica as configurações do VU e das telas. No modo fixo o VU nem pede quadros."""
    screens.configure(cfg["info"])
    vu_cfg = dict(cfg["vu"])
    vu_cfg["on"] = vu_cfg["on"] and screens.vu_allowed()
    vu.configure(vu_cfg)
    info.configure(cfg["info"]["on"], cfg["info"]["source"] or cfg["vu"]["relay"])


configure_feeds(texts)


def draw(full=False):
    """Põe no display do amp a tela do controlador, com os textos personalizados.
    Só manda o que mudou; full=True resincroniza e reescreve tudo (sem apagar a tela)."""
    global shown_cgram, shown_on, last_full, own
    own = None
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


def show_own(key, ms, full=False):
    """Põe no display uma tela própria: o VU ou uma tela de informação. Os desenhos dela
    tomam o lugar dos do controlador; o draw() seguinte grava os do controlador de volta
    (o shown_cgram muda). Só manda as linhas que mudaram."""
    global shown_cgram, last_full, own, own_at
    own, own_at = key, ms
    if full:
        lcd.resync()
        shown[0] = shown[1] = shown_cgram = None
        last_full = time.ticks_ms()
    glyphs = vu.glyphs if key == "vu" else screens_mod.GLYPHS
    if shown_cgram != glyphs:
        for code in range(8):
            lcd.define_char(code, glyphs[8 * code:8 * code + 8])
        shown_cgram = glyphs
    lines = vu.lines() if key == "vu" else screens.lines(key, ms)
    for row, text in enumerate(lines):
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
    configure_feeds(texts)
    draw()


def status():
    ms = time.ticks_ms()
    return {"proxy": {"reads": bus.reads, "writes": bus.writes, "busy_high": busy_high},
            "vu": vu.status(ms), "info": info.status(ms), "screens": screens.status(ms),
            "vu_glyphs": {name: list(g) for name, g in (("bars", vu_meter.GLYPHS),
                                                        ("deck", vu_meter.DECK_GLYPHS),
                                                        ("scale", vu_meter.SCALE_GLYPHS),
                                                        ("kx393", vu_meter.KX_GLYPHS))}}


async def listen():
    global listen_ticks, busy_high, answered, amp_until
    quiet_since = time.ticks_us()
    picked_at = time.ticks_ms()
    key = None
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
            if own:
                show_own(own, ms, full=True)
            else:
                draw(full=True)
        # Telas próprias (VU e informação): só com o display ligado e a tela do amp fora da
        # vez. A escolha é barata, mas roda no máximo a cada PICK_MS, ou quando chega um
        # quadro do VU ou um pacote das telas. Um erro aqui desliga o VU e as telas e mantém
        # o display do amp: com eles salvos ligados, um erro que derrubasse o programa faria
        # o Pico reiniciar sem parar.
        try:
            new_frame = vu.poll(ms)
            new_info = info.poll(ms)
            if time.ticks_diff(ms, amp_until) < 0 or not bus.lcd.display_on:
                key = None                  # a tela do amp tem a vez (conferido a cada volta)
                picked_at = time.ticks_add(ms, -PICK_MS)   # escolhe logo que ela sair
            elif new_frame or new_info or time.ticks_diff(ms, picked_at) >= PICK_MS:
                picked_at = ms
                key = screens.pick(ms, state.power == "standby", vu.active(ms), state.input)
            if key and not bus.pending:
                if key == "vu":
                    if new_frame or own != "vu":
                        show_own("vu", ms)
                elif key != own or new_info or time.ticks_diff(ms, own_at) >= OWN_REDRAW_MS:
                    show_own(key, ms)
            elif own and not key:
                draw()
        except Exception as e:
            print("screens: turned off after an error:", repr(e))
            vu.error = screens.error = repr(e)
            vu.on = False
            vu.close()
            info.configure(False, "0.0.0.0")
            off = dict(screens.cfg)
            off["on"] = False
            screens.cfg = off
            key = None
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
