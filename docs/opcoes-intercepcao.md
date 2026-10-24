# Como o Pico pode mudar o texto do display do amp (opções de interceptação)

Análise de 2026-10-23. **Ainda não há decisão**: o dono está pensando.

Para **só ler** o estado e publicar no Wi-Fi (etapa 4), nada disso é necessário. O Pico apenas escuta os pinos do display,
como nas capturas. As pontas dos pinos, que sobram acima da placa do display (ver foto abaixo), aceitam
**Dupont fêmea** direto, sem solda.

Para **mudar o texto** (etapa 6: "Turntable", textos ao ligar), o Pico precisa ficar **no meio** entre o controlador e o
display.

## Por que "sobrescrever em paralelo" não funciona

A ideia era deixar tudo ligado como está e o Pico reescrever o display logo depois do controlador, rápido o bastante
para ninguém perceber. Isso não dá, por motivo elétrico:

- **E (perna 28, P2.7):** no repouso, o controlador segura o E em 0 com força. A porta é quase-bidirecional e puxa
  para 0 com um transistor. Se o Pico levantasse o E, os dois brigariam pelo fio: o Pico perderia, e o Pico ou o
  controlador poderiam se danificar.
- **Dados (pernas 32–39, P0):** no repouso, ficam presos no último byte escrito (capturas). Os bits em 0 são segurados
  com força pelo controlador; os resistores de 4,7 kΩ (R907/R908) só puxam para 5 V os bits em 1. O Pico conseguiria
  baixar uma linha, mas não levantar.

Não existe uma janela em que o Pico escreva sozinho sem brigar com o controlador.

## O que as fotos mostraram

| Foto | O que mostra |
|---|---|
| ![controlador](img/minha-placa/controlador-t9311-sem-soquete.jpg) | O T9311 está **soldado direto na placa, sem soquete** |
| ![lateral](img/minha-placa/lcd-pinos-lateral.jpg) | O display está preso por uma barra de 16 pinos, soldada nas duas placas, com um **espaçador de plástico** entre elas. As pontas dos pinos sobram acima da placa do display |
| ![solda](img/minha-placa/lcd-lado-solda-trilhas.jpg) | No lado das soldas, sai **uma trilha de cada pino**, ainda separadas umas das outras logo depois da solda. Mais adiante elas se juntam num feixe fino até o controlador |

## Opções

| # | Opção | Veredito |
|---|---|---|
| 1 | Adaptador no lugar do controlador (soquete "sanduíche" de 40 pinos) | **Descartada**: o chip está soldado; seria preciso desoldar 40 pernas |
| 2 | **Cortar 11 trilhas** no lado das soldas, logo depois dos pinos do display | **A menos intrusiva**: o display não é tocado nem desoldado, e nada muda de lugar no painel |
| 3a | Cortar os pinos entre as placas | **Inviável**: o espaçador de plástico não deixa o alicate entrar |
| 3b | Desoldar as 16 soldas de baixo e soltar o display com a barra de pinos, que fica presa a ele; soldar uma barra fêmea na placa | Possível, mas o display ficaria mais alto (a altura da plaquinha do Pico), e talvez não caiba atrás da janela do painel |

## Atualização (2026-10-24): o que dá para fazer em paralelo, só puxando para 0

A conclusão acima vale para escrever **qualquer** texto. Mas o Pico consegue algumas coisas sem cortar nada, desde que
**só puxe linhas para 0** (nunca mande 1):

| Truque | Como | Seguro sem resistor? |
|---|---|---|
| Mudar bits das letras | D0–D7 só vão a 1 pelos pull-ups de 4,7 kΩ: o Pico pode transformar qualquer 1 em 0 | sim (~1 mA) |
| Bloquear uma escrita | segurar o E em 0 durante o pulso | só se o E for fraco no 1 (teste abaixo) |
| Injetar um comando | nas leituras de busy flag (antes de cada comando e de cada letra), segurar o RW em 0: o LCD recebe uma escrita com o byte que o Pico deixar no barramento | só se o RW for fraco no 1 |

Limite: o Pico só **apaga bits**. Dá para mover, apagar ou esconder texto, mas não criar letras com bits que o
controlador não mandou ("PHONO" + espaços não vira "Rega Planar 2"). Trocar nomes livremente continua exigindo o corte.
As experiências servem para aprender como o controlador reage.

**Teste antes (multímetro):** em corrente contínua, escala 20 mA, entre o pino 1 (GND) e o pino 4 (RS, que fica em 1 no
repouso), por 1 segundo, com o amp ligado. Menos de 1 mA = porta fraca, os truques 2 e 3 são seguros. Mais de 5 mA =
porta forte: soltar na hora, só o truque 1 é seguro. Depois, voltar o multímetro para tensão.

