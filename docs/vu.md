# VU meter no display do amp

Com o VU meter ligado na app (aba Display), as duas linhas do display viram as barras dos canais esquerdo (L) e direito
(R) **enquanto houver música**. Desde 2026-10-29. Proposta visual: <https://claude.ai/artifact/6Zrty8KCsb3ZRsa7Uh2Ax7>.

## Caminho dos dados

```
groove-detector ──socket Unix──► sp103-vu-relay ──UDP, Wi-Fi──► Pico (vu.py, proxy.py)
 /tmp/groove-vu.sock              (na placa)                      pede a cada 2 s
 /tmp/groove-gate.json
```

- **groove-detector** (sem mudança): publica o RMS de cada canal num socket Unix e diz no arquivo do gate se há música
  (`"state": "programme"` ou `"idle"`). Formato no `docs/contracts.md` dele.
- **sp103-vu-relay** (`relay/`, Go): só mais um leitor do socket e do gate. Envia cada quadro por UDP a quem pediu nos
  últimos 6 s, no máximo 4 pedidos.
- **Pico** (`firmware/vu.py`): com o VU ligado, pede os quadros a cada 2 s. Calcula as barras, a queda, o pico e o clip,
  e o `proxy.py` escolhe entre o VU e a tela do amp.

O detector não sabe que o SP103 existe, e o Pico só conhece o IP da ponte. Se a ponte, o detector ou o Wi-Fi caírem, o
Pico volta sozinho para a tela do amp em 1 s.

### Protocolo (UDP, porta 7091)

| Mensagem | De → para | Bytes |
|---|---|---|
| Pedido | Pico → ponte | `SUB1` (4 bytes); vale 6 s |
| Quadro | ponte → Pico | `VU`, `0x01`, flags, float32 L, float32 R (12 bytes, little-endian, RMS 0 a 1) |

Flags: bit 0 = há música; bit 1 = o arquivo do gate foi lido. Sem o arquivo do gate, a ponte diz "sem música".

## O que o display mostra

1. **VU desligado** na app: tudo como antes. O Pico nem pede os quadros.
2. **VU ligado, com música e quadros chegando**: L na linha 1, R na linha 2. Coluna 0 = a letra; colunas 1 a 15 = a barra,
   5 colunas de pixels cada: 75 passos do piso até o topo (escala automática).
3. **O controlador desenhou uma tela** (volume, entrada, menu, ligar): a tela do amp aparece na hora e fica 3 s depois do
   último redesenho.
4. **Sem música, sem quadros por 1 s, ou o display do amp desligado**: tela do amp.

A barra sobe na hora e, cheia, esvazia em 0,5 s (a queda acompanha o tamanho da escala). O pico fica parado 1 s e cai
a escala inteira em 1 s. Acima de −1 dBFS, a última célula acende
inteira por 1 s (clip). Pontinhos no fundo da barra vazia marcam −30, −20, −10, −6 e −3 dB abaixo do topo (só os que estão acima
do piso). O clip é sempre o de verdade (−1 dBFS), mesmo com o topo abaixo de 0.

Isso é o layout "barras finas". Há quatro layouts, e cada um tem os seus 8 desenhos próprios. No modo VU eles tomam o
lugar das barras do amp; ao voltar para a tela do amp, o Pico grava de volta os do controlador.

| Layout | Linhas | Passos | Desenhos |
|---|---|---|---|
| Barras finas (`bars`) | L e R, uma linha cada, com a letra na coluna 0 | 75 | 1 a 4 colunas, célula cheia, pico, marca da escala, clip (`vu.GLYPHS`) |
| Deck de cassete (`deck`) | como as barras, com 2 segmentos separados por célula; os das 3 últimas células mais altos (a zona quente). O pico é um segmento sozinho; o clip acende a última célula | 30 | 7 (`vu.DECK_GLYPHS`) |
| Escala impressa (`scale`) | L e R na linha 1 (L na metade de cima de cada célula, R na de baixo); a linha 2 é a régua em dB abaixo do topo (`20 10 6 3 0` na escala automática). O pico é um segmento sozinho; no clip, o 0 da régua vira o bloco cheio da ROM | 32 | 8 pares L/R (`vu.SCALE_GLYPHS`) |
| Yamaha KX-393 (`kx393`) | o medidor do deck: L e R na linha 1, sem letras (L em cima, R embaixo), um segmento por célula na escala do deck, de −30 a +8, de 2 em 2 dB perto do 0. O 0 do deck fica 10 dB abaixo do topo; os segmentos acima dele são mais altos. A linha 2 é a régua `30 17 10 4 0 4 8`. O pico é um segmento sozinho; o clip acende o último | 16 | 6 (`vu.KX_GLYPHS`) |


