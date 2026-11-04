"""Quem pode ficar ligado no /events: uma conexão por IP, e poucas no total.

Uma conexão morta (celular que perdeu o Wi-Fi) só some depois de minutos, e cada uma prende
memória do lwIP e recebe escritas. Com 4 mortas ao mesmo tempo o servidor parou de vez
(issue #2). Um cliente que reconecta vem do mesmo IP: a conexão nova toma o lugar da antiga.
O teto só age com clientes demais, e aí sai o mais antigo.

Roda igual no MicroPython (Pico) e no Python do computador (tools/test_listeners.py).
"""

MAX_LISTENERS = 3


def make_room(listeners, ip, limit=MAX_LISTENERS):
    """Abre lugar para uma conexão nova de ip. listeners: [(ip, writer)], a mais antiga primeiro.
    Quem sai da lista percebe sozinho e fecha (web.py): nada escreve mais nela."""
    for entry in [e for e in listeners if ip is not None and e[0] == ip]:
        listeners.remove(entry)
    while len(listeners) >= limit:
        listeners.pop(0)
