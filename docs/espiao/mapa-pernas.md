# Mapa das pernas do T9311DP

Medições com multímetro, com o amp fora da tomada. Guia e regras de segurança: `BRIEF-espiao-controlador.md`.

## Contagem das pernas (2026-11-05)

Confirmada. Visto por cima, com o LCD à esquerda:

| Perna | Posição | Medição | Resultado |
|---|---|---|---|
| 20 | última à direita, fileira de baixo | × pino 1 do display (GND) | apita |
| 40 | primeira à esquerda, fileira de cima | × pino 2 do display (+5 V) | apita |

## Receptor IR (2026-11-05)

Visto por cima, com o LCD à esquerda e os botões perto de quem olha:

| Ponto | Função | Medição | Resultado |
|---|---|---|---|
| Perna da esquerda | Sinal | × perna 12 do chip | apita (ligação direta) |
| Perna do meio | GND | × GND | apita |
| Perna da direita | Alimentação | × C903 | apita |
| Perna da direita | Alimentação | × perna 40 (+5 V) | cerca de 10 Ω |
| Carcaça | GND | × pino 1 do display | apita |
| C902, terminal de cima | GND | × perna do meio do IR | apita |
| C902, terminal de cima | GND | × perna da esquerda do IR | não apita |
| C902, terminal de baixo | Sinal | × perna do meio do IR | não apita |
| C902, terminal de baixo | Sinal | × perna da esquerda do IR | apita |

Os 10 Ω vêm de 10,5 Ω medidos na escala 200, menos 0,6 Ω dos cabos do multímetro.

**Conclusões:**

- A saída do receptor IR vai direto à perna 12 do chip. Nenhuma outra apitou entre as pernas 1–8, 13–17 e 21–27.
- O C902 (33 pF) fica entre o sinal e o GND.
- Se o chip for um 8051, a perna 12 é P3.2/INT0, a entrada de interrupção. A família do chip ainda não foi confirmada.

**Força da linha do IR (2026-11-06):** em Ω, escala 200k, amp fora da tomada, entre a perna da esquerda (sinal) e a da direita (alimentação): 39,0 kΩ com a ponta vermelha no sinal e 41,1 kΩ com as pontas invertidas. Quase igual nos dois sentidos, então é um resistor de cerca de 40 kΩ segurando a linha em 1. Puxar a linha para o GND custa cerca de 0,1 mA.

**Em aberto:**

- Confirmar se o resistor de cerca de 10 Ω é mesmo o R903.

## Encoder do volume (2026-11-05)

Pinos vistos por baixo, com a ponta do LCD para cima: E1 é o de cima, E2 o do meio e E3 o de baixo.

| Ponto | Função | Liga em | Resistor para o +5 V (perna 40) |
|---|---|---|---|
| E1 | A ou B | **Perna 22 do chip**, direto | 4,6 kΩ |
| E2 | A ou B | **Perna 21 do chip**, direto | 4,6 kΩ |
| E3 | Comum | GND (apita em todas as posições) | 4,76 kΩ (é a leitura entre +5 V e GND) |
| 2 patilhas de fixação | Só fixação | Não apitam com o GND | não medido |

Conferência em continuidade: E1 × 22 e E2 × 21 apitam; E1 × 21 e E2 × 22 não apitam. As mesmas ligações em Ω foram anotadas como "nada" e devem ser 0.00, porque apitam.

**Conclusões:**

- O C908 fica entre E2 e o GND.
- E1 e E2 têm resistor de cerca de 4,6 kΩ para o +5 V, e o contato do encoder os puxa para o GND.
- As leituras de 9,2 kΩ são dois desses resistores em série, passando pelo +5 V. Não são ligações diretas.
- Se o chip for um 8051, as pernas 21 e 22 são P2.0 e P2.1. A família do chip ainda não foi confirmada.
- Na primeira varredura, 21 e 22 não apitaram, e uma leitura do E2 falhou por falta de contato. Encostar com firmeza faz diferença.

**Em aberto:**

- Qual dos dois é A e qual é B: isso depende do sentido de giro.
- Onde liga o C907: não apitou com E1, E2, E3 nem GND.
- Por que E1 dá 6,9 kΩ com as pernas 1, 2 e 3, e 9,2 kΩ com as pernas 4–8, 13–17, 23–27. Voltar a isso ao medir os botões.

## Botões (2026-11-05)

Perninhas vistas por cima: P1 e P3 à esquerda, P2 e P4 à direita. P1 apita com P3, e P2 apita com P4. Sem apertar, um lado não apita com o outro.

| Botão | P1 (esquerda) | P2 (direita) |
|---|---|---|
| K1 | Perna 13 | Perna 8 |
| K2 | Perna 14 | Perna 8 |
| K3 | Perna 13 | Perna 7 |
| K4 | Perna 14 | Perna 7 |
| K5 | Perna 13 | Perna 5 |
| K6 | Perna 14 | Perna 5 |
| K7 | Perna 6 | Perna 13 |

