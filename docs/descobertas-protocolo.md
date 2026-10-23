# Como o controlador do SP103 fala com o LCD (descobertas das capturas)

Fonte: capturas em `captures/`, decodificadas com `tools/hd44780_decode.py`.

## Volume: `01-volume-c.lac` (2026-10-23, um clique no knob)

Tela depois do clique:

```
┌────────────────┐
│Volume -28.75 dB│
│■■■■■■■■■■      │   <- 10 caracteres personalizados (código 0x00) + 6 espaços
└────────────────┘
```

- **Barramento de 8 bits.** Os pulsos do E duram de 10,5 a 22,5 µs (às vezes mais). É um controlador lento,
  e 2 MHz de amostragem bastam (21 amostras no pulso mais curto).
- **Lê o busy flag antes de cada comando e de cada caractere.** A sequência por caractere é:
  1. leitura (RS=0, RW=1): busy flag + contador de endereço
  2. comando `Set DDRAM addr` (posiciona na coluna)
  3. leitura (RS=0, RW=1)
  4. escrita do caractere (RS=1)

  São cerca de 230 µs por caractere. Ele **não** usa o incremento automático do endereço: posiciona cada caractere.
- **Um clique no volume redesenha as duas linhas inteiras:** 32 caracteres em cerca de 8,6 ms.
- **Linha 1:** `Volume -28.75 dB`.
- **Linha 2, ao mexer no volume:** uma **barra gráfica** com o caractere personalizado `0x00` (provavelmente
  um bloco cheio). Comprimento: 10 de 16 colunas para -28,75 dB, ou seja, proporcional a (78,75 − 28,75) / 78,75 ≈ 63 %.
  Na tela, a barra substitui o nome da entrada (confirmado visualmente).
- **Leituras:** o busy flag nunca apareceu em 1 nesta captura. O LCD responde rápido em relação ao ritmo do controlador.
- **Repouso:** entre as escritas, o RS fica em 1 e os dados ficam presos no último byte escrito (não voltam a 0xFF).
  O E fica em 0.

### O que isso significa para o projeto
- **O Pico final precisa responder às leituras** (RW = 1) do controlador, pelo menos com o busy flag = 0.
  Se não responder, o controlador pode travar esperando.
- **A opção "cortar só o pino E" é improvável**, porque os dados não ficam livres no repouso.
  O caminho realista é interceptar os sinais (cortar os pinos 4 a 14) ou desoldar o LCD.
- **O caractere personalizado 0x00** é definido em algum momento (provavelmente ao ligar).
  A captura de inicialização deve mostrar os comandos `Set CGRAM addr` com o desenho dele.

## Entrada Phono: `04-phono-b.lac` (2026-10-23)

```
┌────────────────┐
│Volume -28.75 dB│
│PHONO           │
└────────────────┘
```

- Ao trocar de entrada, o controlador também **redesenha as duas linhas inteiras** (cerca de 8,5 ms),
  com o mesmo padrão (leitura → endereço → leitura → caractere).
- Linha 2 = nome da entrada, completado com espaços até as 16 colunas.

## Entradas: `05-tuner` a `09-dab` (2026-10-23)

Mesmo padrão do Phono: as duas linhas são redesenhadas, e a linha 2 traz o nome da entrada completado com espaços.

| Botão | Linha 2 |
|---|---|
| Phono | `PHONO` |
| Tuner | `TUNER` |
| Tape/Aux | `TAPE/AUX` |
| CD | `CD` |
| DVD | `DVD` |
| DAB | `DAB` |

## Ao ligar: `03-liga.lac` (2026-10-23)

Capturado com **pattern trigger** E=1, RS=0, RW=0 (canais 1–3, padrão `100`), a 1 MHz, com jumper entre GP0 e GP1 do Pico.
Com o edge trigger não funciona: durante o reset o controlador deixa E, RS e RW em 1 (`00-amp-onoff.lac`).

Sequência:
1. `0x01` Clear → `0x06` Entry mode (incrementa) → `0x0C` Display ON (sem cursor) → `0x38` Function set
   (8 bits, 2 linhas, 5x8). O Function set vem **por último**, o que não é comum, mas funciona porque o LCD
   já liga no modo de 8 bits.
2. `0x40` Set CGRAM addr 0 e mais **64 bytes**: os 8 caracteres personalizados (abaixo).
3. **Tudo se repete cerca de 64 ms depois** (init + CGRAM de novo).
4. As duas linhas são preenchidas com espaços (posicionando cada caractere) e depois vem a tela de boas-vindas:

```
┌────────────────┐
│    ACOUSTIC    │
│    SOLUTIONS   │
└────────────────┘
```

A captura (190 ms) termina na tela de boas-vindas. A passagem para a tela normal acontece depois.

### Telas seguintes: `03-liga-telas.lac` (burst, 10 trechos de 19 ms a 1 MHz)

Capturado armando o edge trigger (E) assim que "ACOUSTIC SOLUTIONS" apareceu, e girando o volume depois para completar
os trechos. O fio do D1 estava sem contato, mas o texto se recupera pelo contexto (o bit 1 foi lido sempre como 0).

Sequência completa ao ligar (cerca de 4 s no total):

```
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│    ACOUSTIC    │ --> │Amplifier SP103 │ --> │Volume -28.75 dB│
│    SOLUTIONS   │     │ SW version 1.0 │     │DAB             │   <- última entrada usada
└────────────────┘     └────────────────┘     └────────────────┘
```

