"""Ler um socket UDP sem esperar, e sem erro quando a fila está vazia (vu.py, info.py).

O laço do proxy.py pergunta pelos pacotes umas 1000 vezes por segundo. Com o socket sem
espera, um recv() com a fila vazia levanta OSError: cada erro é um objeto novo na memória,
e o lixo faz o coletor rodar mais vezes (cada coleta para o laço por alguns ms). Com o
poll, só se chama o recv() quando há pacote.

    p = poller(sock)            # uma vez, ao abrir o socket
    while ready(p):
        data = sock.recv(...)   # ainda dentro de um try (o Wi-Fi pode cair no meio)
"""

try:
    import select
except ImportError:
    select = None


def poller(sock):
    """O poll do socket, ou None se não der (o socket de mentira dos testes)."""
    try:
        p = select.poll()
        p.register(sock, select.POLLIN)
        return p
    except Exception:
        return None


def ready(p):
    """Há pacote na fila? Sem poll, diz sempre que sim (o recv() decide, com erro)."""
    if p is None:
        return True
    for _ in p.ipoll(0):            # ipoll: o MicroPython não cria uma lista a cada chamada
        return True
    return False