Nos botões K2 a K7, a medição parou no primeiro apito. No K1, a lista foi até o fim. O K7 tem os lados invertidos em relação aos outros.

A matriz, com as pernas que cada botão liga:

| | Perna 8 | Perna 7 | Perna 6 | Perna 5 |
|---|---|---|---|---|
| **Perna 13** | K1 | K3 | K7 | K5 |
| **Perna 14** | K2 | K4 | livre | K6 |

**Conclusões:**

- Os botões formam uma matriz de 2 × 4. Nenhuma perninha do K1 vai ao GND.
- Com o multímetro não dá para saber quais pernas o chip aciona e quais ele lê. Isso sai da captura.

O botão de liga/desliga é uma chave que vai direto à placa de alimentação (220 V). Ele não faz parte da matriz e **não deve ser medido**.

**Em aberto:**

- O cruzamento 14 × 6 está livre: nenhum dos botões K1–K7 usa esse cruzamento.

## EEPROM IC801 (2026-11-05)

| Pino do IC801 | Função (24C01) | Liga em |
|---|---|---|
| 1, 2, 3 | Endereço | GND |
| 4 | GND | GND |
| 5 | SDA | **Perna 25 do chip** |
| 6 | SCL | **Perna 24 do chip** |
| 7 | Proteção de escrita | GND |

Com os pinos de endereço no GND, o endereço esperado é 0x50. Com o pino 7 no GND, a gravação fica liberada. A captura vai confirmar os dois.

## Cabo para a placa de entradas (2026-11-05, em andamento)

Na placa, são 4 fios entre a placa do display e a placa das entradas RCA, e não 9 como diz o brief. Falta confirmar em qual conector eles chegam. Suspeita: são os 4 sinais do CON51 (SDA0, SDA1, SCL e GND).

Olhando a placa de frente, os fios são F1 a F4, da esquerda para a direita.

| Fio | Função | Liga em |
|---|---|---|
| F1 | GND | GND (apita) |
| F2 | Sinal, provável I2C | Perna 1 do chip |
| F3 | Sinal, provável I2C | Perna 2 do chip |
| F4 | Sinal, provável I2C | Perna 3 do chip |

**Conclusões (a confirmar):**

- O CON51 tem SCL e duas linhas SDA. A ordem GND, CL, DA1, DA0 sugere F2 = SCL, F3 = SDA1 e F4 = SDA0, mas isso só sai da captura.
- As pernas 1, 2 e 3 não são as da EEPROM (24 e 25). Os PT2314 parecem estar em outro barramento, então a captura deles deve ser em F2–F4, não no IC801.
- F2, F3 e F4 dão 4,6 kΩ até a perna 40 (escala 20k), igual a E1 e E2. A hipótese de resistores extras (2,3 kΩ) foi descartada.
- Os 6,9 kΩ de E1 com as pernas 1, 2 e 3 continuam sem explicação. Esperado seria 9,2 kΩ.

Há também um cabo de 8 fios entre a placa do display e a placa do amp. Falta confirmar em qual conector ele chega. Antes de medir continuidade nele, conferir tensão, porque a placa do amp pode guardar carga. Medir só na placa do display.

Tensão nos 8 fios contra o GND, com o amp fora da tomada: 0 V em todos. Olhando a placa de frente, os fios são G1 a G8, da esquerda para a direita.

| Fio | Função | Liga em |
|---|---|---|
| G1 | Saída do Q902 | Perna do Q902 mais perto da borda |
| G2 | GND | GND |
| G3 | Sinal do controlador | **Perna 16 do chip** |
| G4 | +5 V | Perna 40 |
| G5 | GND | GND |
| G6 | A descobrir | Nenhuma perna testada apitou |
| G7 | A descobrir | Nenhuma perna testada apitou |
| G8 | A descobrir | Nenhuma perna testada apitou |

Pernas testadas em G1, G3, G6, G7 e G8: 4, 15–17, 23, 26, 27 e 29–31.

Q902, visto por cima com o LCD à esquerda: Q1 é a perna da esquerda, Q2 a do meio e Q3 a da direita. Em continuidade, nenhuma das três apita com o GND (falta a resposta para G1, G6, G7 e G8).

Q2 em Ω (escala 20k):

| Perna do chip | Leitura | Leitura provável |
|---|---|---|
| 15 | 4,66 kΩ | Resistor de base de 4,7 kΩ: Q2 liga à perna 15 |
| 4, 16, 17, 23, 26, 27 | 13,92 kΩ | 4,66 + 4,6 + 4,6 kΩ, passando pela perna 15 e pelo +5 V |
| 31 | 9,30 kΩ | 4,66 + 4,6 kΩ: a perna 31 está no +5 V |
| 29, 30 | sem leitura | Sem ligação a estes pontos |

