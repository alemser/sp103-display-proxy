#!/usr/bin/env python3
"""Pede os quadros à ponte do VU como o Pico faz e diz o que chegou.

    python3 tools/vu_check.py IP
"""

import socket
import struct
import sys
import time

PORT = 7091
SUBSCRIBE = b"SUB2\x03"         # VU e telas
SECONDS = 6                     # a ponte manda as telas a cada 5 s, mesmo sem mudança


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip())
    host = sys.argv[1]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.2)
    sock.sendto(SUBSCRIBE, (host, PORT))
    frames = screens = 0
    flags = 0
    level = 0.0
    end = time.monotonic() + SECONDS
    while time.monotonic() < end:
        try:
            data = sock.recv(512)
        except TimeoutError:
            continue
        except OSError as e:
            sys.exit("%s: sem resposta (%s). A ponte está instalada?" % (host, e))
        if len(data) == 12 and data[:3] == b"VU\x01":
            _, _, flags, left, right = struct.unpack("<2sBBff", data)
            level = max(level, left, right)
            frames += 1
        elif data[:3] == b"NP\x01":
            screens += 1
    if not frames:
        sys.exit("%s: nenhum quadro em %d s. Veja se a ponte e o groove-detector estão rodando e se "
                 "o firewall da placa deixa passar a porta UDP %d." % (host, SECONDS, PORT))
    print("%s: %d quadros em %d s, %d pacotes das telas, nível máximo %.4f" % (host, frames, SECONDS, screens, level))
    print("gate: " + ("não lido" if not flags & 2 else "música" if flags & 1 else "sem música"))


if __name__ == "__main__":
    main()
