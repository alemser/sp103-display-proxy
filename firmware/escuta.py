"""Porta de entrada do programa: o main.py importa este arquivo ao ligar o Pico.

O main.py só se troca pelo cabo (ota.py), por isso o nome continua "escuta". Desde
2026-10-29 o display do amp está dessoldado nos pinos 4..14 e o programa é o proxy
(proxy.py, docs/proxy-ligacao.md). A escuta antiga, com o display ligado direto ao
controlador e a escrita sem corte (escrita.py, plano.py, refresh.py), está no
histórico do git (commit 45e782c).
"""

import proxy                            # noqa: F401  (o programa roda ao ser importado)