A mensagem original dizia "37"; a medição pedida era a perna 27.

**Conclusões:**

- A perna 15 aciona a base do Q902 por um resistor de cerca de 4,7 kΩ.
- A perna do Q902 mais perto da borda da placa apita com G1. A perna mais longe da borda apita com G4 (+5 V). A do meio é Q2, a base.
- Pela ordem usual do 2N4401, a perna do +5 V é o coletor, e a de G1 é o emissor. Assim, quando a perna 15 sobe, o Q902 deve levar cerca de 4,3 V ao fio G1, que vai à placa do amp. Falta confirmar com o amp ligado.
- A perna 31 no +5 V e as pernas 29 e 30 soltas combinam com um 8051 (EA alto; PSEN e ALE sem uso). É um bom indício, não uma prova.

**Em aberto:** o que G3 faz, e se algum dos fios G1, G6, G7 e G8 passa pelo Q902 ou é de áudio.

## LED da frente (2026-11-05)

O LED tem 3 pernas: L1 (esquerda), L2 (meio) e L3 (direita). Nenhuma apita com o GND.

| Perna | Apita com | Provável função |
|---|---|---|
| L1 | Nada | Uma das cores |
| L2 | Perna 40, perna 31 e G4 | Comum, no +5 V |
| L3 | Nada | Uma das cores |

Três pernas com o meio no +5 V sugerem um LED de duas cores com anodo comum. O apito de L2 com a perna 31 confirma que a perna 31 está no +5 V.

Em Ω (escala 20k):

| Perna do LED | Perna do chip | Leitura | Leitura provável |
|---|---|---|---|
| L1 | 26 | 0,99 kΩ | Resistor de cerca de 1 kΩ: L1 liga à perna 26 |
| L1 | 4, 17, 23, 27 | 10,25 kΩ | 0,99 + 4,6 + 4,6 kΩ, passando pelo +5 V |
| L3 | 27 | 0,45 kΩ | Resistor de cerca de 470 Ω: L3 liga à perna 27 |
| L3 | 4, 17, 23, 26 | cerca de 9,7 kΩ | 0,45 + 4,6 + 4,6 kΩ, passando pelo +5 V |

Observado com o amp ligado: **vermelho em standby, verde ligado**. Girar o volume não muda a cor. Falta medir qual perna acende cada cor (L1/perna 26 ou L3/perna 27).

## Transistor Q901 (2026-11-05)

Visto por cima, com o LCD à esquerda: T1 é a perna da esquerda, T2 a do meio e T3 a da direita.

| Perna | Apita com | Provável função |
|---|---|---|
| T1 | Perna 4, por cerca de 470 Ω (0,46 kΩ) | Base, a confirmar |
| T2 | Pino 15 do display (luz de fundo) | Saída para a luz de fundo |
| T3 | Perna 40 e G4 (+5 V) | Entrada do +5 V |

O Q901 parece ser a chave da luz de fundo do LCD, acionada pela perna 4. T1 × pernas 17 e 23 deu 9,69 e 9,66 kΩ, que são 0,46 + 4,6 + 4,6 kΩ passando pelo +5 V. Falta confirmar com o amp ligado se a perna 4 muda entre standby e ligado.

## A reconferir (2026-11-05)

Pode ter havido erro de contagem das pernas nas medições anteriores à dos botões K1–K7, que está correta. Ficam a reconferir, usando as pernas 13, 20 e 21 como referência:

- [x] IR, sinal → perna 12: confirmado (apita na 12; não apita na 11 nem na 13)
- [x] Encoder, E1 → perna 22 e E2 → perna 21: contagem confirmada
- [x] Leituras em Ω de E1 com as pernas 1, 2 e 3 (6,9 kΩ): contagem confirmada

## Em uso (2026-11-06)

O Pico de dentro do amp usa estes pontos: o sinal do IR (GP15), o E1 do encoder (GP14) e as pernas 6 e 13 do botão
Function, que é o K7 (GP0 e GP1). Ver `../proxy-ligacao.md`. As capturas dos PT2314 saíram do plano, porque o volume já
vem do display.

**Function (2026-11-06):** com o botão solto, a perna 6 pulsa e a perna 13 fica em 1. Com ele apertado, a perna 13 cai
junto com a 6 em todos os pulsos. Os pulsos da perna 6 vêm em grupos de 3, com cerca de 30 µs cada, a cada 320 µs.

## Falta medir

- [ ] C907: achar onde liga
- [ ] G6, G7 e G8: achar para onde vão
- [ ] Pernas 17 e 23: ainda sem função conhecida
