# Etapa 4: ligar o Pico no amp para só escutar

> **Histórico.** Desde 2026-10-29 o display está dessoldado e a ligação atual é a do proxy (`docs/proxy-ligacao.md`).

O Pico lê o barramento do LCD do amp e publica o estado em `http://sp103.local/`. Ele **não manda sinal nenhum** para o
amp: o display do amp funciona igual a sempre, e para desfazer basta puxar os fios. Nada é cortado nem soldado.

Programa: `firmware/escuta.py` (roda sozinho ao ligar, pelo `main.py`).

## Decisões (2026-10-24)

- **Sem resistores em série**: o dono não vai comprar. O risco é pequeno, porque o próprio amp limita a corrente: os
  dados D0–D7 só vão a 1 pelos pull-ups de 4,7 kΩ (R907/R908), e RS/RW/E saem de portas que são fracas no 1.
  Em troca, o programa nunca põe 1 em GP2–GP12 (ver "Regra" abaixo).
- **Alimentação pelo próprio amp** (pino 2 do LCD → VSYS do Pico). Medido pelo dono: **o pino 2 tem 5 V mesmo em standby**.
  Assim o Pico fica ligado sempre que o amp está na tomada, e liga junto com o controlador: nunca recebe 5 V nos sinais
  estando desligado. Falta confirmar se a fonte de 5 V aguenta o Pico (ver "Teste da fonte").

## Ligação (amp FORA DA TOMADA, USB do Pico desconectado)

Os fios dos sinais são os mesmos das capturas (`ligacao-analisador.md`): Dupont fêmea nas pontas dos pinos que sobram
acima da placa do display.

| Pino do LCD do amp | Sinal | Pico | Pino físico do Pico |
|---|---|---|---|
| 1 | GND | GND | 38 |
| 2 | +5 V | **VSYS** | **39** (nunca o 40, VBUS) |
| 4 | RS | GP3 | 5 |
| 5 | RW | GP4 | 6 |
| 6 | E | GP2 | 4 |
| 7–14 | D0–D7 | GP5–GP12 | 7, 9, 10, 11, 12, 14, 15, 16 |

Os pinos 3, 15 e 16 do LCD ficam livres.

### Fios soldados nas pontas dos pinos (guia de solda)

Para uma ligação firme (e para os testes de escrita), solde um fio com Dupont **fêmea** na outra ponta, em cada ponta de
pino que sobra acima da placa do display. O lado do Pico encaixa na barra de pinos dele.

| Pino do LCD | Sinal | Cor (como montado) | Pico | Pino físico | Para quê |
|---|---|---|---|---|---|
| 1 | GND | preto | GND | 3 (qualquer GND serve: 3, 8, 13, 38…) | sempre |
| 2 | +5 V | vermelho | VSYS | 39 (nunca o 40) | alimentar o Pico pelo amp (solto com o USB ligado) |
| 4 | RS | amarelo | GP3 | 5 | escuta e testes |
| 5 | RW | laranja | GP4 | 6 | escuta e **teste 1** |
| 6 | E | **marrom** | GP2 | 4 | escuta |
| 7 | D0 | **verde** | GP5 | 7 | escuta |
| 8 | D1 | branco | GP6 | 9 | escuta |
| 9 | D2 | cinza | GP7 | 10 | escuta |
| 10 | D3 | roxo | GP8 | 11 | escuta |
| 11 | D4 | azul | GP9 | 12 | escuta |
| 12 | D5 | branco | GP10 | 14 | escuta |
| 13 | D6 | cinza | GP11 | 15 | escuta |
| 14 | D7 | roxo | GP12 | 16 | escuta |

Pinos 3, 15 e 16: **não soldar** (contraste e luz de fundo). Os pinos 8 e 13 do Pico são GND, por isso a numeração pula.

**Montado em 2026-10-24** e conferido pelas fotos: sem pontes de solda, display do amp normal. Os fios mais longos fazem
a borda do E "tremer"; o `sniffer.py` filtra isso (só aceita pulsos do E com 3 µs ou mais). Com o filtro, 1408 palavras
lidas sem nenhum erro.

Passo a passo:
1. **Amp fora da tomada.** Pico desligado dos fios.
2. Corte 13 fios com uns 20 cm. Se as cores repetirem, marque cada fio com fita e o número do pino do LCD.
3. Desencape ~3 mm, torça e estanhe a ponta do fio.
4. Ponha um pedaço de **termo-retrátil** no fio antes de soldar.
5. Encoste o fio estanhado na ponta do pino e aqueça só 2–3 s. Os pinos são vizinhos (2,54 mm): cuidado com
   pingos de solda entre eles.