A versão `1.0` foi confirmada na tela pelo dono.
Depois de mexer no volume, a linha 2 vira a barra e, um tempo depois, **volta sozinha** ao nome da entrada.

Observação: o programa não salvou `LoopCount` no arquivo `.lac` desta captura em burst. O script detecta o burst
pelo tamanho dos dados.

### Caracteres personalizados (CGRAM)

| Código | Desenho (8 linhas, 5 pontos) | Uso |
|---|---|---|
| 0x00 | `00 1F 11 11 11 11 1F 00`: **caixa vazia** (contorno) | barra de volume |
| 0x01 | só a última linha cheia | nível 1/7 |
| 0x02 | 2 linhas de baixo | nível 2/7 |
| 0x03 | 3 linhas | nível 3/7 |
| 0x04 | 4 linhas | nível 4/7 |
| 0x05 | 5 linhas | nível 5/7 |
| 0x06 | 6 linhas | nível 6/7 |
| 0x07 | 7 linhas (bloco quase cheio) | nível 7/7 |

Os códigos 0x01–0x07 formam "barras verticais" crescentes, provavelmente usadas nos menus do Function
(grave/agudo?) ou em alguma animação. Ainda não vimos onde.

## Function, 1º toque: `13-function-1.lac` (2026-10-23)

Fios com mau contato nesta captura: RW e D4 sempre em 0, e o RS se soltou no começo. Mesmo assim, o padrão fixo
(leitura → endereço → leitura → caractere) permite separar endereço e dado em grupos de 4 pulsos, e o D4 se recupera
pelo contexto. Reconstrução (falta confirmar na tela):

```
┌────────────────┐
│Bass -10 dB     │
│  ■■■■■<>       │   <- barra bipolar: "<>" no centro (colunas 7–8), 5 caixas à esquerda = -10 dB
└────────────────┘
```

Segunda gravação do mesmo toque (só o RW falhou), com outro valor de grave:

```
┌────────────────┐
│Bass   2 dB     │   <- valor alinhado à direita nas colunas 5–7 ("-10", "  2"), sem sinal de "+"
│       <>■      │   <- 1 caixa à direita do centro = +2 dB
└────────────────┘
```

- A linha 2 é escrita **a partir do centro**: colunas 7, 8 ("<", ">"), 9…15 e depois 0…6.
- Cada caixa (caractere 0x00) parece valer 2 dB, compatível com os passos de grave do PT2314.

## Function, todos os menus: `13-function-todos.lac` (burst, 2026-10-23)

Decodificado com `--sem-rw` (o RW falhava de vez em quando). São 6 cliques no Function até voltar à tela normal:

```
1 ┌────────────────┐  2 ┌────────────────┐  3 ┌────────────────┐
  │Bass   2 dB     │    │Treble   0 dB   │    │Balance <level> │
  │       <>■      │    │       <>       │    │       <>       │
  └────────────────┘    └────────────────┘    └────────────────┘
4 ┌────────────────┐  5 ┌────────────────┐  6 ┌────────────────┐
  │   Loudness     │    │   Speakers     │    │Volume -15.00 dB│
  │ < OFF >   ON   │    │   OFF   < ON > │    │DAB             │
  └────────────────┘    └────────────────┘    └────────────────┘
```

- Bass e Treble: valor numérico alinhado à direita (3 caracteres) + barra bipolar com "<>" no centro.
- Balance: "<level>" quando centrado (falta ver como fica fora do centro).
- Loudness e Speakers: duas opções, e a escolhida fica entre "< >".
- Os trechos 7 a 10 são cliques no volume (com o D4 falhando: "Foleme" = "Volume").

## Balance girando o knob: `15-balance.lac` (burst, 2026-10-23)

Cada clique do knob redesenha a tela inteira, em passos de **1,25 dB** (o atenuador de alto-falante do PT2314):

```
┌────────────────┐        ┌────────────────┐
│Balance -5.00 dB│  ...   │Balance-10.00 dB│   <- com dois dígitos, o espaço depois de "Balance" some
│       <>■      │        │       <>■■     │   <- 1 caixa a cada 5 dB, deste lado do centro
└────────────────┘        └────────────────┘
```

Os 10 trechos foram -1,25 → -12,50 dB, sempre na mesma direção. Ordem de escrita: linha 1 inteira, depois
"<" ">" (colunas 7–8), colunas 0–6 da linha 2 e por fim colunas 9–15.
Falta ver o outro lado: de que lado a barra fica, e se o número muda de sinal ou ganha L/R.

## Controle remoto e desligar (observado pelo dono, 2026-10-23)

- O controle remoto faz exatamente o mesmo que os botões do painel, com as mesmas telas.
- Ao desligar, o amp **não escreve nada** no display.

## Balance para o outro lado: `15-balance-b.lac` (burst, 2026-10-23)

Os mesmos números negativos (-1,25 → -12,50 dB). Só a **barra** muda de lado e cresce para a **esquerda** do "<>":

```
┌────────────────┐
│Balance-10.00 dB│   <- igual ao outro lado: a linha 1 não diz qual canal está atenuado
│     ■■<>       │
└────────────────┘
```

## Status

**Fase de captura concluída (2026-10-23).** Todas as telas do controlador estão registradas acima.
Próximo passo: a bancada. O Pico 2 W e o display reserva vão reproduzir essas telas fora do amplificador.