A ligação é a mesma da escuta (`escuta-ligacao.md`); muda só o programa.

### Medições do dono (2026-10-24, amp em standby; iguais com o amp ligado)

| Fio | Tensão | Corrente para o GND (escala 2 mA) | Conclusão |
|---|---|---|---|
| RS | 4,94 V | 0,168 mA | **fraco no 1** (pull-up fraco do 8051): o Pico pode puxar para 0 |
| RW | 0,00 V | 0,057 mA | está em 0 no repouso; não diz nada sobre o RW em 1 (só dura ~20 µs, nas leituras) |
| E | 0,03 V | 0,306 mA | **segurado em 0 com força**: o Pico nunca levanta o E |

O RW fica na mesma porta do RS (P3.1 e P3.0), então provavelmente também é fraco no 1, mas o T9311 não tem folha de
dados: falta testar. Nas capturas, o RW sobe ~21 µs antes do E (folga para o Pico agir).

### Resultado do teste 1 no amp (2026-10-24)

- **O RW é fraco no 1**: o Pico puxou com 2 mA e o fio desceu. O controlador seguiu normal. Puxar o RW é seguro.
- **Mas o controlador não solta o barramento inteiro para ler o busy flag**: ele solta só o D7. Os outros fios ficam
  presos no último byte escrito. O byte injetado foi 0xD6 = o caractere 'V' (0x56) com o bit 7 ligado.
- Confirmado também: com o bit 7 em 1 ("ocupado"), o controlador pergunta de novo e depois segue normal.

Consequência: o comando injetado é sempre **o último byte com o bit 7 ligado, menos os bits que o Pico zerar**. Não dá
para injetar qualquer comando. Desviar uma letra só funciona para um endereço que seja um "pedaço" (subconjunto de bits)
do endereço original (da coluna 6 da linha 2, 0x45, dá para ir a 0x40, 0x05, 0x04, 0x01, 0x00). Montar nomes na área
escondida, como descrito abaixo, **não é viável**. Mas há mais truques; ver "Opções para mudar os caracteres" logo abaixo.

### Opções para mudar os caracteres, sem corte (análise de 2026-10-24)

Todas só puxam fios para 0. "Fonte" = o caractere que o controlador está escrevendo naquele momento.

| # | Opção | Como | Fios | Falta testar |
|---|---|---|---|---|
| A | Trocar letra por letra | zerar bits do caractere ("PHONO" → "PHONE") | dados | — |
| B | Desenhos próprios | ao ligar, o controlador grava 8 desenhos (64 bytes) e nunca mais mexe. Os desenhos 1–7 (barras) nunca aparecem nas telas: zerando pontos das linhas cheias (0x1F), viram letras ou ícones. O 7 tem as linhas 1–7 cheias (letra 1 ponto mais baixa), o 6 as linhas 2–7 (minúsculas). Mostrar o desenho k: zerar bits de uma fonte que tenha os bits de k | dados | reconhecer o início do amp e aplicar 64 máscaras, 2 vezes (o controlador repete 64 ms depois) |
| C | Mover letras | na leitura depois de uma letra, injetar "vá para a célula Y" (Y contido nos bits da letra anterior; um 'o' alcança qualquer coluna da linha 2) e zerar o comando de endereço do controlador (vira 0x00, que não existe) | RW + dados | se o LCD ignora o comando 0x00 |
| D | Congelar células | transformar a escrita do controlador em comando 0x00 (puxar o RS e zerar os dados) | RS + dados | idem |
| E | Comandos de tela | piscar, cursor, deslocar ou apagar a tela (comandos contidos nos bits da fonte) | RW + dados | — |

O ponto fraco: **na troca de entrada, o controlador redesenha a tela uma vez só** (32 caracteres), e só volta a
redesenhar quando alguém mexe no volume. O nome precisa sair inteiro desse redesenho, usando como fontes as letras da
linha 1 (que não mudam: "Volume", "dB"), as do nome original e os espaços. O tempo para cada decisão é de ~20 µs (PIO com
tabelas prontas).

**Planejador** (`tools/planejador.py`): diz se um nome sai inteiro, em quantos dos 64 volumes, e com quais desenhos.
Com os nomes configurados no Pico (2026-10-24):

| Entrada | Nome | Resultado |
|---|---|---|
| DAB | Streaming | não sai: `S t r e n g` sem fonte possível nas suas posições |
| TUNER | Rega Planar 2 | não sai: `a a n r 2` |
| TAPE/AUX | Yamaha KX-393 | não sai: `Y a K X - 3 9 3` |
| CD | Yamaha CD-S303 | não sai: `Y a C - S 3 3` |