6. Passe o termo-retrátil sobre a solda e aqueça para encolher.
7. Confira com o multímetro em continuidade (apito):
   - de cada Dupont até o seu pino do LCD: **apita**;
   - entre pinos vizinhos (1–2, 4–5, 5–6, …, 13–14): **não apita**.
8. Prenda o feixe com abraçadeira, para o peso dos fios não puxar as soldas.
9. Ligue os Dupont no Pico pela tabela. O fio do VSYS (vermelho) fica **solto** sempre que o USB estiver ligado
   (ver "Regra do USB").

O display reserva da bancada (GP16–21, `bancada-ligacao.md`) pode continuar ligado: ele mostra uma cópia da tela do amp
**já com os textos personalizados** (prévia da etapa 6). Antes da primeira tela ele mostra "waiting for amp".

### Por que o VSYS e não o VBUS
O VBUS (40) é ligado direto ao conector USB. No VSYS (39) há um diodo dentro do Pico entre os dois, que impede o 5 V do amp
de ir para o computador.

### Regra do USB
Com o fio do pino 2 ligado ao VSYS, **não conecte o USB com o amp fora da tomada**: o USB alimentaria o painel do amp de
trás para frente, pelo Pico, e isso pode estragar o regulador de 5 V do amp. Para usar o computador (mpremote), solte antes
o fio do VSYS. Com o amp na tomada não há esse problema, mas o mais simples é sempre soltar o fio.

## Teste da fonte (na primeira vez)

O Pico 2 W com Wi-Fi gasta uns 50 a 100 mA (picos de ~250 mA). Um regulador 7805 aguenta com folga; um 78L05 (pequeno,
com cara de transistor) não.

1. Faça a ligação acima e deixe o multímetro em tensão contínua (escala 20 V) entre os pinos 1 e 2 do LCD, com fios
   levados para fora do amp.
2. Ligue o amp na tomada e depois ligue o amp. Em uns 10 s, `http://sp103.local/` deve abrir e mostrar o estado.
3. Por 10 minutos, a tensão deve ficar **entre 4,8 e 5,2 V**, e o display e o controle remoto devem funcionar normalmente.
4. Se a tensão cair, ou o amp ficar estranho (display piscando, reiniciando): tire da tomada. A fonte não aguenta, e o
   Pico vai para um carregador USB próprio, sempre na tomada.

## Pico dentro do amp (2026-10-24)

Para fechar o gabinete com o Pico dentro, ele passa a ser alimentado pelo amp: o **fio vermelho** (pino 2 do LCD, +5 V)
vai ao **VSYS, pino físico 39** do Pico (nunca ao 40, VBUS). O preto (GND) e os 11 sinais continuam como estão.

Passo a passo:
1. **Amp fora da tomada. USB do Pico desligado.**
2. Encaixe o Dupont vermelho no pino 39 do Pico. Com o conector USB para cima, na fileira dos pinos 21-40: o 1º pino
   do canto, colado ao USB, é o **40 (VBUS, não use)**; o **2º é o 39 (VSYS)**; o 3º é o 38 (GND). É a fileira do lado
   oposto à dos sinais (o preto, no pino 3, e GP2-GP12 ficam na outra). Conte com cuidado.
3. **Teste da fonte, antes de fechar** (ver acima): multímetro em tensão contínua entre os pinos 1 e 2 do LCD, amp na
   tomada e ligado, Pico rodando (a página `http://sp103.local/` abre). A tensão tem que ficar entre 4,8 e 5,2 V por
   alguns minutos, com o display e o controle remoto normais. Se cair, tire da tomada: a fonte do amp não aguenta e o
   Pico precisa de um carregador USB próprio.
4. Prenda o Pico isolado: espaçadores de nylon ou fita dupla face sobre uma placa isolante. Nenhum pino pode encostar
   no metal do gabinete, e tudo longe da parte de 230 V (fonte, transformador, cabo de força).
5. Prenda o feixe de fios com abraçadeira, sem puxar as soldas do LCD.
6. Feche o gabinete. Desse ponto em diante, **atualize só pelo Wi-Fi** (`python3 tools/enviar.py`).

Regras com o Pico dentro:
- **Não ligue o USB com o fio vermelho no VSYS** (ver "Regra do USB"). Se precisar do cabo: amp fora da tomada, abrir,
  soltar o vermelho, e só então o USB. Um diodo Schottky 1N5817 no fio vermelho (anodo no LCD, catodo no VSYS) acabaria
  com essa regra.
