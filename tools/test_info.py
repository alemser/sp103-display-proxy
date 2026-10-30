#!/usr/bin/env python3
"""Testa no computador as telas de informação: firmware/info.py (o pacote "NP" e a conta
do tempo), firmware/screens.py (quem aparece e o texto) e a configuração (names.py "info").

    python3 tools/test_info.py
"""

import os
import sys
import time as real_time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

fake_time = types.ModuleType("time")
for k in dir(real_time):
    if not k.startswith("__"):
        setattr(fake_time, k, getattr(real_time, k))
fake_time.ticks_add = lambda a, b: a + b
fake_time.ticks_diff = lambda a, b: a - b
sys.modules["time"] = fake_time

import info      # noqa: E402
import names     # noqa: E402
import screens   # noqa: E402

sys.modules["time"] = real_time
fails = 0


def check(ok, what):
    global fails
    fails += not ok
    print("%-5s %s" % ("ok" if ok else "FALHA", what))


def packet(fields, playing=True, side_end=False):
    flags = (1 if playing else 0) | (2 if side_end else 0)
    return b"NP\x01" + bytes([flags]) + "\x1f".join(fields).encode()


def time_a4(elapsed, side_left, artist="Pink Floyd", title="Time", pos="A4", track="4"):
    return [artist, title, pos, str(elapsed), "421", "A", track, "5", str(side_left), "312", "62"]


def cfg(**kw):
    return names.validate({"info": dict({"on": True}, **kw)})["info"]


# --- info.py: o pacote e a conta do tempo -----------------------------------------
i = info.Info()
i.on = True
i.feed(packet(time_a4(161, 544)), 1000)
check(i.data["artist"] == "Pink Floyd" and i.data["position"] == "A4" and i.data["duration"] == 421,
      "lê os campos do pacote")
check(i.playing and not i.side_end and i.track_seq == 1, "tocando; uma faixa nova")
check(i.elapsed(1000) == 161 and i.elapsed(11500) == 171, "conta os segundos sozinho entre os pacotes")
check(i.side_left(11500) == 534, "e o tempo do lado também")
i.feed(packet(time_a4(172, 533)), 12000)
check(i.elapsed(12000) == 172 and i.track_seq == 1, "pacote de acordo (1 s de diferença): não pula, a mesma faixa")
check(i.data["side_left"] == 544, "  e fica com a conta dele")
i.feed(packet(time_a4(200, 505)), 13000)
check(i.elapsed(13000) == 200 and i.side_left(13000) == 505, "pacote 28 s à frente: corrige a conta")
i.feed(packet(time_a4(0, 284, title="The Great Gig In The Sky", pos="A5", track="5")), 14000)
check(i.track_seq == 2 and not i.side_start, "faixa nova no meio do lado")
i.feed(packet(time_a4(0, 900, title="Money", pos="B1", track="1")), 15000)
check(i.track_seq == 3 and i.side_start, "a primeira faixa do lado: começo do lado")
check(i.elapsed(15000 + 385000) == 385 and i.elapsed(15000 + 500000) == 421, "a posição não passa da duração")
i.feed(packet(["Pink Floyd", "", "", "", "", "A", "5", "5", "0", "312", "62"], playing=False, side_end=True), 16000)
check(not i.playing and i.side_end and i.data["title"] is None, "o lado acabou: campos vazios viram None")
check(i.elapsed(30000) is None and i.side_left(30000) == 0, "parado, o tempo não anda")
i.feed(packet(["x"]), 17000)
check(i.data["stylus_hours"] is None, "campos que faltam no fim: None")
i.feed(packet(time_a4(10, 20)[:9] + ["abc", "62"]), 17500)
check(i.side_left(17500) == 20, "o tempo do lado mudou muito: fica com o do pacote")
check(i.data["stylus_hours"] is None, "número estragado: None")
check(i.fresh(17500 + info.STALE_MS - 1) and not i.fresh(17500 + info.STALE_MS), "sem pacote por 15 s: não vale mais")


class FakeSock:
    def __init__(self, *a):
        self.sent, self.queue = [], []

    def setblocking(self, f):
        pass

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recv(self, n):
        if not self.queue:
            raise OSError(11)
        return self.queue.pop(0)

    def close(self):
        pass


info.socket = types.SimpleNamespace(socket=FakeSock, AF_INET=2, SOCK_DGRAM=2)
i = info.Info()
i.configure(True, "192.168.178.99")
check(not i.poll(0) and i.sock.sent == [(b"SUB2\x02", ("192.168.178.99", 7091))], "pede só as telas, à fonte")
i.sock.queue += [b"lixo", "NP\x01\x01Björk".encode("utf-8"), packet(time_a4(1, 2))]
check(i.poll(100) and i.packets == 1, "ignora lixo e pacote fora do ASCII")
i.configure(False, "192.168.178.99")
check(i.sock is None and not i.poll(200) and not i.fresh(200), "desligado: fecha e não pede")