Juntos, eles precisariam de 15 desenhos próprios (o limite é 7), e nem montando aos poucos, em vários redesenhos, eles
completam. **Nomes curtos funcionam**: "Mac" e "TV" sem desenho nenhum; "Rega", "Yamaha" e "Vinil" com 7 desenhos. "Stream"
não. Isso ainda supõe que o comando 0x00 é ignorado e que os desenhos (por exemplo, o `Y`) cabem nas linhas disponíveis.

Conclusão: sem corte, só nomes curtos (até ~6 letras, escolhidos com o planejador). Os nomes longos atuais exigem o
corte das trilhas.

Segunda rodada (nomes curtos propostos pelo dono), com o formato real dos desenhos (maiúsculas só no desenho 7):

| Entrada | Proposto | Resultado | Alternativa que sai |
|---|---|---|---|
| TUNER | Rega | não sai: o `a` não alcança a coluna 4 | **REGA** ou **RegA** (sem desenhos) |
| TAPE/AUX | Tape | não sai: `p` e `e` nas colunas 3 e 4 | **TAPE** (sem desenhos) |
| DAB | AP/BT | não sai: `P` não cabe na coluna 2, `B` na 4, e só há um desenho para maiúscula | **Air** (desenho próprio para o `r`), **Mac** |
| about | Oceano Amplifier / SP103 | não sai (20 de 32 células); nenhuma variante testada sai | manter o original |

**Nomes escolhidos pelo dono para o caminho sem corte (2026-10-24): REGA (TUNER), TAPE (TAPE/AUX), Air (DAB).**

### Teste 2: o LCD ignora o comando 0x00? Sim (`tools/teste_nop_pico.py`, 2026-10-24)

O Pico zerou os 8 fios de dados durante o comando "vá para a linha 2, coluna 1" (0xC0) do controlador. O LCD recebeu 0x00
e **não fez nada**: continuou no endereço seguinte (a coluna 17 da linha 1, escondida), e a primeira letra do nome novo
foi parar lá. Trocando de TUNER para DAB, o display mostrou "**T**AB". O controlador seguiu normal. Girar o volume
consertou a tela. Os truques C e D funcionam.

Detalhes do programa:
- Lê o barramento na **subida** do E (o controlador já pôs RS, RW e os dados; conferido nas capturas e com
  `tools/diag_subida_pico.py`) e segura os fios até a descida, com o mesmo filtro de ruído do sniffer.
- No MicroPython, `mov(pindirs, ...)` gera o mesmo código que `mov(exec, ...)` (0xA083): o PIO executa o valor como
  instrução. A direção dos pinos só muda com `out(pindirs, n)` ou `set(pindirs, n)`. Na primeira tentativa, isso
  prendeu o programa num laço, e ele nunca reconheceu o 0xC0.
- O teste só aparece no display se as duas entradas começarem com letras diferentes (TUNER → TAPE/AUX não mostra nada).

### Teste 4: mover uma letra da linha 1 para a linha 2. Funciona (`tools/teste_mover_pico.py`, 2026-10-24)

