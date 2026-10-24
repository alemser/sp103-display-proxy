"""Roda sozinho toda vez que o Pico liga (o MicroPython executa o main.py ao ligar).

Hoje: a escuta do amp (escuta.py, etapa 4). A demonstração da bancada, com o amp de
mentira, continua disponível: .venv/bin/mpremote run firmware/bancada_wifi.py
Para parar e voltar ao computador, basta usar o mpremote: ele interrompe o programa
(Ctrl-C) antes de cada comando.
"""

import sys
import time
import machine

try:
    import escuta                   # noqa: F401  (o programa roda ao ser importado)
except Exception as e:
    # Qualquer erro (Wi-Fi fora do ar, por exemplo): mostra e tenta de novo em 30 s.
    sys.print_exception(e)
    try:
        from lcd1602 import Lcd1602
        Lcd1602().show("Error, rebooting", str(e)[:16])
    except Exception:
        pass
    time.sleep(30)
    machine.reset()
