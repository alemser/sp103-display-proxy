# Proxy: o Pico no meio, entre o controlador e o display (opção 3b)

Montado em 2026-10-29. O display do amp foi dessoldado. Os pinos 1–3, 15 e 16 voltaram a ser soldados na placa; nos
furos 4–14 da placa de baixo há fios novos (lado do controlador). Os fios antigos, soldados nas pontas de cima dos
pinos do display, são o lado do display. Programa: `firmware/proxy.py` (o `escuta.py` só o importa).

## Conferir o corte (multímetro em continuidade, amp fora da tomada)

- Fio de baixo do furo N × pino N do display (em cima), N = 4…14: **não apita**.
- Pino 1 do display × GND da placa, e pino 2 × +5 V: **apita**.

## Lado do controlador: fios de baixo → Pico (iguais aos da escuta)

| Furo na placa | Sinal | Pico | Pino físico |
|---|---|---|---|
| 4 | RS | GP3 | 5 |
| 5 | RW | GP4 | 6 |
| 6 | E | GP2 | 4 |
| 7–14 | D0–D7 | GP5–GP12 | 7, 9, 10, 11, 12, 14, 15, 16 |

O Pico só lê esses fios, com uma exceção: nas leituras do busy flag ele puxa o D7 (GP12) para 0 = "livre"
(`firmware/busy.py`). Nunca põe 1 em GP2–GP12.

## Lado do display: fios de cima → Pico

| Pino do display | Sinal | Fio | Liga em | Pino físico |
|---|---|---|---|---|
| 1 | GND | preto | GND | 3 (como antes) |
| 2 | +5 V | vermelho | VSYS | 39 (como antes; nunca o 40) |
| 4 | RS | amarelo | GP16 | 21 |
| 5 | RW | laranja | **GND** | 23 |
| 6 | E | marrom | GP17 | 22 |
| 7–10 | D0–D3 | verde, branco, cinza, roxo | nada (pontas isoladas) | — |
| 11 | D4 | azul | GP18 | 24 |
| 12 | D5 | branco | GP19 | 25 |
| 13 | D6 | cinza | GP20 | 26 |
| 14 | D7 | roxo | GP21 | 27 |

Contraste (3) e luz de fundo (15, 16) continuam vindo da placa do amp.

## Sem o Pico

O controlador pergunta "ocupado?" antes de cada letra e, sem resposta, pergunta para sempre. Sem o Pico, o amp não
atualiza o display. Para voltar ao original: ligue cada fio de baixo ao fio de cima do mesmo número (11 jumpers).

## Instalar o programa (pelo Wi-Fi)

1. Faça a ligação acima e ligue o amp na tomada. O Pico ainda tem a versão antiga: o display deve mostrar
   `SP103 listener` / `waiting for amp`. Isso prova que o lado do display está certo.
2. No computador: `python3 tools/enviar.py`. Ele envia os arquivos que mudaram, aplica e espera a confirmação.
3. Gire o volume e troque de entrada. Os nomes da página aparecem inteiros no display do amp.
4. Em `http://sp103.local/names`, o campo `proxy.busy_high` deve ficar em 0 (leituras em que o controlador viu
   "ocupado").

Se a versão nova falhar, o `main.py` volta sozinho para a anterior.