Três passos num redesenho, todos só puxando fios para 0 (2 mA):
1. Na leitura logo depois do 'V', puxar o RW e zerar D1, D2 e D4: o LCD recebe 0xD6 menos esses bits = **0xC0** ("vá para
   a linha 2, coluna 1"). O controlador lê "ocupado" e pergunta de novo.
2. O comando seguinte do controlador (0x81) vira 0x00 (ignorado): o 'o' cai na linha 2, coluna 1.
3. O 0xC0 do controlador, mais adiante, vira 0x00: a primeira letra do nome vai para a coluna escondida, e o 'o' fica.

Resultado no amp, trocando para TAPE/AUX: **"oAPE/AUX"**, com a linha 1 intacta (a célula do 'o' não foi reescrita). O
redesenho atrasado consertou a tela. O programa PIO é genérico: uma fila de passos (palavra que dispara, fios a puxar, "agora"
ou "na próxima leitura"), 29 instruções no PIO1. O programa final pode usar o mesmo formato.

### Teste 3: criar um desenho próprio ao ligar. Funciona (`tools/teste_desenho_pico.py`, 2026-10-24)

1. Desligar e ligar o amp **no botão de força**: só assim ele refaz a sequência completa ("ACOUSTIC SOLUTIONS" e a
   gravação dos 8 desenhos, duas vezes com 64 ms de intervalo). Voltar do standby não grava os desenhos.
2. O Pico espera o "Set CGRAM 0x40", conta 50 bytes e, nas linhas 2 a 7 do desenho 6, zera os pontos que não fazem
   parte do `r`. Nas duas gravações, o desenho saiu exatamente como o `r` da fonte do LCD.
3. Na tela normal, o 'V' (0x56) com D4 e D6 zerados vira 0x06: a linha 1 mostrou **"rolume"**, e ficou assim. O Pico também
   tratou o redesenho atrasado. O desenho vale até o amp desligar.

`tools/teste_mostrar_pico.py` é a mesma coisa sem a gravação (para quando o desenho já está no LCD).

**Os quatro truques (A, B, C, D) funcionam no amp.** Falta o programa final, em tempo real.

### Armadilhas do PIO (para o programa final)

Cada uma custou pelo menos uma tentativa nos testes:

| Armadilha | Sintoma | Como evitar |
|---|---|---|
| `mov(pindirs, ...)` no MicroPython gera o mesmo código que `mov(exec, ...)` | o PIO executa o valor como instrução e trava num laço | mudar a direção dos pinos só com `out(pindirs, n)` ou `set(pindirs, n)` |
| `autopull=True` faz o `pull()` não fazer nada se o OSR estiver cheio | a fila sai desalinhada (o 1º valor vira o 2º) | sem autopull; `pull(ifempty)` quando precisar |
| O padrão do MicroPython é `out_shiftdir=SHIFT_LEFT` | `out()` pega os bits do topo do OSR; a máscara nos bits baixos não puxa nada | sempre `out_shiftdir=SHIFT_RIGHT` |
| Ruído no E (fios longos; o E é fraco em 1) | pulsos falsos e "piscadas" no meio do pulso: contagem adiantada, puxar e soltar fora de hora | aceitar a subida só depois de 3 µs em 1; soltar só depois de 1,7 µs em 0 (a mesma regra do `sniffer.py`). Para contar pulsos, uma máquina só de filtro avisa por IRQ |
| Cada bloco PIO tem só 32 instruções | `ENOMEM` ao carregar | o sniffer (com filtro) fica no PIO0; a escrita, no PIO1 |

Cada coluna aceita poucos caracteres: `python3 tools/planejador.py --paleta DAB` mostra a lista. As colunas 4 e 8 da linha 2
são as mais restritas (`␣$(,@DHL`dhl` para o DAB).

O plano abaixo foi escrito antes do teste e fica como registro.

### O que parecia possível antes do teste (se o RW fosse fraco)

- **Injetar qualquer comando**: na leitura do busy flag, o controlador solta os dados (pull-ups = 0xFF) e põe o RW em 1.
  O Pico puxa o RW para 0 e zera os bits que quiser: o LCD recebe uma escrita (RS=0) com o byte do Pico. O controlador
  lê esse mesmo byte como busy flag: com o bit 7 em 1, ele acha que o LCD está ocupado e pergunta de novo (o Pico ganha
  mais chances, e o controlador espera).
- **Mudar o lugar de cada caractere**: entre o "Set DDRAM addr" do controlador e o caractere há uma leitura; nela o
  Pico injeta outro endereço.
- **Não dá para criar bits**: caracteres (RS=1) só saem das escritas do controlador, com bits zerados. Juntando todas
  as telas (incluindo as de ligar e os menus), dá para obter os símbolos e números, `A`–`W` e `a`–`v`; faltam
  `w x y z X Y Z ; = ? [ ] ^ _ { | } ~` e a barra invertida. "Streaming", "Turntable" e "Rega Planar 2" são possíveis;
  "Spotify" não (falta o `y`).
- Para trocar um nome, as letras precisariam ser juntadas aos poucos nas colunas escondidas (17 a 40) do LCD e mostradas
  com o comando "shift". O "Clear display" ao ligar apaga tudo, e cabem só 1 ou 2 nomes. É possível, mas complexo e
  frágil; cortar as trilhas dá liberdade total.

### Teste 1: o RW é fraco no 1? (`tools/teste_rw_pico.py`)

Amp ligado, fio do VSYS solto, Pico no USB: `.venv/bin/mpremote run tools/teste_rw_pico.py` e girar o volume um passo.
O Pico puxa o RW **uma vez só**, na leitura logo depois de um caractere, com a saída na força mínima (2 mA) e só se o E
ainda estiver em 0. O LCD recebe um "Set DDRAM addr" inofensivo (o controlador manda o endereço dele logo depois), e a
escuta mostra se o RW desceu. O teste do RW usa o PIO1, porque o sniffer com o filtro de ruído ocupa o PIO0.

Antes do teste, os fios soldados (mais longos) faziam a borda do E "tremer", e o sniffer contava pulsos a mais. O
`sniffer.py` agora tem um filtro: só vale um pulso do E com 3 µs ou mais (os reais têm 10 µs ou mais). Com ele, 1408
palavras saíram sem nenhum erro.

## Opção 3b, variação: desoldar e dobrar ou cortar os pinos 4–14

Ideia do dono, a partir de uma sugestão do ChatGPT (soquete de perfil baixo): desoldar as 16 soldas de baixo, soltar o
display e, nos pinos 4–14, impedir que entrem na placa de baixo. Depois soldar de novo só os pinos 1–3, 15 e 16.

- Os furos vazios 4–14 da placa de baixo viram o ponto de solda do lado do controlador (mais fácil que as pernas do
  T9311); o lado do display continua nas pontas de cima dos pinos.
- **Dobrar**: o pedaço tem só ~3 mm e fica preso entre o espaçador e a placa, então não serve para ligar nada; o display
  sobe ~0,7 mm. Vantagem: dá para desdobrar e soldar de novo (uma vez só).
- **Cortar rente ao espaçador**: altura igual, mas para voltar ao original precisa de uma barra nova.
- A placa de baixo parece ser de fenolite, de uma face: as ilhas soltam com calor. Por isso cortar as trilhas (opção 2)
  continua sendo o menos arriscado.
- Soquete de perfil baixo (ChatGPT): só faz sentido se a folga entre as placas permitir; falta medir a altura do espaçador.

## Interceptado: o que vai ao Pico

Depois do corte, cada um dos 11 fios fica em dois pedaços:
- **Lado do controlador: os 11** (RS, RW, E, D0–D7), em GP2–GP12, como na escuta. O Pico finge ser o display e precisa
  responder às leituras do busy flag (puxando as linhas para 0 = "livre"); sem resposta, os pull-ups dão "ocupado para
  sempre" e o controlador pode travar.
- **Lado do display: só 6** (RS, E, D4–D7) em GP16–21, modo 4 bits, com o RW do display (pino 5) ligado ao GND (pino 1),
  como na bancada. O display nunca manda sinal de volta, então não entra 5 V no Pico por esse lado.
- **Saída de emergência**: levar os dois lados (11 + 11) a uma barra de pinos. Com 11 jumpers ligando cada fio do
  controlador ao do display, o amp volta ao original sem o Pico.

## Opção 2 em detalhe: cortar trilhas

```
ANTES:  controlador ───────────trilha────────────── display

DEPOIS: controlador ───── ✂ ───────────────── display
             │       (corte)                     │
             └──fio──► Pico ──fio────────────────┘
          (solda na perna        (Dupont na ponta do pino,
           do T9311, embaixo)     em cima do display)
```

1. **Cortar 11 trilhas** com estilete, 1 a 2 mm depois da solda de cada pino do display: pinos 4 a 14 (RS, RW, E, D0–D7).
   Não mexer nas trilhas do GND (1), +5 V (2), contraste (3) e luz (15, 16).
2. **Lado do controlador:** um fio soldado em cada perna do T9311 correspondente, pelo lado das soldas:
   RS = 10, RW = 11, E = 28, D0–D7 = 39–32 (mapa em `ligacao-analisador.md`). Essas soldas são grandes e fáceis.
3. **Lado do display:** Dupont fêmea nas pontas dos pinos 4–14, em cima da placa do display. Sem solda.
4. **Para voltar ao original:** uma gota de solda ou um pedacinho de fio sobre cada corte.

Cuidados:
- O risco principal é cortar uma trilha vizinha. Corte onde as trilhas estão separadas (logo depois da solda), com lupa
  ou com a câmera do celular. Faça dois cortes paralelos e retire o cobre do meio.
- Depois de cada corte, confira com o multímetro (continuidade): entre o pino do display e a perna do controlador não
  pode mais apitar, e entre trilhas vizinhas também não.
- O display não recebe calor nem esforço.

Ainda falta, antes de cortar:
- Escrever um roteiro passo a passo: ordem dos cortes, medições antes e depois, e como desfazer.
- Parte elétrica da etapa 6: o Pico precisa responder às leituras do busy flag (puxando as linhas para 0, sem levantar,
  já que o P0 tem pull-ups de 5 V). As entradas do Pico vindas do controlador são de 5 V; elas só aguentam isso com o Pico
  alimentado, então a alimentação pelo 5 V do amp (pino 2 do display, com diodo) precisa ser pensada junto.
  Considerar resistores em série nessas entradas.