# --- screens.py: textos ---------------------------------------------------------
check(screens.mmss(0) == "0:00" and screens.mmss(421) == "7:01", "minutos:segundos")
check(screens.lr("Side A", "track 4/5") == "Side A track 4/5", "esquerda e direita em 16")
long = "The Great Gig In The Sky"
check(screens.roll(long, 16, 0) == long[:16] and screens.roll(long, 16, 1999) == long[:16], "nome longo: parado 2 s")
check(screens.roll(long, 16, 2000 + 3 * screens.SCROLL_STEP_MS) == long[3:19], "depois anda uma letra por passo")
check(screens.roll("Time", 16, 99999) == "Time", "nome curto não anda")
check(screens.bar(0.62, 12) == chr(4) * 7 + chr(1) + " " * 4, "barra de 62 % em 12 células")
check(screens.bar(0, 4) == "    " and screens.bar(1.5, 2) == chr(4) * 2, "barra vazia e cheia")
check(screens._last_sunday(2026, 3) == 29 and screens._last_sunday(2026, 10) == 25, "últimos domingos de 2026")
check(screens._last_sunday(2027, 10) == 31, "outubro de 2027: o próprio dia 31")
check(screens.eu_summer((2026, 7, 1, 12)) and not screens.eu_summer((2026, 12, 1, 12)), "verão e inverno")
check(not screens.eu_summer((2026, 3, 29, 0)) and screens.eu_summer((2026, 3, 29, 1)), "muda à 1h UTC em março")
check(screens.eu_summer((2026, 10, 25, 0)) and not screens.eu_summer((2026, 10, 25, 1)), "e em outubro")


def make(**kw):
    i = info.Info()
    i.on = True
    s = screens.Screens(i)
    s.configure(cfg(**kw))
    return i, s


i, s = make(mode="fixed", fixed="side")
check(not s.vu_allowed(), "fixo: o VU não entra")
i.feed(packet(time_a4(161, 544)), 0)
check(s.pick(0, False, True) == "side", "fixo: a tela escolhida")
check(s.lines("side", 0) == ("Side A track 4/5", "Left        9:04"), "a tela do lado")
check(s.lines("pos", 1000) == ("A4 Time         ", "2:42/7:01  -4:19"), "a tela da faixa")
check(s.lines("track", 0) == ("Pink Floyd      ", "Time            "), "a tela de artista e música")
i.feed(packet(time_a4(161, 544, artist="Bob Marley & The Wailers", title="The Great Gig In The Sky")), 0)
moved = s.lines("track", 2000 + 4 * screens.SCROLL_STEP_MS)
check(moved == ("Bob Marley & The", "Great Gig In The"), "artista longo cortado; só a música rola: %r" % (moved,))
i.feed(packet(time_a4(161, 544)), 0)
check(s.lines("stylus", 0) == ("Stylus     312 h", chr(4) * 7 + chr(1) + "     62%"), "a tela da agulha")
i.feed(packet(time_a4(161, 544)[:5] + ["", "", "", "", "312", "62"]), 100)
check(s.pick(100, False, True) == "track", "fixo sem os dados do lado: artista e música")
i.feed(packet(time_a4(161, 50)), 200)
check(s.pick(200, False, True) == "alert", "último minuto do lado: o aviso")
check(s.lines("alert", 200) == ("End of side A   ", "Left        0:50"), "o aviso com o tempo")
i.feed(packet(["Pink Floyd", "", "", "", "", "A", "5", "5", "0", "312", "62"], playing=False, side_end=True), 300)
check(s.pick(300, False, True) == "alert", "o lado acabou: o aviso")
on, off = s.lines("alert", 300 + 200), s.lines("alert", 300 + 1200)
check(on[1] == "Flip the record " and off[1] == " " * 16, "\"Flip the record\" piscando")
s.configure(cfg(mode="fixed", alert=False))
check(s.pick(400, False, False) is None, "sem o aviso e sem tocar: a tela do amp")
check(s.pick(400, True, False) == "clock", "standby: o relógio")
s.configure(cfg(mode="fixed", clock=False))
check(s.pick(400, True, False) is None, "standby sem o relógio: a tela do amp")
check(s.pick(400 + info.STALE_MS, False, True) == "vu", "sem dados: o VU, se tiver música")

