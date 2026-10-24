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
