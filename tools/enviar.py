#!/usr/bin/env python3
"""Envia o programa novo para o Pico pelo Wi-Fi (firmware/ota.py) e acompanha até ele confirmar.

    python3 tools/enviar.py                    # envia o que mudou em firmware/ e aplica
    python3 tools/enviar.py escuta.py web.py   # só esses arquivos (se mudaram)
    python3 tools/enviar.py --estado           # só mostra a versão e o estado do Pico
    python3 tools/enviar.py --voltar           # volta para a versão anterior (guardada no Pico)

Opções: --host (padrão sp103.local, ou a variável SP103_HOST) e --forcar (envia mesmo sem mudança).
A senha vem do UPDATE_PASSWORD de firmware/secrets.py (ou da variável SP103_PASSWORD).

Nunca envia main.py nem secrets.py: esses só pelo cabo, com o mpremote.
"""

import argparse
import glob
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FIRMWARE = os.path.join(HERE, "..", "firmware")
LOCKED = ("main.py", "secrets.py")
TRIAL_S = 180                   # o mesmo do main.py
WAIT_S = TRIAL_S + 90           # reinício + Wi-Fi + teste


def password():
    if os.environ.get("SP103_PASSWORD"):
        return os.environ["SP103_PASSWORD"]
    values = {}
    try:
        with open(os.path.join(FIRMWARE, "secrets.py")) as f:
            exec(f.read(), values)
    except OSError:
        pass
    if not values.get("UPDATE_PASSWORD"):
        sys.exit("Falta a senha: ponha UPDATE_PASSWORD = \"...\" em firmware/secrets.py "
                 "(e o mesmo secrets.py no Pico, pelo cabo).")
    return values["UPDATE_PASSWORD"]


def request(host, method, path, body=None, pw=None, timeout=10):
    req = urllib.request.Request("http://%s%s" % (host, path), data=body, method=method)
    if pw:
        req.add_header("X-Password", pw)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", e.reason)
        except (ValueError, OSError):   # o Pico responde antes de ler tudo e fecha a conexão
            msg = e.reason
        sys.exit("O Pico recusou (%d): %s" % (e.code, msg))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def version(files):
    """O mesmo código de versão do ota.version()."""
    h = hashlib.sha256()
    for name in sorted(files):
        if name in LOCKED:
            continue
        h.update((name + files[name]).encode())
    return h.hexdigest()[:8]


def show(st):
    print("Versão no Pico: %s   estado: %s%s" % (
        st["version"], st["state"], "  (%s)" % st["why"] if st.get("why") else ""))
    print("Versão anterior guardada: %s" % (st["previous"] or "nenhuma"))
    if not st["enabled"]:
        print("A atualização pelo Wi-Fi está DESLIGADA: falta UPDATE_PASSWORD no secrets.py do Pico.")


def local_files(names):
    paths = [os.path.join(FIRMWARE, n) for n in names] if names else \
        sorted(glob.glob(os.path.join(FIRMWARE, "*.py")))
    out = {}
    for path in paths:
        name = os.path.basename(path)
        if not name[:-3].replace("_", "").isalnum():
            continue                        # secrets.example.py e afins: não são do programa
        if name in LOCKED:
            if names:
                print("%s fica de fora: só pelo cabo (.venv/bin/mpremote cp firmware/%s :%s)" % (
                    name, name, name))
            continue
        with open(path, "rb") as f:
            data = f.read()
        try:
            compile(data, name, "exec")     # erro de digitação: melhor descobrir aqui
        except SyntaxError as e:
            sys.exit("Erro de sintaxe em %s, linha %s: %s" % (name, e.lineno, e.msg))
        out[name] = data
    return out


