# Instalação atual: o Pico no meio, entre o controlador e o display

Montado e funcionando desde 2026-10-29 (opção 3b de `opcoes-intercepcao.md`). O display do amp foi dessoldado. Os
pinos 1–3, 15 e 16 voltaram a ser soldados na placa; os pinos 4–14 não entram mais nela:

- **Lado do controlador**: fios Dupont soldados nos furos 4–14 da placa de baixo.
- **Lado do display**: os fios soldados nas pontas de cima dos pinos do display (os mesmos da antiga escuta, mesmas
  cores).

Programa: `firmware/proxy.py`. O `main.py` importa o `escuta.py`, que só importa o `proxy.py`, porque o `main.py` só se
troca pelo cabo.

## Ligação

Pino 1 do Pico: o canto ao lado do USB. Os pinos 1–20 ficam numa fileira e os 21–40 na outra (o 40 fica de frente para
o 1, também ao lado do USB).

### Lado do controlador: fios de baixo → Pico

| Furo na placa | Sinal | Pico | Pino físico |
|---|---|---|---|
| 4 | RS | GP3 | 5 |
| 5 | RW | GP4 | 6 |
| 6 | E | GP2 | 4 |
| 7–14 | D0–D7 | GP5–GP12 | 7, 9, 10, 11, 12, 14, 15, 16 |

### Lado do display: fios de cima → Pico

| Pino do display | Sinal | Fio | Liga em | Pino físico |
|---|---|---|---|---|
| 1 | GND | preto | GND | 3 (qualquer GND serve: 3, 8, 13, 38…) |
| 2 | +5 V | vermelho | **VSYS** | **39** (nunca o 40, VBUS) |
| 4 | RS | amarelo | GP16 | 21 |
| 5 | RW | laranja | **GND** | 23 |
| 6 | E | marrom | GP17 | 22 |
| 7–10 | D0–D3 | verde, branco, cinza, roxo | nada (pontas isoladas com fita) | — |
| 11 | D4 | azul | GP18 | 24 |
| 12 | D5 | branco | GP19 | 25 |
| 13 | D6 | cinza | GP20 | 26 |
| 14 | D7 | roxo | GP21 | 27 |

- Contraste (3) e luz de fundo (15, 16) continuam vindo da placa do amp.
- O display funciona em 4 bits, com o RW no GND: ele só recebe e nunca manda 5 V de volta ao Pico. Os 3,3 V do Pico
  bastam para ele, sem conversor de nível (testado na bancada, `bancada-ligacao.md`).
- Como os fios brancos, cinzas e roxos se repetem, cada um está marcado com o número do pino.

### Conferir o corte (multímetro em continuidade, amp fora da tomada)

- Fio de baixo do furo N × pino N do display, para N = 4 a 14: **não apita**.
- Pino 1 do display × GND da placa, e pino 2 × +5 V: **apita**.

## O que o programa faz

- **Lê o controlador** (`sniffer.py`): a cada descida do E, o PIO lê os 11 fios, e o DMA copia as palavras para um
  buffer circular. Nada se perde enquanto o Python cuida do Wi-Fi.
- **Responde "livre"** (`busy.py`): o controlador pergunta "ocupado?" antes de cada comando e de cada letra, e para isso
  solta só o D7. Em cada leitura (RW = 1 na subida do E), o PIO puxa o D7 para 0 até o E descer.
- **Desenha** (`hd44780.py`, `names.py`, `lcd1602.py`): depois de 2 ms sem escritas, a tela está completa. O Pico troca
  os nomes e manda ao display só as linhas que mudaram, sem piscar. Os desenhos próprios (as barras) e o "display
  on/off" seguem os do controlador. A cada 30 s ele resincroniza o modo 4 bits e reescreve tudo, sem apagar a tela, para
  corrigir algum erro de ruído nos fios.
- **Publica** o estado (`amp_state.py`, `web.py`). O estado mostra sempre os nomes originais ("TUNER"), mais o nome
  personalizado em `input_name`.

### Regra de segurança

