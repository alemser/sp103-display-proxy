# Pico 2 W como analisador lógico

Software: [gusmanb/LogicAnalyzer](https://github.com/gusmanb/logicanalyzer) v6.0.

- `firmware/logic-analyzer-firmware_v6.0.0_BOARD_PICO_2.uf2`: o firmware que vai para o Pico.
- `app/`: o programa para Mac (Apple Silicon). Já está assinado localmente para o macOS deixar rodar.
- `abrir.sh`: abre o programa.
- `app/python.cfg`: aponta para o Python 3.13 (`brew install python@3.13`). Os decodificadores
  (I2C etc.) usam pythonnet 3.0.5, que **não** aceita Python 3.14. Sem esse arquivo, aparece o erro
  "Cannot load Sigrok decoders".

## Sobre o Pico 2 **W**

Não existe um firmware oficial para o "Pico 2 W". Usamos o do **Pico 2** (o mesmo chip, RP2350).
Ele funciona normalmente pelo USB. A única diferença é que **o LED da placa não acende**,
porque no modelo W o LED fica ligado ao chip de Wi-Fi. Isso é normal e não indica defeito.

## Passo 1: gravar o firmware (uma vez só)

1. Com o Pico **desconectado**, segure o botão branco **BOOTSEL**.
2. Ainda segurando o botão, ligue o cabo USB no Mac. Depois solte o botão.
3. Vai aparecer um "pendrive" chamado **RP2350** no Finder.
4. Arraste o arquivo `.uf2` da pasta `firmware/` para dentro dele.
5. O pendrive some sozinho. Pronto: agora o Pico é um analisador lógico.

Para voltar a usar o Pico com MicroPython depois, basta repetir o processo com o `.uf2` do MicroPython.

## Passo 2: testar a conexão

1. Pico ligado no USB (sem o botão).
2. Rode `./abrir.sh` (ou dê dois cliques em `app/LogicAnalyzer`).
3. No programa, escolha a porta serial `/dev/tty.usbmodem...` e clique em **Open**.
   Deve aparecer a versão do firmware e o nome da placa (`PICO_2`).

Teste sem amplificador: ligue um jumper do pino **GPIO2** a um pino **GND** e capture.
O canal 1 deve ficar em 0. Solte o jumper e o canal mostra ruído ou 1.

## Canais ↔ pinos do Pico

Canal N = GPIO(N+1). O pino físico é a posição na placa: pino 1 fica ao lado do USB, lado esquerdo.

| Canal | GPIO | Pino físico | Uso sugerido no SP103 |
|------:|-----:|------------:|-----------------------|
| 1  | GP2  | 4  | LCD pino 4: RS |
| 2  | GP3  | 5  | LCD pino 5: RW |
| 3  | GP4  | 6  | LCD pino 6: E |
| 4  | GP5  | 7  | LCD pino 7: D0 |
| 5  | GP6  | 9  | LCD pino 8: D1 |
| 6  | GP7  | 10 | LCD pino 9: D2 |
| 7  | GP8  | 11 | LCD pino 10: D3 |
| 8  | GP9  | 12 | LCD pino 11: D4 |
| 9  | GP10 | 14 | LCD pino 12: D5 |
| 10 | GP11 | 15 | LCD pino 13: D6 |
| 11 | GP12 | 16 | LCD pino 14: D7 |
| 12 | GP13 | 17 | 24C01 pino 5: SDA |
| 13 | GP14 | 19 | 24C01 pino 6: SCL |
| —  | GND  | 3, 8, 13, 18, 23, 28, 33, 38 | GND do amplificador (LCD pino 1) |

Os canais 14 a 21 são GP15 a GP22, e os canais 22 a 24 são GP26 a GP28.
GP0 e GP1 ficam reservados para o trigger externo. Não use.

## Segurança (sinais de 5 V)

O amplificador trabalha com 5 V e o Pico com 3,3 V. As entradas do RP2350 aguentam 5 V
**apenas enquanto o Pico está ligado**. Então siga esta ordem:

1. Amplificador **desligado da tomada**. Conecte os fios e o GND comum.
2. Ligue o Pico no USB do notebook (notebook **na bateria**).
3. Só então ligue o amplificador.
4. Para terminar, desligue **primeiro o amplificador** e só depois o USB do Pico.

Recomendado: coloque um **resistor de 1 kΩ em série** em cada fio de sinal, entre o
amplificador e o Pico. Ele protege o Pico se a ordem acima falhar e não atrapalha a medição.

## Teste validado (2026-10-22): I2C do Raspberry Pi 5

Pi 5 pino 3 (SDA) → Pico pino 4 (GP2, canal 1). Pi 5 pino 5 (SCL) → Pico pino 5 (GP3, canal 2).
Pi 5 pino 6 (GND) → Pico pino 3 (GND).
Captura a 2 MHz, trigger de borda **negativa** no canal 1, 50.000 postsamples, rodando
`i2cdetect -y 1` no Pi. Os dois canais aparecem certinhos.
Decodificador: na busca, ele se chama **`I²C`** (digite "Inter", porque buscar "i2c" não acha nada).
Use SCL = Channel 2, SDA = Channel 1 e formato "shifted". As etiquetas Start, Address write e NACK aparecem.

**Atenção ao trigger:** o "edge trigger" deste firmware dispara pelo **nível**, não pela borda. Com "Negative edge"
marcado, ele dispara assim que o pino está em 0 (no I2C funcionou porque o SDA fica em 1 no repouso). Para um sinal
que fica em 0 no repouso, como o E do LCD, deixe "Negative edge" **desmarcado**.

**Importante:** o programa **sempre** espera um trigger (não existe "sem trigger"). Se o sinal
nunca mudar, a captura fica esperando para sempre. Use **Abort** para cancelar.

**Cuidado:** não use o Pico apenas encaixado na placa proto, porque o contato falha. Ligue os fios
direto nos pinos ou use a protoboard. Num teste, o chip esquentou muito (a causa provável foi um
curto ao mexer nos fios). Ele sobreviveu, mas desligue o USB na hora se isso acontecer.

## Configuração de captura sugerida

- Frequência: **10 MHz** para o barramento do LCD. O pulso E do HD44780 dura no mínimo cerca de 230 ns.
  Use **1 MHz** se for capturar só o I2C.
- Trigger: borda no canal 3 (E). Mude a entrada do amplificador e veja o que passa no barramento.
- Decodificadores incluídos: `parallel` (para o LCD: clock = E, dados = D0–D7) e `i2c` / `eeprom24xx`.
  Não existe decodificador de HD44780 pronto. O sniffer em Python do projeto vai fazer esse papel.
