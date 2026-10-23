# Ligação do analisador lógico ao LCD do SP103

## Mapa de pinos (medido com multímetro em 2026-10-22, amp fora da tomada)

Pinos do LCD numerados da esquerda para a direita, olhando o display de frente (pino 1 = ponta esquerda).
Chip T9311DP: pernas 1–20 na fileira de baixo (da esquerda para a direita) e 40–21 na de cima
(da esquerda para a direita; a perna 40 fica no canto superior esquerdo).

| Pino LCD | Sinal | Perna do chip | Porta (se 8051) | Observação |
|---|---|---|---|---|
| 1 | GND (VSS) | – | – | apita com o GND |
| 2 | +5 V (VDD) | – | – | **não ligar nada** |
| 3 | VO (contraste) | – | – | apita com o GND (trimpot quase no mínimo; normal) |
| 4 | RS | 10 | P3.0 | |
| 5 | RW | 11 | P3.1 | **não** vai ao GND: o controlador controla o RW |
| 6 | E | 28 | P2.7 | |
| 7–14 | D0–D7 | 39–32 | P0.0–P0.7 | P0 precisa de pull-ups: são as redes R907/R908 (9 × 4,7k) |
| 15 | A (backlight +) | – | – | não medido |
| 16 | K (backlight −) | – | – | apita com o GND |

**Conclusão:** barramento de **8 bits**, e o RW é controlado pelo chip (ele pode ler o busy flag).

## Ligação no Pico 2 W

Confirmado no código do firmware (`pinMap`): **Canal N = GP(N+1)** para os canais 1–21.
Os canais 22–24 são GP26–28, que são pinos de ADC e **não** aguentam 5 V. Não use esses canais.

| Sinal | Pino LCD | Canal | Pico GPIO | Pino físico do Pico |
|---|---|---|---|---|
| GND | 1 | – | GND | 3 (ou 8, 13) |
| E | 6 | CH1 | GP2 | 4 |
| RS | 4 | CH2 | GP3 | 5 |
| RW | 5 | CH3 | GP4 | 6 |
| D0 | 7 | CH4 | GP5 | 7 |
| D1 | 8 | CH5 | GP6 | 9 |
| D2 | 9 | CH6 | GP7 | 10 |
| D3 | 10 | CH7 | GP8 | 11 |
| D4 | 11 | CH8 | GP9 | 12 |
| D5 | 12 | CH9 | GP10 | 14 |
| D6 | 13 | CH10 | GP11 | 15 |
| D7 | 14 | CH11 | GP12 | 16 |

Dica: na janela de captura, escreva os nomes nos campos abaixo de cada canal (E, RS, RW, D0…D7).
Assim as ondas ficam legíveis e o script usa os nomes.

## Segurança elétrica

- **5 V nas entradas:** pelo datasheet do RP2350, os GPIOs do banco 0 (exceto os de ADC, GP26–29) toleram 5 V
  **somente com o Pico alimentado** (IOVDD = 3,3 V). Por isso:
  1. Amp **fora da tomada**: ligue os fios.
  2. Pico no USB do Mac (notebook **na bateria**).
  3. Só então ligue o amp na tomada.
  4. Para terminar: **primeiro** desligue o amp da tomada, **depois** o USB do Pico.
- **Resistor de proteção (recomendado):** um de 1 kΩ em série em cada fio de sinal, perto do Pico. Ele não atrapalha
  nesta velocidade e limita a corrente se a ordem acima falhar.
- **Pull-downs internos (errata E9):** o firmware não liga nenhum pull de propósito, mas o RP2350 começa com o
  pull-down ligado. O E9 só atrapalha sinais fracos, e aqui todos os sinais são acionados com força
  (saídas do chip ou pull-ups de 4,7k), então não há problema para a captura.
- **Fios Dupont:** encaixados lado a lado nos pininhos (passo de 2,54 mm), confira que nenhum encosta no vizinho.
  O pino 2 (+5 V) fica **livre**.

## Plano de captura

Com 11 canais, o firmware usa o modo de 16 canais: cabem **cerca de 196 mil amostras** por captura.

| Frequência | Duração máxima | Uso |
|---|---|---|
| 25 MHz | ~7,8 ms | medir a largura do pulso E |
| 10 MHz | ~19,6 ms | ver um bloco de escrita com detalhe |
| 4 MHz | ~49 ms | ligar o amp, trocar de entrada (precisa de pulso E ≥ 0,75 µs) |
| 2 MHz | ~98 ms | sequências longas (precisa de pulso E ≥ 1,5 µs) |

Em todas as capturas, use: canais 1–11, **Edge trigger no canal 01 com "Negative edge" desmarcado**, presamples 512.

Pelo código do firmware (`NEGATIVE_CAPTURE` em `LogicAnalyzer.pio`), o "edge trigger" testa o **nível** do pino:
- "Negative" dispara assim que o pino está em 0;
- "Positive" dispara assim que o pino está em 1.

O E fica em 0 no repouso, então só o "Positive" espera o pulso. Além disso, o pino é testado uma vez por amostra:
em frequências baixas, um pulso E mais curto que o intervalo entre amostras pode passar despercebido.
Por isso a primeira captura é feita a 25 MHz.

1. **Largura do pulso E (primeira captura):** amp ligado, 25 MHz, gire o volume.
   O script mostra a largura mínima do E, e com isso você escolhe a frequência das próximas capturas
   (pelo menos 3 amostras no pulso mais curto).
2. **Ligar o amp (sequência de inicialização):** com o Pico já ligado e esperando a captura, ligue o amp na tomada.
3. **Trocar de entrada:** por exemplo, para PHONO.
4. **Girar o volume.**

Se a captura disparar sem você mexer em nada, é sinal de que o controlador redesenha a tela sozinho de tempos em
tempos. Isso também é uma resposta (pergunta 3).

Salve cada captura com **File → Save** (arquivo `.lac`) em `captures/` e rode:

```
python3 tools/hd44780_decode.py captures/nome.lac
```

Ele mostra:
- os comandos (Function set, Clear, endereço DDRAM…) e os textos escritos, com o horário em µs;
- as **leituras (RW = 1)** e o busy flag;
- a tela reconstruída depois de cada bloco e a largura mínima do pulso E.

## Perguntas que as capturas respondem

1. O controlador chega a ler o LCD (RW = 1)? Se ler, o Pico final precisa responder a essas leituras.
2. Qual é a sequência de inicialização?
3. O texto é redesenhado inteiro ou só os caracteres que mudam? Com que frequência?
