"""Atualização do programa pelo Wi-Fi, com senha e volta automática.

No computador, quem usa isto é o tools/enviar.py. Os pedidos com senha levam o
cabeçalho "X-Password: <secrets.UPDATE_PASSWORD>" (sem essa linha no secrets.py,
a atualização fica desligada).

    GET  /update            estado: versão, arquivos (sha256), arquivos recebidos
    PUT  /update/<nome>.py  recebe um arquivo em new/ (confere a sintaxe)     [senha]
    DELETE /update/<nome>.py  marca o arquivo para apagar no próximo apply   [senha]
    POST /update/cancel     apaga o que foi recebido e não aplicado            [senha]
    POST /update/apply      guarda a versão atual em old/, aplica new/, reinicia [senha]

Apagar também passa pelo old/: se a versão nova falhar, o main.py traz o arquivo de volta.
    POST /update/rollback   volta para a versão de old/ e reinicia             [senha]

Depois do apply, a versão nova fica "em teste" (update.json, state "trial"). O
escuta.py chama confirm() quando ela se mostra saudável; se não chamar, o main.py
devolve a versão anterior (ver main.py, que só se troca pelo cabo).
"""

import os
import json
import hashlib
import asyncio
import machine
from binascii import hexlify

import secrets
from web import reply_json

MARKER = "update.json"          # os mesmos nomes do main.py
OLD = "old"
NEW = "new"
LOCKED = ("main.py", "secrets.py")   # só pelo cabo: o porteiro e as senhas
DELETE = ".del"                 # new/<nome>.py.del = apagar <nome>.py no apply


def _marker():
    try:
        with open(MARKER) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(m):
    with open(MARKER, "w") as f:
        json.dump(m, f)


def in_trial():
    return _marker().get("state") == "trial"


def confirm():
    """A versão nova funcionou: fica de vez (old/ continua guardando a anterior)."""
    m = _marker()
    if m.get("state") == "trial":
        m["state"] = "ok"
        _save(m)
        print("update: new version confirmed")


def _ls(folder=""):
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def _path(folder, name):
    return folder + "/" + name if folder else name


def _sha(path):
    h = hashlib.sha256()
    buf = bytearray(1024)
    with open(path, "rb") as f:
        while True:
            n = f.readinto(buf)
            if not n:
                break
            h.update(buf[:n])
    return hexlify(h.digest()).decode()


def _copy(src, dst):
    buf = bytearray(1024)
    with open(src, "rb") as a, open(dst, "wb") as b:
        while True:
            n = a.readinto(buf)
            if not n:
                break
            b.write(buf[:n])


def _clear(folder):
    for name in _ls(folder):
        os.remove(_path(folder, name))
    if folder not in os.listdir():
        os.mkdir(folder)


def _program(folder=""):
    """Os arquivos do programa numa pasta (o secrets.py fica de fora: tem senhas)."""
    return [n for n in _ls(folder) if n.endswith(".py") and n != "secrets.py"]


def _files(folder=""):
    return {name: _sha(_path(folder, name)) for name in _program(folder)}


def version(files):
    """Um código curto que muda sempre que algum arquivo do programa muda (fora o main.py,
    que não vai para old/, para a versão anterior guardada ter o mesmo código de antes)."""
    h = hashlib.sha256()
    for name in sorted(files):
        if name in LOCKED:
            continue
        h.update((name + files[name]).encode())
    return hexlify(h.digest()).decode()[:8]


def status():
    m = _marker()
    files = _files()
    return {"version": version(files), "state": m.get("state", "ok"), "why": m.get("why"),
            "previous": version(_files(OLD)) if _ls(OLD) else None, "files": files,
            "staged": _ls(NEW), "enabled": hasattr(secrets, "UPDATE_PASSWORD"), "can_delete": True}


def _valid_name(name):
    base = name[:-3]
    return (name.endswith(".py") and 0 < len(base) <= 32 and name not in LOCKED
            and all(c.isalpha() or c.isdigit() or c == "_" for c in base))


async def _discard(req):
    """Lê e joga fora o corpo do pedido: respondendo sem ler, a conexão cai e o
    computador não vê a mensagem de erro."""
    left = req.length
    while left > 0:
        chunk = await req.reader.read(min(1024, left))
        if not chunk:
            break
        left -= len(chunk)


