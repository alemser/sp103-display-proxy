"""Roda sozinho toda vez que o Pico liga (o MicroPython executa o main.py ao ligar).

Hoje: a escuta do amp (escuta.py, etapa 4). A demonstração da bancada, com o amp de
mentira, continua disponível: .venv/bin/mpremote run firmware/bancada_wifi.py
Para parar e voltar ao computador, basta usar o mpremote: ele interrompe o programa
(Ctrl-C) antes de cada comando.

Atualização pelo Wi-Fi (ota.py, tools/enviar.py): este arquivo é o "porteiro" que
devolve a versão anterior se a nova falhar. Por isso ele NÃO usa nenhum outro
arquivo do projeto e só pode ser trocado pelo cabo USB (o ota.py recusa).

    update.json = {"state": "trial", "boots": 0}   versão nova, ainda em teste
    1º boot da versão nova: boots vira 1 e um relógio dá TRIAL_S segundos para o
       programa chamar ota.confirm() (state vira "ok"). Se não chamar, reinicia.
    Boot seguinte ainda em "trial" (travou, deu erro ou o relógio venceu): volta.
    "rollback" (pedido pela página ou pelo enviar.py): volta também.
Voltar = copiar de volta a pasta old/ (a versão anterior inteira, guardada pelo ota.py).
"""

import os
import sys
import json
import time
import machine

MARKER = "update.json"
OLD = "old"
TRIAL_S = 180               # tempo para a versão nova se mostrar saudável (ver escuta.py)
_timer = None


def _marker():
    try:
        with open(MARKER) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _save(m):
    with open(MARKER, "w") as f:
        json.dump(m, f)


def _restore():
    """Põe de volta a versão guardada em old/. Pode repetir sem estragar (se faltar luz no meio)."""
    old = os.listdir(OLD)
    for name in os.listdir():
        if name.endswith(".py") and name != "main.py" and name not in old:
            os.remove(name)                 # arquivo que só existia na versão nova
    buf = bytearray(1024)
    for name in old:
        with open(OLD + "/" + name, "rb") as src, open(name, "wb") as dst:
            while True:
                n = src.readinto(buf)
                if not n:
                    break
                dst.write(buf[:n])


def _check_update():
    global _timer                           # guardado aqui para o coletor de lixo não apagá-lo
    m = _marker()
    if not m:
        return
    if m["state"] == "rollback" or (m["state"] == "trial" and m.get("boots", 0) >= 1):
        why = "requested" if m["state"] == "rollback" else "the new version did not confirm"
        print("update: going back to the previous version (%s)" % why)
        _restore()
        _save({"state": "rolled_back", "why": why, "version": m.get("version")})
    elif m["state"] == "trial":
        m["boots"] = 1
        _save(m)
        print("update: new version on trial, %d s to confirm" % TRIAL_S)

        def deadline(t):
            if (_marker() or {}).get("state") == "trial":
                machine.reset()             # não confirmou: o próximo boot volta
        _timer = machine.Timer(period=TRIAL_S * 1000, mode=machine.Timer.ONE_SHOT,
                               callback=deadline)


try:
    _check_update()
except Exception as e:
    sys.print_exception(e)          # sem old/ ou flash com problema: segue com o que há

try:
    import escuta                   # noqa: F401  (o programa roda ao ser importado)
except Exception as e:
    # Qualquer erro (Wi-Fi fora do ar, por exemplo): mostra e tenta de novo em 30 s.
    # Numa versão em teste, esse reinício faz o _check_update() voltar à anterior.
    sys.print_exception(e)
    try:
        from lcd1602 import Lcd1602
        Lcd1602().show("Error, rebooting", str(e)[:16])
    except Exception:
        pass
    time.sleep(30)
    machine.reset()
