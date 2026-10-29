# VU meter no display do amp

Com "VU meter" ligado na página do Pico, as duas linhas do display viram as barras dos canais esquerdo (L) e direito
(R) **enquanto houver música**. Desde 2026-10-29. Proposta visual: <https://claude.ai/artifact/6Zrty8KCsb3ZRsa7Uh2Ax7>.

## Caminho dos dados

```
groove-detector ──socket Unix──► sp103-vu-relay ──UDP, Wi-Fi──► Pico (vu.py, proxy.py)
 /tmp/groove-vu.sock              (no Orange Pi)                  pede a cada 2 s
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

1. **VU desligado** na página: tudo como antes. O Pico nem pede os quadros.
2. **VU ligado, com música e quadros chegando**: L na linha 1, R na linha 2. Coluna 0 = a letra; colunas 1 a 15 = a barra,
   5 colunas de pixels cada: 75 passos do piso até o topo (configuráveis).
3. **O controlador desenhou uma tela** (volume, entrada, menu, ligar): a tela do amp aparece na hora e fica 3 s depois do
   último redesenho.
4. **Sem música, sem quadros por 1 s, ou o display do amp desligado**: tela do amp.

A barra sobe na hora e cai a 26 dB/s. O pico fica parado 1,5 s e cai a 15 dB/s. Acima de −1 dBFS, a última célula acende
inteira por 1 s (clip). Pontinhos no fundo da barra vazia marcam −30, −20, −10, −6 e −3 dB abaixo do topo (só os que estão acima
do piso). O clip é sempre o de verdade (−1 dBFS), mesmo com o topo abaixo de 0.

Os 8 desenhos próprios do display (`vu.GLYPHS`): 1 a 4 colunas, célula cheia, marca de pico, marca da escala e clip. No
modo VU eles tomam o lugar das barras do amp; ao voltar para a tela do amp, o Pico grava de volta os do controlador.

## Configuração (página do Pico, "Display")

| Campo | Padrão | Faixa |
|---|---|---|
| VU meter | desligado | — |
| VU floor (dB) | −40 | −60 a −10: a barra vazia |
| VU top (dB) | 0 | −30 a 0: a barra cheia; pelo menos 10 dB acima do piso |
| VU source (IP) | 192.168.178.105 (oceano-0001) | um IP; o MicroPython não resolve nomes `.local` |

Fica no `names.json` do Pico, junto com os nomes (`"vu": {"on", "floor", "top", "relay"}`). A linha embaixo dos campos diz o
que o VU está fazendo: "VU on the display now", "waiting for music", "no data from the VU source"...

**Acertar a escala:** o REC OUT chega bem abaixo de 0 dBFS (depende do ganho da captura no groove-detector, que não
deve ser mexido por causa do VU). Medido em 2026-10-29 com música: no oceano-0000 (Pi 5, ganho 25 %) a média ficou em
−30 dBFS e os picos em −25; no oceano-0001, −40 e −35. Para o Pi 5: piso −45, topo −20. Regra prática: topo uns 5 dB
acima dos picos, piso uns 15 dB abaixo da média.

**L e R iguais:** a placa de captura do oceano-0000 (GeneralPlus USB Audio Device) é mono: só a entrada de microfone,
1 canal (`/proc/asound/card0/stream0`: `Channels: 1`, `MONO`). O detector repete o mesmo valor nos dois canais, e o R
do REC OUT provavelmente nem é medido. Com uma captura estéreo de linha (plano: HiFiBerry DAC+ ADC), o VU mostra os
dois canais sem mudar nada no Pico nem na ponte; só é preciso recalibrar o ganho no groove-detector e acertar o piso e
o topo de novo.

Se o VU der um erro no Pico, ele se desliga sozinho e o display continua com a tela do amp; a página mostra o erro.
Diagnóstico em `http://sp103.local/names`, campo `vu` (quadros recebidos, idade do último, música).

## Instalar a ponte

Cada placa com o groove-detector pode ter a sua; o Pico escolhe pelo IP.

```sh
cd relay
make test
make deploy HOST=orange@192.168.178.105      # oceano-0001 (Orange Pi)
make deploy HOST=alemser@192.168.178.99      # oceano-0000 (Pi 5)
make status HOST=orange@192.168.178.105
```

O serviço `sp103-vu-relay` roda como `nobody`, no grupo `groove` (o socket do VU é `root:groove 0660`).

**Firewall:** no oceano-0000 (Pi 5) o ufw bloqueia a entrada. Para usar essa placa:

```sh
ssh alemser@192.168.178.99 'sudo ufw allow from 192.168.178.0/24 to any port 7091 proto udp comment sp103-vu-relay'
```

O oceano-0001 não tem firewall.

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
- Na rede (2026-10-29): a ponte do oceano-0001 enviou ~22 quadros/s ao Mac e ~33/s ao Pico.