- O Pico fica ligado sempre que o amp estiver na tomada (o 5 V existe também em standby).
- **O `r` de "Air" não é gravado**: ligado pelo amp, o Pico liga junto com ele e ainda está iniciando quando o
  controlador grava os desenhos (logo depois de ligar no botão de força; do standby ele não grava). Sem o desenho, a
  página avisa e a entrada DAB mostra "DAB". REGA e TAPE não usam desenho. Para ter o "Air": alimentar o Pico por um
  carregador USB próprio (sem o fio vermelho), escolher um nome sem desenho (a página e o `tools/planejador.py`
  dizem), ou, no futuro, gravar o desenho com o amp já ligado (ideia em `opcoes-intercepcao.md`).

## Regra de segurança do programa

GP2–GP12 recebem 5 V do amp. Eles **nunca** podem ser saída com valor 1 (isso brigaria com o controlador).
`firmware/sniffer.py` deixa todos como entrada. As experiências futuras (ver `opcoes-intercepcao.md`) só podem **puxar
para 0**: valor de saída fixo em 0, trocando apenas a direção do pino.

## Como o programa escuta

- **PIO** (`sniffer.py`): a cada descida do E, lê os 11 fios e põe a palavra na fila.
- **DMA**: copia a fila, sem parar, para um buffer circular de 4096 palavras (umas 30 telas). Nada se perde enquanto o
  Python cuida do Wi-Fi.
- **`hd44780.py`**: mantém uma cópia da memória do LCD. Depois de 2 ms sem escritas, a tela está completa e vai para o
  `amp_state` e para a página.
- Testes: `tools/test_sniffer.py` (no computador, com as capturas `.lac`) e `tools/teste_sniffer_pico.py` (no Pico, sem
  o amp, simulando o controlador só puxando os pinos para 0). Os dois passam.
- Detalhe do RP2350 (errata E9): o pull-down interno não consegue baixar um pino que já esteve em 1. Não afeta a escuta,
  porque o amp define todos os níveis com força; só o teste no Pico precisou simular o nível 0 puxando o pino.

## Página do barramento: `http://sp103.local/bus`

Se `sp103.local` demorar ou não abrir (aconteceu em 2026-10-24), use o IP do Pico: `http://192.168.178.108/bus`.
O IP aparece no roteador ou na mensagem "Wi-Fi ok" do Pico.

Para conferir a escuta no amp e guardar o que o controlador escreveu (programa: `firmware/buslog.py`).

- **Estatísticas** (atualizam a cada 2 s): palavras lidas, escritas, leituras do busy flag, telas, telas que o leitor
  não reconheceu, quantas vezes o amp ligou ("clear display"), maior pausa da leitura e maior lote.
  Se o "Biggest batch" ficar vermelho (3000 palavras ou mais numa leitura só), algumas palavras podem ter se perdido.
- **Download log (CSV)**: as últimas 8192 palavras (umas 50 telas), da mais antiga para a mais nova, com o horário
  local. O Pico acerta o relógio pela internet ao conectar no Wi-Fi; sem internet, a coluna do horário fica vazia, mas
  a coluna `ms` (relógio interno) continua.
- **Clear log**: zera o registro e as contagens, para começar um teste limpo.

Como analisar um teste no amp, passo a passo:

1. Abra `http://sp103.local/bus` no celular ou no computador e toque em **Clear log**.
2. Faça o que quer estudar no amp (girar o volume, trocar a entrada, abrir o menu Function) e anote a hora.
3. Toque em **Download log (CSV)**. O arquivo (`sp103-bus-<data>-<hora>.csv`) abre no Numbers ou no Excel.
4. Para ver as telas que o Pico montou, com o horário de cada uma:

   ```sh
   python3 tools/ler_bus.py ~/Downloads/sp103-bus-2026-10-24-1628.csv
   python3 tools/ler_bus.py ~/Downloads/sp103-bus-2026-10-24-1628.csv --palavras   # cada palavra também
   ```

O horário de cada palavra é o da leitura pelo programa, que pega as palavras em lotes (a cada ~1 ms). Palavras do mesmo
lote têm o mesmo horário, mas a ordem é sempre a certa. Para tempos finos (µs), continue usando o analisador lógico.

Testes: `tools/test_buslog.py` (no computador) e `tools/teste_bus_pico.py` (no Pico, sem o amp: um "amp de mentira"
escreve uma tela de volume a cada 2 s enquanto a escuta roda).

## Atualizar o programa sem o cabo

Ver `atualizacao-wifi.md`: `python3 tools/enviar.py`, com senha e volta automática para a versão anterior.

## Ainda em aberto

- **Saber quando o amp vai para standby**: ao desligar, o controlador não escreve nada no display. Ao ligar, ele manda
  "Clear display" (o programa avisa no log serial). Falta achar um sinal de standby (talvez a luz de fundo, pino 15/16).
