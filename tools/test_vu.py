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
    c = {"on": True, "floor": -40, "relay": "192.168.178.105"}
    c.update(kw)
    return c


# --- names.py: a configuração do VU ---------------------------------------
default = names.validate({})["vu"]
check(default == {"on": False, "floor": -40, "relay": "192.168.178.105"}, "padrão: VU desligado, -40 dB")
check(names.validate({"vu": {"on": True, "floor": -30}})["vu"]["floor"] == -30, "piso configurável")
check(names.validate({"vu": {"on": True}})["inputs"] == {}, "só 'vu' não vira o formato antigo")
for bad, what in (({"floor": -60}, "piso fora da faixa"), ({"floor": "x"}, "piso não numérico"),
                  ({"on": "yes"}, "on não booleano"), ({"relay": "oceano-0001.local"}, "nome em vez de IP"),
                  ({"relay": "192.168.1.300"}, "IP inválido")):
    try:
        names.validate({"vu": bad})
        check(False, "recusa: " + what)
    except ValueError:
        check(True, "recusa: " + what)

# --- Meter: queda, pico, clip ---------------------------------------------
m = vu.Meter()
m.feed(-10, 46, 0)
check(m.level == -10 and m.peak == -10, "a barra sobe na hora")
m.feed(-40, 1000, 1000)
check(abs(m.level - (-36)) < 1e-6, "cai 26 dB/s (1 s: de -10 a -36)")
check(m.peak == -10, "o pico fica parado até 1,5 s")
m.feed(-40, 1000, 2000)
check(m.peak < -10, "depois de 1,5 s o pico começa a cair")
m.feed(-0.5, 46, 2046)
check(m.clip, "acima de -1 dBFS: clip")
m.feed(-30, 46, 3100)
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
check(len(vu.GLYPHS) == 64, "8 desenhos de 8 linhas")

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