GP2–GP12 recebem 5 V do amp, sem resistores em série. Eles **nunca** podem ser saída com valor 1, porque isso brigaria
com o controlador. O único que vira saída é o GP12 (D7), e só para 0: o valor de saída fica fixo em 0, só a direção
muda, na força mínima (2 mA). O D7 é do P0 do controlador, que só sobe pelo resistor de 4,7 kΩ, então puxar para 0 é
sempre seguro (~1 mA).

## Alimentação pelo amp

O fio vermelho (pino 2 do display, +5 V) vai ao **VSYS, pino 39** do Pico. Esse 5 V existe também em standby, então o
Pico fica ligado sempre que o amp está na tomada, e liga junto com o controlador.

Na fileira dos pinos 21–40, com o USB para cima: o 1º pino do canto, colado ao USB, é o **40 (VBUS, não use)**; o 2º
é o **39 (VSYS)**; o 3º é o 38 (GND).

**Por que o VSYS e não o VBUS:** o VBUS (40) é ligado direto ao conector USB. Entre o VBUS e o VSYS há um diodo dentro
do Pico, que impede o 5 V do amp de ir para o computador.

### Regra do USB

Com o fio vermelho no VSYS, **não ligue o USB com o amp fora da tomada**. O USB alimentaria o painel do amp de trás para
frente, pelo Pico, e isso pode estragar o regulador de 5 V do amp. Isso aconteceu em 2026-10-29: com o USB ligado, o
controlador ligou e desenhou a tela. Para usar o cabo, com o amp fora da tomada, **solte antes o fio vermelho**.

Um diodo Schottky 1N5817 no fio vermelho (anodo no display, catodo no VSYS) acabaria com essa regra.

Com o Pico dentro do amp, atualize só pelo Wi-Fi (`atualizacao-wifi.md`).

## Sem o Pico

O controlador pergunta "ocupado?" antes de cada letra e, sem resposta, pergunta para sempre. **Sem o Pico, o display
do amp não atualiza.** Para voltar ao original, ligue cada fio de baixo ao fio de cima do mesmo número (11 jumpers).

## Diagnóstico

- **`http://sp103.local/names`**, campo `proxy`:
  - `reads` e `writes`: leituras e escritas do controlador desde que o Pico ligou.
  - `busy_high`: leituras em que o controlador viu "ocupado" depois de o Pico já estar respondendo. **Tem que ficar em
    0.** Ao ligar, o controlador espera alguns milissegundos enquanto o Pico inicia; essas leituras não contam.
- **`http://sp103.local/bus`** (ou `http://192.168.178.108/bus`): estatísticas do barramento e o registro das últimas
  8192 palavras (umas 50 telas), com horário (o Pico acerta o relógio pela internet).
  1. Toque em **Clear log**.
  2. Faça o que quer estudar no amp e anote a hora.
  3. Toque em **Download log (CSV)**.
  4. Veja as telas montadas: `python3 tools/ler_bus.py ~/Downloads/sp103-bus-<data>-<hora>.csv` (com `--palavras`,
     cada palavra também).

  Se o "Biggest batch" ficar vermelho (3000 palavras ou mais numa leitura só), algumas palavras podem ter se perdido.
- **Depois de o Pico reiniciar sozinho** (uma atualização, por exemplo), o display fica vazio até o controlador mandar a
  próxima tela (girar o volume ou trocar de entrada). Ao ligar o amp na tomada isso não acontece: os dois ligam juntos.

## Testes

- `python3 tools/test_proxy.py`: roda o `proxy.py` no computador com as capturas `.lac` e confere cada tela no display,
  já com os nomes. Confere também que o RW não muda durante o pulso do E, a regra que o `busy.py` usa.
- Testado no Pico pelo cabo (2026-10-29): o programa do `busy.py` puxa o D7 só nas leituras; e no amp, depois de o Pico
  começar a responder, nenhuma leitura deu "ocupado".

## Em aberto

- **Saber quando o amp vai para standby.** Ao desligar, o controlador não escreve nada no display. Ao ligar, ele manda
  "Clear display". Falta achar um sinal de standby (talvez a luz de fundo, pinos 15/16).
