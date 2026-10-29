# Roteiro de captura: o que o controlador manda para o display

> **Concluído em 2026-10-23.** Os resultados estão em `docs/descobertas-protocolo.md`. Fica como registro. O display
> já não está mais ligado ao controlador (`docs/proxy-ligacao.md`).

**Objetivo:** gravar **tudo** o que o controlador do SP103 envia ao LCD (ao ligar, ao trocar de entrada,
ao mexer no volume, no botão Function…). Com isso montamos o "dicionário" completo de comandos e textos.
Depois desmontamos tudo, fechamos o amplificador e seguimos para a bancada, com o display reserva.

**Nada é cortado nem soldado.** Os fios são só encaixados nos pininhos do LCD.

Mapa de pinos e detalhes técnicos: `docs/ligacao-analisador.md`.

---

## Parte 0: o que separar

- [X] Pico 2 W (já com o firmware do analisador) e cabo USB **de dados**
- [X] Mac com o LogicAnalyzer (`tools/logicanalyzer/abrir.sh`), **na bateria** (carregador fora da tomada)
- [X] Protoboard de 830 furos
- [X] **12 jumpers fêmea-fêmea** de uns 20 cm (11 sinais + 1 GND)
- [ ] (Opcional) **11 resistores de 1 kΩ** (marrom, preto, vermelho). Servem só de seguro; dá para fazer sem
      eles, seguindo à risca a ordem da Parte 3.
- [X] Fita crepe e caneta, para etiquetar os fios
- [X] Celular para tirar fotos de cada etapa
- [X] Amplificador já aberto, com o painel frontal solto, como nas suas fotos

---

## Parte 1: montar o Pico na protoboard (longe do amplificador)

1. Encaixe o Pico na protoboard **atravessando o canal central**: uma fileira de pinos de cada lado,
   com o USB virado para a ponta da protoboard.
2. **Resistores em pé:** para cada um dos 11 sinais, encaixe um resistor de 1 kΩ **em pé** num furo livre
   ao lado do pino do Pico. A perna de baixo vai no furo; a de cima fica para o alto.
   O jumper fêmea vai encaixado nessa perna de cima.

   ```
        jumper fêmea  →  vai para o pino do LCD
             │
             ▓  ← perna de cima do resistor
             █  resistor 1 kΩ (em pé)
             │
      ───────●──────────●  pino do Pico (mesma fileira da protoboard)
   ```

   Use a tabela abaixo. Os pinos 4 a 16 do Pico ficam todos do mesmo lado, logo depois do pino 3 (GND).

   | Etiqueta do fio | Pino físico do Pico (GPIO) | Vai no pino do LCD | Com resistor? |
   |---|---|---|---|
   | **GND** | 3 (GND) | 1 | **não**, ligação direta |
   | **E** | 4 (GP2) | 6 | sim |
   | **RS** | 5 (GP3) | 4 | sim |
   | **RW** | 6 (GP4) | 5 | sim |
   | **D0** | 7 (GP5) | 7 | sim |
   | **D1** | 9 (GP6) | 8 | sim |
   | **D2** | 10 (GP7) | 9 | sim |
   | **D3** | 11 (GP8) | 10 | sim |
   | **D4** | 12 (GP9) | 11 | sim |
   | **D5** | 14 (GP10) | 12 | sim |
   | **D6** | 15 (GP11) | 13 | sim |
   | **D7** | 16 (GP12) | 14 | sim |

   Repare que os pinos 8 e 13 do Pico são GND: eles ficam **sem fio**.

3. **GND:** encaixe um jumper fêmea-macho (ou um macho-macho com um fêmea-fêmea emendado) na fileira do
   pino 3 do Pico. Esse fio vai **direto** ao pino 1 do LCD, sem resistor.
4. **Etiquetas:** cole uma etiqueta de fita crepe na ponta solta de cada fio (E, RS, RW, D0…D7, GND).
5. **Foto:** tire uma foto da protoboard montada.

> **Sem resistores (o seu caso):** pule o passo 2. Use jumpers **fêmea-macho**: a ponta macho vai num furo livre
> da protoboard, na fileira do pino do Pico, e a ponta fêmea vai no pino do LCD. Se só tiver fêmea-fêmea, tire o Pico
> da protoboard e encaixe a fêmea direto no pino dele.
> O Pico aguenta os 5 V **desde que esteja ligado no USB antes do amplificador** (Parte 3). Os resistores eram só
> um seguro caso essa ordem falhe. Sem eles, a ordem passa a ser **obrigatória**.