i, s = make(mode="temp", secs=8, show=["track", "side", "stylus"])
check(s.vu_allowed(), "temporário: o VU pode entrar")
i.feed(packet(time_a4(0, 900, title="Money", pos="B1", track="1")), 0)
seen = []
for t in range(0, 30000, 500):
    if t % 5000 == 0:                  # a fonte manda um pacote a cada 5 s
        i.feed(packet(time_a4(t // 1000, 900 - t // 1000, title="Money", pos="B1", track="1")), t)
    k = s.pick(t, False, True, "TUNER")
    if not seen or seen[-1] != k:
        seen.append(k)
check(seen == ["track", "side", "stylus", "vu"], "temporário, começo do lado: as marcadas, depois o VU: %s" % seen)
seen = []
for t in range(30000, 60000, 500):
    if t % 5000 == 0:
        i.feed(packet(time_a4(t // 1000 - 30, 630 - t // 1000, title="Us And Them", pos="B2", track="2")), t)
    k = s.pick(t, False, False)
    if not seen or seen[-1] != k:
        seen.append(k)
check(seen == ["track", "side", None], "faixa nova: sem a agulha; sem VU, a tela do amp: %s" % seen)
i.feed(packet(time_a4(0, 600, title="Any Colour You Like", pos="B3", track="3")[:5] + [""] * 6), 60000)
check(s.pick(60000, False, True) == "track" and s.pick(68000, False, True) == "vu",
      "uma tela sem dados é pulada")
i.feed(packet(time_a4(0, 600, title="Brain Damage", pos="B4", track="4")), 70000)
check(s.pick(70000, False, True) == "track", "faixa nova: recomeça")
i.feed(packet(time_a4(5, 600, title="Brain Damage", pos="B4", track="4")), 75000)
check(s.pick(75000, False, True) == "track", "o mesmo pacote de novo não recomeça a sequência")
check(s.pick(78000, False, True) == "side", "  e ela segue no tempo dela")
i, s = make(mode="temp", secs=8, show=["track", "stylus"])
i.feed(packet(time_a4(0, 900, title="Money", pos="B1", track="1")), 0)
check(s.pick(0, False, True, "CD") == "track" and s.pick(8000, False, True, "CD") == "vu",
      "agulha: numa entrada sem toca-discos (CD) a tela é pulada")
i, s = make(mode="fixed", fixed="stylus", turntable=["PHONO"])
i.feed(packet(time_a4(0, 900)), 0)
check(s.pick(0, False, True, "PHONO") == "stylus" and s.pick(100, False, True, "TUNER") == "track",
      "agulha fixa: só nas entradas marcadas; nas outras, artista e música")
check(cfg(turntable=["TUNER", "PHONO"])["turntable"] == ["PHONO", "TUNER"], "as entradas do toca-discos na ordem do amp")
s.configure(cfg(on=False))
check(s.pick(80000, False, True) == "vu" and s.pick(80000, True, False) is None, "telas desligadas: como antes")

# --- names.py: a configuração ------------------------------------------------------
d = names.validate({})["info"]
check(d == {"on": False, "mode": "temp", "fixed": "track", "show": ["track", "pos", "side", "stylus"], "secs": 8,
            "alert": True, "clock": True, "scroll": True, "utc_offset": 0, "eu_dst": True, "source": "",
            "turntable": ["PHONO", "TUNER"]},
      "padrão: desligadas")
check(names.INFO_KINDS == screens.KINDS, "names.py e screens.py conhecem as mesmas telas")
check(cfg(show=["stylus", "track"])["show"] == ["track", "stylus"], "as telas marcadas ficam na ordem certa")
check(cfg(utc_offset=5.5)["utc_offset"] == 5.5 and cfg(source=" 192.168.178.99 ")["source"] == "192.168.178.99",
      "fuso com meia hora; IP com espaços")
check(names.validate({"info": {"on": True}})["vu"]["on"] is False, "as telas não mexem no VU")
for bad in ({"mode": "always"}, {"fixed": "clock"}, {"show": ["track", "lyrics"]}, {"show": "track"},
            {"secs": 2}, {"secs": 8.5}, {"secs": True}, {"utc_offset": 15}, {"utc_offset": 1.1},
            {"source": "oceano.local"}, {"on": "yes"}, {"clock": 1}, {"turntable": ["RADIO"]}, {"turntable": "TUNER"}):
    try:
        names.validate({"info": bad})
        check(False, "recusa %r" % bad)
    except ValueError:
        check(True, "recusa %r" % bad)

print("\ntudo certo" if not fails else "\n%d falha(s)" % fails)
sys.exit(1 if fails else 0)