## Configuração (app, aba Display)

| Campo | Padrão | Faixa |
|---|---|---|
| VU meter | Disabled | Disabled (desligado), barras finas, deck de cassete, escala impressa ou Yamaha KX-393 |
| VU source (IP) | vazio | o IP da placa com a ponte, obrigatório com o VU ligado; o MicroPython não resolve nomes `.local` |

A escala é sempre a automática (abaixo). Com "Disabled", o layout escolhido antes fica guardado para quando o VU voltar.

Fica no `names.json` do Pico, junto com os nomes (`"vu": {"on", "auto", "layout", "relay"}`; `"auto"` é sempre true, e o
`"floor"`/`"top"` de um arquivo antigo é ignorado). A linha embaixo dos campos diz o
que o VU está fazendo: "VU on the display now", "waiting for music", "no data from the VU source"...

**Escala automática (padrão desde 2026-10-29):** o nível do REC OUT muda muito com a fonte. Medido com
música: DAB com média perto de −30 dBFS; vinil (o Rega na entrada TUNER) com média −11 e picos −3, nos dois sockets do
detector, então não é ruído grave. Com a escala automática, o topo fica 5 dB acima do quadro mais alto: sobe na hora e,
com música, desce 1 dB/s (do vinil ao DAB leva uns 24 s). O piso fica 20 dB abaixo do topo, como num VU de ponteiro: a
música varia pouco de um quadro para outro (no vinil, 90 % dos quadros numa faixa de 7 dB), e com 20 dB a barra fica
entre a metade e 3/4, mexendo. Sem música o topo fica parado; ele vai de −40 a 0 dB. A app mostra a escala de agora
("scale −26 to −6 dB").

**Escala manual (removida da página em 2026-11-02):** piso e topo fixos, escolhidos à mão. Saiu porque a automática
acompanha a fonte sozinha; o `vu.py` ainda a aceita (`"auto": false`), mas só os testes a usam.

**L e R iguais:** a placa de captura USB (GeneralPlus USB Audio Device) é mono: só a entrada de microfone, 1 canal
(`/proc/asound/card0/stream0`: `Channels: 1`, `MONO`). O detector repete o mesmo valor nos dois canais, e o R do REC
OUT provavelmente nem é medido. Com uma captura estéreo de linha, o VU mostra os dois canais sem mudar nada no Pico
nem na ponte; só é preciso recalibrar o ganho no groove-detector.

Se o VU der um erro no Pico, ele se desliga sozinho e o display continua com a tela do amp; a app mostra o erro.
Diagnóstico em `http://sp103.local/names`, campo `vu` (quadros recebidos, idade do último, música).

## Instalar a ponte

Ver [`trocar-de-placa.md`](trocar-de-placa.md). Cada placa com o groove-detector pode ter a sua; o Pico escolhe pelo IP.

O serviço `sp103-vu-relay` roda como `nobody`, no grupo `groove` (o socket do VU é `root:groove 0660`).

## Atraso

Estimado, ainda não medido: o detector junta um bloco de amostras antes de calcular (~46 ms), a ponte e o Wi-Fi somam
de 5 a 20 ms (às vezes 50 a 100 ms), e o cristal do display leva de 100 a 200 ms para mudar um pixel. As barras
acompanham a música como um VU de ponteiro; a batida seca do bumbo pode parecer um pouco atrasada. A economia de
energia do Wi-Fi do Pico já está desligada (`web.py`).

O VU mede o REC OUT, que normalmente sai antes do controle de volume do amp: com o volume baixo, as barras continuam
altas.

## Testes

- `python3 tools/test_vu.py`: queda, pico, clip, desenho das linhas, pedido à ponte, "só com música" e a configuração.
- `python3 tools/test_proxy.py`, parte 3: o VU alterna com a tela do amp (3 s depois de um redesenho) e some sem quadros.
- `cd relay && make test`: pacote, pedidos (validade de 6 s, limite de 4), leitura do gate e o caminho completo.
- Na rede (2026-10-29): a ponte enviou ~22 quadros/s ao Mac e ~33/s ao Pico.
