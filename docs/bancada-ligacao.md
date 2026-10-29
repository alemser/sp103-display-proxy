# Bancada: ligação do display reserva (1602 azul) ao Pico 2 W

> Os GP16–21 são os mesmos que hoje desenham no display do amp (`proxy-ligacao.md`). Na bancada, o display reserva
> ocupa esse lugar, alimentado pelo USB.

Modo de **4 bits**, com o **RW ligado ao GND**: o Pico só escreve e nunca lê. Assim o display nunca manda 5 V de volta
ao Pico, e os conversores de nível não são necessários. Os pinos GP2–GP12 ficam livres para o lado do controlador.

Pino 1 do Pico: o canto ao lado do USB. Os pinos 1–20 ficam numa fileira e os 21–40 na outra
(o 40 fica de frente para o 1, também ao lado do USB).

| Pino do display | Nome no display | Pino físico do Pico | Nome no Pico | Observação |
|---|---|---|---|---|
| 1 | GND | 3 | GND | |
| 2 | VDD | **40** | VBUS (5 V do USB) | ⚠️ confira duas vezes: nunca num GPIO |
| 3 | VO | 8 | GND | ligado direto ao GND = contraste máximo (funciona bem neste display azul); trimpot opcional |
| 4 | RS | 21 | GP16 | |
| 5 | RW | 23 | GND | fixo em 0 = só escrita |
| 6 | E | 22 | GP17 | |
| 7 | D0 | — | — | livre |
| 8 | D1 | — | — | livre |
| 9 | D2 | — | — | livre |
| 10 | D3 | — | — | livre |
| 11 | D4 | 24 | GP18 | |
| 12 | D5 | 25 | GP19 | |
| 13 | D6 | 26 | GP20 | |
| 14 | D7 | 27 | GP21 | |
| 15 | BLA (luz +) | 36 | 3V3 | começar em 3,3 V; se ficar fraco, mudamos |
| 16 | BLK (luz −) | 28 | GND | |

## Trimpot (contraste, opcional)

Na bancada (2026-10-23) o VO foi ligado direto ao GND (pino 8 do Pico) e o texto ficou bom.
Para ajustar o contraste, use o trimpot como resistor variável: perna do meio no VO, uma ponta num GND livre
(8, 13, 18 ou 33) e a outra ponta solta. Ou faça o divisor completo abaixo.

| Perna do trimpot | Liga em |
|---|---|
| ponta 1 | pino 40 do Pico (VBUS, 5 V) |
| meio | VO (pino 3 do display) |
| ponta 2 | pino 38 do Pico (GND) |

Com o display ligado, gire o trimpot até aparecer uma fileira de quadradinhos na linha 1 (display ainda sem
inicializar). Depois volte um pouco, até os quadradinhos ficarem fracos.

## Antes de ligar o USB

- [ ] O VDD está no pino **40** (e não no 39, VSYS, nem num GPIO).
- [ ] Nenhum fio descascado encosta no vizinho.
- [ ] O jumper entre os pinos 1 e 2 do Pico foi retirado (era só para o analisador).

## Resultado (2026-10-23)

Funcionou de primeira com os sinais de 3,3 V do Pico, sem conversor de nível.
Sem nada no VO a tela fica azul e vazia: o VO precisa ir ao GND (ou ao trimpot).
Programa de teste: `firmware/demo_telas.py` (ver instruções no próprio arquivo).
