#!/usr/bin/env python3
"""Testa no computador o VU do display (firmware/vu.py) e a configuração dele (names.py).

Com um relógio e um socket de mentira: a queda da barra, o pico parado, o clip, o
desenho das duas linhas, o pedido ao relay e o "só com música".

    python3 tools/test_vu.py
"""

import os
import struct
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import time as real_time   # noqa: E402

fake_time = types.ModuleType("time")
for k in dir(real_time):
    if not k.startswith("__"):
        setattr(fake_time, k, getattr(real_time, k))
fake_time.ticks_add = lambda a, b: a + b
fake_time.ticks_diff = lambda a, b: a - b
sys.modules["time"] = fake_time

import names   # noqa: E402
import vu      # noqa: E402

sys.modules["time"] = real_time
fails = 0


def check(ok, what):
    global fails
    fails += not ok
    print("%-5s %s" % ("ok" if ok else "FALHA", what))


class FakeSocket:
    """O relay: guarda os pedidos e entrega os quadros da fila."""
    def __init__(self, *a):
        self.sent, self.queue, self.closed = [], [], False

    def setblocking(self, flag):
        pass

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recv(self, n):
        if not self.queue:
            raise OSError(11)           # EAGAIN, como o MicroPython sem dado
        return self.queue.pop(0)

    def close(self):
        self.closed = True


vu.socket = types.SimpleNamespace(socket=FakeSocket, AF_INET=2, SOCK_DGRAM=2)


def frame(l_db, r_db, music=True):
    rms = lambda d: 10 ** (d / 20)
    return struct.pack("<2sBBff", b"VU", 1, 3 if music else 2, rms(l_db), rms(r_db))


def cfg(**kw):
    c = {"on": True, "auto": False, "floor": -40, "top": 0, "relay": "192.168.178.105"}
    c.update(kw)
    return c


# --- names.py: a configuração do VU ---------------------------------------
default = names.validate({})["vu"]
check(default == {"on": False, "auto": True, "floor": -40, "top": 0, "relay": "192.168.178.105"},
      "padrão: VU desligado, escala automática")
check(names.validate({"vu": {"on": True, "floor": -30}})["vu"]["floor"] == -30, "piso configurável")
check(names.validate({"vu": {"on": True}})["inputs"] == {}, "só 'vu' não vira o formato antigo")
for bad, what in (({"floor": -70}, "piso fora da faixa"), ({"floor": "x"}, "piso não numérico"),
                  ({"on": "yes"}, "on não booleano"), ({"auto": 1}, "auto não booleano"), ({"relay": "oceano-0001.local"}, "nome em vez de IP"),
                  ({"relay": "192.168.1.300"}, "IP inválido")):
    try:
        names.validate({"vu": bad})
        check(False, "recusa: " + what)
    except ValueError:
        check(True, "recusa: " + what)

# --- Meter: queda, pico, clip ---------------------------------------------
m = vu.Meter()
m.feed(-10, 46, 0, 40)
check(m.level == -10 and m.peak == -10, "a barra sobe na hora")
m.feed(-60, 250, 250, 40)
check(abs(m.level - (-30)) < 1e-6, "escala de 40 dB: cai 80 dB/s (0,25 s: de -10 a -30)")
m.feed(-60, 250, 500, 40)
check(abs(m.level - (-50)) < 1e-6, "a barra cheia esvazia em 0,5 s")
check(m.peak == -10, "o pico fica parado até 1 s")
m.feed(-60, 500, 1500, 40)
check(abs(m.peak - (-30)) < 1e-6, "depois de 1 s o pico cai a escala inteira em 1 s")
m.feed(-0.5, 46, 2046, 40)
check(m.clip, "acima de -1 dBFS: clip")
m.feed(-30, 46, 3100, 40)
check(not m.clip, "o clip apaga depois de 1 s")