def wait(host, expected, started):
    """Acompanha o reinício e o teste da versão nova, até confirmar ou voltar."""
    last = None
    while time.time() - started < WAIT_S:
        time.sleep(2)
        try:
            st = request(host, "GET", "/update", timeout=5)
        except (OSError, urllib.error.URLError):
            msg = "Pico reiniciando (ainda sem resposta)..."
        else:
            if st["state"] == "ok" and st["version"] == expected:
                print("\nPronto: versão %s confirmada. A anterior (%s) fica guardada no Pico." % (
                    expected, st["previous"]))
                return True
            if st["state"] == "rolled_back":
                print("\nA versão nova FALHOU e o Pico voltou para a anterior (%s): %s." % (
                    st["version"], st["why"]))
                print("Veja o erro pelo cabo: .venv/bin/mpremote (o Pico mostra o erro ao ligar).")
                return False
            if st["state"] == "trial":
                msg = "Versão %s em teste (o Pico confirma depois de 20 s funcionando)..." % st["version"]
            else:
                msg = "Estado: %s, versão %s" % (st["state"], st["version"])
        if msg != last:
            print("  %3d s  %s" % (time.time() - started, msg))
            last = msg
    print("\nO Pico não confirmou em %d s. Ele volta sozinho para a versão anterior;" % WAIT_S)
    print("confira com: python3 tools/enviar.py --estado")
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="arquivos de firmware/ (padrão: todos os .py)")
    ap.add_argument("--host", default=os.environ.get("SP103_HOST", "sp103.local"))
    ap.add_argument("--estado", action="store_true", help="só mostra o estado")
    ap.add_argument("--voltar", action="store_true", help="volta para a versão anterior")
    ap.add_argument("--forcar", action="store_true", help="envia mesmo os arquivos sem mudança")
    args = ap.parse_args()
    host = args.host

    try:
        st = request(host, "GET", "/update")
    except (OSError, urllib.error.URLError) as e:
        sys.exit("Não achei o Pico em %s (%s). Ele está ligado e no Wi-Fi? "
                 "Tente --host com o IP." % (host, getattr(e, "reason", e)))
    show(st)
    if args.estado:
        return

    pw = password()
    if args.voltar:
        if not st["previous"]:
            sys.exit("Não há versão anterior guardada no Pico.")
        if st["previous"] == st["version"]:
            sys.exit("O Pico já está na versão guardada (%s): não há para onde voltar." % st["version"])
        request(host, "POST", "/update/rollback", b"", pw)
        print("Voltando para a versão %s..." % st["previous"])
        started = time.time()
        while time.time() - started < 60:
            time.sleep(2)
            try:
                st = request(host, "GET", "/update", timeout=5)
            except (OSError, urllib.error.URLError):
                continue
            if st["state"] == "rolled_back":
                print("Pronto: o Pico está na versão %s." % st["version"])
                return
        sys.exit("O Pico não respondeu em 60 s.")

    if st["state"] == "trial":
        sys.exit("A última atualização ainda está em teste. Espere uns minutos e tente de novo.")

    files = local_files(args.files)
    if not args.files:
        with open(os.path.join(FIRMWARE, "main.py"), "rb") as f:
            if sha(f.read()) != st["files"].get("main.py"):
                print("Aviso: o main.py do Pico é diferente do firmware/main.py. Ele não vai pelo "
                      "Wi-Fi;\n       se precisar, pelo cabo: .venv/bin/mpremote cp firmware/main.py :main.py")
    send = {n: d for n, d in files.items() if args.forcar or sha(d) != st["files"].get(n)}
    if not send:
        print("Nada mudou: o Pico já tem esses arquivos.")
        return

    print("\nEnviando %d arquivo(s):" % len(send))
    request(host, "POST", "/update/cancel", b"", pw)
    for name, data in send.items():
        got = request(host, "PUT", "/update/" + name, data, pw, timeout=30)
        if got["sha256"] != sha(data):
            sys.exit("%s chegou diferente; nada foi aplicado. Tente de novo." % name)
        print("  %-20s %6d bytes  ok" % (name, len(data)))

    expected = dict(st["files"])
    expected.update({n: sha(d) for n, d in send.items()})
    expected = version(expected)
    request(host, "POST", "/update/apply", b"", pw)
    print("\nAplicado. Versão nova: %s. O Pico reinicia e testa a versão nova:" % expected)
    sys.exit(0 if wait(host, expected, time.time()) else 1)


if __name__ == "__main__":
    main()