async def _stage(req, name):
    """Recebe um arquivo em new/ e confere se o MicroPython consegue ler o código."""
    if not _valid_name(name):
        await _discard(req)
        raise ValueError("%s cannot be updated over Wi-Fi" % name)
    if NEW not in os.listdir():
        os.mkdir(NEW)
    path = _path(NEW, name)
    left = req.length
    with open(path, "wb") as f:
        while left > 0:
            chunk = await req.reader.read(min(1024, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    if left:
        os.remove(path)
        raise ValueError("%s arrived incomplete" % name)
    try:
        with open(path) as f:
            compile(f.read(), name, "exec")
    except SyntaxError as e:
        os.remove(path)
        raise ValueError("%s: syntax error: %s" % (name, e))
    return _sha(path)


def _stage_delete(name):
    """Marca um arquivo do programa para apagar no próximo apply."""
    if not _valid_name(name):
        raise ValueError("%s cannot be deleted over Wi-Fi" % name)
    if name not in _program():
        raise ValueError("%s is not on the Pico" % name)
    if NEW not in os.listdir():
        os.mkdir(NEW)
    open(_path(NEW, name + DELETE), "wb").close()


def _apply():
    staged = _ls(NEW)
    if not staged:
        raise ValueError("nothing to apply: send the files first")
    if in_trial():
        raise ValueError("the last update is still on trial; wait for it to confirm")
    # 1. A versão atual inteira vai para old/ (o main.py volta para ela se a nova falhar).
    _clear(OLD)
    for name in _ls():
        if name.endswith(".py") and name != "main.py":
            _copy(name, _path(OLD, name))
    # 2. Marca "em teste" ANTES de trocar: se faltar luz no meio, o main.py volta.
    _save({"state": "trial", "boots": 0, "files": staged})
    # 3. Troca (ou apaga) os arquivos.
    for name in staged:
        target = name[:-len(DELETE)] if name.endswith(DELETE) else name
        if target in os.listdir():
            os.remove(target)
        if target == name:
            os.rename(_path(NEW, name), name)
        else:
            os.remove(_path(NEW, name))
    m = _marker()
    m["version"] = version(_files())
    _save(m)
    return m


async def _reset_soon():
    await asyncio.sleep(1)              # dá tempo da resposta chegar ao computador
    machine.reset()


async def handle(req, writer):
    """Rota /update (ver web.Publisher)."""
    if req.method == "GET" and req.path == "/update":
        return await reply_json(writer, status())
    password = getattr(secrets, "UPDATE_PASSWORD", None)
    if not password or req.headers.get("x-password") != password:
        await _discard(req)
    if not password:
        return await reply_json(writer, {"error": "updates are off: no UPDATE_PASSWORD in secrets.py"},
                                "403 Forbidden")
    if req.headers.get("x-password") != password:
        await asyncio.sleep(1)          # atrasa quem tenta adivinhar a senha
        return await reply_json(writer, {"error": "wrong password"}, "403 Forbidden")
    action = req.path[len("/update/"):]
    try:
        if req.method == "PUT":
            answer = {"file": action, "sha256": await _stage(req, action)}
        elif req.method == "DELETE":
            _stage_delete(action)
            answer = {"file": action, "delete": True}
        elif req.method == "POST" and action == "cancel":
            _clear(NEW)
            answer = {"staged": []}
        elif req.method == "POST" and action == "apply":
            answer = _apply()
            print("update: applied %s, restarting" % answer["files"])
            asyncio.create_task(_reset_soon())
        elif req.method == "POST" and action == "rollback":
            if not _ls(OLD):
                raise ValueError("there is no previous version saved")
            _save({"state": "rollback"})
            print("update: rollback requested, restarting")
            asyncio.create_task(_reset_soon())
            answer = {"state": "rollback"}
        else:
            return await reply_json(writer, {"error": "unknown request"}, "404 Not Found")
    except (ValueError, OSError) as e:
        return await reply_json(writer, {"error": str(e)}, "400 Bad Request")
    await reply_json(writer, answer)