---

## Parte 2: ligar os fios no LCD (amp FORA DA TOMADA)

1. **Confirme** que o cabo de força do amplificador está **fora da tomada**.
2. **Marque o pino 1:** é o pininho da **ponta esquerda** da fileira do LCD, olhando o display de frente
   (o lado mais perto do trimpot de contraste). Cole um pedacinho de fita na placa ao lado dele.
3. **Conte os pinos** a partir dele: 1, 2, 3… até 16. Na sua foto IMG_0777, eles ficam no vão entre a placa do LCD
   e a placa de controle.
4. **Encaixe os jumpers na ordem.** Comece pelo **GND no pino 1**, depois:

   | Pino do LCD | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
   |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
   | Fio | **GND** | ✖ livre | ✖ livre | **RS** | **RW** | **E** | **D0** | **D1** | **D2** | **D3** | **D4** | **D5** | **D6** | **D7** | ✖ livre | ✖ livre |

   ⚠️ **Pino 2 = +5 V: nunca encaixe nada nele.**

5. **Verificação:**
   - [ ] Cada conector fêmea entrou **até o fim** e ficou firme (puxe de leve).
   - [ ] Nenhum conector encosta no pino vizinho (o pino 2, principalmente).
   - [ ] Os fios não forçam nem entortam os pininhos. Prenda o feixe com fita na mesa se precisar.
   - [ ] A protoboard com o Pico fica **apoiada fora do amplificador**, sobre papelão ou madeira, sem encostar no chassi.
6. **Foto:** tire uma foto dos fios encaixados no LCD.

---

## Parte 3: ligar na ordem certa

**Sempre nesta ordem:**

0. **Impeça o Mac de dormir** (se ele dormir, pode cortar a energia do USB enquanto o amp está ligado).
   Abra um terminal e rode o comando abaixo. Deixe essa janela aberta durante todas as capturas;
   para encerrar, aperte Ctrl+C.
   ```
   caffeinate -dis
   ```
   Prenda também o cabo USB com fita, para não ser puxado sem querer.
1. Ligue o **Pico no USB** do Mac.
2. Abra o programa: `tools/logicanalyzer/abrir.sh`.
3. Escolha `/dev/cu.usbmodem…` (ou `tty.usbmodem…`) e clique em **Open device**.
   Deve aparecer `LOGIC_ANALYZER_PICO_2_V6_0`.
4. **Só agora** ligue o amplificador na tomada. A tela dele deve acender normalmente,
   porque os fios só "escutam" e não mudam nada.

Se a tela do amplificador ficar estranha (apagada ou com lixo): desligue o amp da tomada e confira os fios.

---

## Parte 4: configurar a captura (uma vez só)

Clique em **Capture** e ajuste:

- **Canais:** marque **Channel 1 a Channel 11**. Nos campos abaixo de cada um, escreva os nomes:
  `E, RS, RW, D0, D1, D2, D3, D4, D5, D6, D7`. O script usa esses nomes.
- **Presamples:** 512
- **Postsamples:** o **máximo** que o programa aceitar (cerca de 190000). Se der erro, diminua até ele aceitar.
- **Edge trigger:** canal **01** (E), com **Negative edge DESMARCADO**.
  ⚠️ Neste firmware o "edge trigger" na verdade dispara pelo **nível**: desmarcado, dispara quando o E está em **1**.
  Como o E fica em 0 no repouso, a captura espera o primeiro pulso. Com "Negative edge" marcado, ela dispararia
  **na hora** (o E já está em 0), antes de você fazer qualquer coisa. Foi o que aconteceu no primeiro teste
  (`captures/volume.lac`).
- **Frequency:** depende da captura (veja a tabela da Parte 5).

O programa lembra esses ajustes nas próximas vezes. Depois é só trocar a frequência quando a tabela pedir.

**Como funciona cada captura:**
1. Clique em **Capture → Accept**. O programa fica **esperando**.
2. Faça a ação no amplificador (apertar o botão, girar o knob…).
3. A captura dispara sozinha no primeiro pulso do E e aparece na tela.
4. Salve com **File → Save** na pasta `captures/`, com o nome da tabela.

Se nada acontecer em uns 10 segundos, clique em **Abort**. Isso também é uma informação: anote.

**Disparou no mesmo instante do Accept, antes de você mexer em algo?** Então o trigger está errado
(confira se "Negative edge" está desmarcado) ou o controlador estava escrevendo sozinho. Teste
clicando em Accept e esperando, sem tocar no amp.

