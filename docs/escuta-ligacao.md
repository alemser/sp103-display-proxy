# Etapa 4: ligar o Pico no amp para só escutar

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

## Ainda em aberto

- **Saber quando o amp vai para standby**: ao desligar, o controlador não escreve nada no display. Ao ligar, ele manda
  "Clear display" (o programa avisa no log serial). Falta achar um sinal de standby (talvez a luz de fundo, pino 15/16).