# --- Vu: linhas ---------------------------------------------------------------
v = vu.Vu()
v.configure(cfg())
v.L.level, v.L.peak = -20, -10        # metade da escala, pico a 3/4
v.R.level = v.R.peak = vu.SILENT_DB
l1, l2 = v.lines()
check(len(l1) == len(l2) == 16, "duas linhas de 16 células")
check(l1[0] == "L" and l2[0] == "R", "coluna 0: L e R")
px = v._px(-20)                       # 38 de 75 passos: 7 células cheias + 3 colunas
check(l1[1:8] == chr(vu.FULL) * 7 and l1[8] == chr(2), "-20 dB de -40: 7 cheias e uma de 3 colunas (%d px)" % px)
check(l1.index(chr(vu.PEAK)) == 1 + (v._px(-10) - 1) // 5, "a marca de pico na célula de -10 dB")
check(chr(vu.TICK) in l2 and chr(vu.FULL) not in l2, "canal mudo: só as marcas da escala")
v.configure(cfg(floor=-20))
check(v._px(-20) == 0 and v._px(0) == 75, "piso -20: a escala vai de -20 a 0")
check(all(c >= 0 for c in v._ticks) and len(v._ticks) == 3, "piso -20: só as marcas -10, -6 e -3")
v.configure(cfg(floor=-45, top=-20))
check(v._px(-45) == 0 and v._px(-20) == 75 and v._px(-10) == 75, "topo -20: a barra enche em -20 dBFS")
check(v._ticks == tuple((v._px(-20 + d) - 1) // 5 for d in (-20, -10, -6, -3)), "topo -20: marcas a -20..-3 dB do topo")
check(names.validate({"vu": {"floor": -45, "top": -20}})["vu"]["top"] == -20, "topo configurável")
check(names.validate({})["vu"]["top"] == 0, "topo padrão: 0 dBFS")
for bad in ({"top": 5}, {"top": -40}, {"floor": -25, "top": -20}, {"top": True}):
    try:
        names.validate({"vu": bad})
        check(False, "recusa %r" % bad)
    except ValueError:
        check(True, "recusa %r" % bad)
check(len(vu.GLYPHS) == 64, "8 desenhos de 8 linhas")

# --- Vu: escala automática ---------------------------------------------------
v = vu.Vu()
v.configure(cfg(auto=True, floor=-45, top=-20))
check((v.floor, v.top) == (-60, -40), "automática: começa embaixo e ignora piso e topo fixos")
ticks = v._ticks
v.poll(0)
v.sock.queue.append(frame(-11, -14))
v.poll(46)
check(abs(v.top - (-6)) < 1e-6 and abs(v.floor - (-26)) < 1e-6, "um quadro a -11 dB leva o topo a -6 na hora")
check(v._ticks == ticks and v._px(-11) < 75, "as marcas não mudam e a barra não enche")
t = 46
for _ in range(22):                    # 1 s de quadros a -30 dB
    t += 46
    v.sock.queue.append(frame(-30, -30))
    v.poll(t)
check(-7.2 < v.top < -6.8, "com música mais baixa, o topo desce 1 dB/s (%.2f)" % v.top)
v.sock.queue.append(frame(-50, -50, music=False))
v.poll(t + 46)
check(-7.2 < v.top < -6.8, "sem música, o topo fica parado")
v.sock.queue.append(frame(-90, -90))
for _ in range(300):                   # 60 s (cada quadro conta no máximo 200 ms)
    t += 1000
    v.sock.queue.append(frame(-90, -90))
    v.poll(t)
check(v.top == -40, "o topo não desce abaixo de -40 dB")
v.sock.queue.append(frame(5, 5))
v.poll(t + 46)
check(v.top == 0, "nem sobe acima de 0 dB")
check(v.status(t + 46)["top"] == 0 and v.status(t + 46)["auto"], "a página vê a escala de agora")

# --- Vu: pedido, quadros, música -----------------------------------------------
v = vu.Vu()
v.configure(cfg())
check(not v.poll(0) and v.sock.sent == [(b"SUB1", ("192.168.178.105", 7091))], "pede logo ao ligar")
v.poll(1000)
check(len(v.sock.sent) == 1, "não repete o pedido antes de 2 s")
v.poll(2000)
check(len(v.sock.sent) == 2, "repete o pedido a cada 2 s")
v.sock.queue += [frame(-12, -14), b"lixo", frame(-11, -13)]
check(v.poll(2046) and v.frames == 2, "lê os quadros da fila e ignora o lixo")
check(v.active(2046), "com música e quadros: VU ativo")
check(not v.active(3100), "sem quadros por 1 s: volta a tela do amp")
v.sock.queue.append(frame(-12, -14, music=False))
v.poll(3200)
check(not v.active(3200), "sem música: tela do amp")
sock = v.sock
v.configure(cfg(on=False))
check(sock.closed and not v.poll(4000) and not v.active(4000), "desligado: fecha e não pede mais")
v.configure(cfg(relay="192.168.178.99"))
v.poll(5000)
check(v.sock.sent[0][1] == ("192.168.178.99", 7091), "troca de placa: pede à nova")

print("\ntudo certo" if not fails else "\n%d falha(s)" % fails)
sys.exit(1 if fails else 0)