---

## Parte 5: as capturas

Faça na ordem. **A captura 1 decide a frequência das outras.**

| # | Arquivo | Frequência | Ação no amplificador | O que responde |
|---|---|---|---|---|
| 1 | `01-pulso-e.lac` | 25 MHz | Gire o volume um "clique" | a largura do pulso E, para escolher a frequência das próximas |
| 2 | `02-parado.lac` | F | **Não toque em nada** por 10 s (Abort se não disparar) | o controlador redesenha a tela sozinho? |
| 3 | `03-liga.lac` | F | Com a captura esperando, **ligue o amp na tomada**. Antes disso, desligue-o da tomada; o Pico continua no USB | sequência de inicialização |
| 4 | `04-phono.lac` | F | Aperte **Phono** | texto da entrada |
| 5 | `05-tuner.lac` | F | Aperte **Tuner** | |
| 6 | `06-tape.lac` | F | Aperte **Tape/Aux** | |
| 7 | `07-cd.lac` | F | Aperte **CD** | |
| 8 | `08-dvd.lac` | F | Aperte **DVD** | |
| 9 | `09-dab.lac` | F | Aperte **DAB** | |
| 10 | `10-vol-sobe.lac` | F | Gire o volume **para cima** um clique | como o volume é escrito |
| 11 | `11-vol-desce.lac` | F | Gire o volume **para baixo** um clique | |
| 12 | `12-vol-rapido.lac` | F | Gire o volume **rápido**, vários cliques | redesenha a cada clique? |
| 13 | `13-function-1.lac` | F | Aperte **Function** uma vez | menus (grave, agudo, balanço?) |
| 14 | `14-function-2.lac` … | F | Aperte **Function** de novo, uma captura por toque, até voltar à tela normal | todos os menus |
| 15 | `15-function-ajuste.lac` | F | Dentro de um menu do Function, gire o knob | como os valores do menu são escritos |
| 16 | `16-controle.lac` | F | (se tiver o controle remoto) aperte um botão do controle | |
| 17 | `17-desliga.lac` | F | Com a captura esperando, **desligue o amp na tomada** | o que é escrito ao desligar (se algo for) |

**Como escolher F** (depois da captura 1): rode o script nela (Parte 6) e veja a linha "Largura do pulso E: mín …".

| Pulso E mais curto | F |
|---|---|
| 1,5 µs ou mais | 2 MHz (captura cerca de 98 ms) |
| 0,75 a 1,5 µs | 4 MHz (cerca de 49 ms) |
| menos de 0,75 µs | 10 MHz (cerca de 19 ms) |

Se você não quiser esperar o script, use **4 MHz**: é o valor mais provável.

**Captura cortada no meio?** Se a tela reconstruída pelo script ficar incompleta, a captura terminou antes de o
controlador acabar de escrever. Repita a mesma ação com uma frequência menor (por exemplo, 2 MHz).

---

## Parte 6: rodar o script

No terminal, na pasta do projeto:

```
python3 tools/hd44780_decode.py captures/01-pulso-e.lac
```

Para salvar o resultado de todas as capturas de uma vez:

```
for f in captures/*.lac; do python3 tools/hd44780_decode.py "$f" > "${f%.lac}.txt"; done
```

Ou só me avise que as capturas estão na pasta: eu rodo o script em todas e monto o dicionário.

---

## Parte 7: desmontar e fechar

1. **Primeiro** desligue o amplificador **da tomada**.
2. Clique em **Close device** no programa e tire o USB do Pico.
3. Retire os jumpers do LCD **um por um**, puxando reto, sem entortar os pininhos.
4. Confira com uma foto que nenhum pininho ficou torto.
5. Recoloque o painel frontal e feche o amplificador.
6. Ligue e confira se tudo funciona como antes.

---

## O que vem depois: a bancada

Com o dicionário pronto, montamos na protoboard, **fora do amplificador**:

1. **Pico 2 W + display reserva (1602):** o Pico faz o papel do controlador e reproduz exatamente as sequências
   capturadas. Se o display reserva mostrar "Volume -26.25 dB / PHONO", entendemos tudo certo.
2. **Camada de reescrita:** o mesmo Pico troca os textos ("PHONO" → "Turntable") e testa mensagens
   personalizadas.
3. **Decidir a instalação final:** cortar só o E ou os 11 pinos, com base no que as capturas mostraram sobre
   o **repouso** dos fios (o script mostra isso no começo de cada resultado).
