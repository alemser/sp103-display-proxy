# Brief: texto personalizado no LCD frontal do Acoustic Solutions SP103 (Raspberry Pi Pico 2 W)

Resumo vindo da conversa no Claude (cloud), 2026-10-21. Fica como referência do projeto.

## Objetivo
Mudar o que o LCD frontal original do amplificador SP103 mostra (por exemplo, "PHONO" vira "Turntable", volume personalizado, mensagem de boas-vindas e, mais tarde, o nome da faixa vindo do OceanO). O LCD original, o controlador original e todas as funções do amplificador continuam intactos. Tudo deve ser reversível. O dono é amador, então as explicações devem ser passo a passo.

## Fatos de hardware
Verificado pelas fotos:
- Placa frontal: "SP103 AMPLIFIER CONTROL BOARD 3", DSP-ISS2, de 2007/06/08.
- Display: módulo LCD de caracteres 16x2 padrão (marcado LCD1A), backlight amarelo-esverdeado, uma fileira de 16 pinos, pads A/K separados à direita. Trimpot de contraste VR301.
- Controlador: DIP de 40 pinos marcado T9311DP / Y534D383 9353 / D2414 3323550. Sem datasheet e firmware não modificável. Tem um cristal com dois capacitores de 22 pF e duas redes de resistores de 9 pinos 4,7k (R907/R908, "9P4K7").
- IC801 = EEPROM I2C 24C01 (pino 5 = SDA, pino 6 = SCL, pino 4 = GND). O volume é um encoder rotativo, então o volume é totalmente digital.
- Processador de áudio: PT2314 (I2C), na placa de entradas. Passos de 1,25 dB, de 0 a -78,75 dB.
- O display mostra, por exemplo, "Volume -78.75 dB" na linha 1 e "PHONO" na linha 2.

Inferido, ainda não confirmado:
- LCD compatível com HD44780 em barramento paralelo. Pinagem: 1 VSS, 2 VDD, 3 VO, 4 RS, 5 RW, 6 E, 7–14 D0–D7, 15/16 A/K. A orientação do pino 1 ainda precisa ser confirmada.
- Controlador da família 8051: pino 20 = GND, pino 40 = +5 V.
- Desconhecido: modo 4 bits ou 8 bits, e se RW vai ao GND ou se o controlador lê o busy flag.

## Abordagem escolhida
1. Medir primeiro, sem invadir nada:
   - Continuidade com o multímetro, com o amp desligado da tomada. Checar LCD pino 5 contra o GND, ver se os pinos 7–10 estão ligados ou soltos (modo 4 bits), mapear os pinos 4–14 do LCD às pernas do controlador, e ver se os pinos 5/6 da 24C01 chegam ao conector J2.
   - Analisador lógico com o amp ligado: barramento do LCD (RS, E, dados) e I2C, trocando de entrada e girando o volume.
2. Fase de bancada: o Pico só escuta os pinos do LCD original, como entradas, com GND comum. Ele controla um 1602 reserva na protoboard. Durante essa fase o Pico é alimentado pelo USB do notebook, com o notebook na bateria.
3. Instalação final: cortar só os pinos de sinal (4–14) entre a placa do LCD e a placa de controle. O toco de baixo (vindo do controlador) vai a uma entrada do Pico, e o de cima (para o LCD) recebe uma saída do Pico. Para reverter, basta ligar cada par de tocos. O Pico fica numa MonkMakes Prototype PCB, em espaçadores de nylon.
4. Alimentação: VSYS a partir do LCD pino 2 (+5 V) por um diodo Schottky 1N5817, com GND no LCD pino 1.
5. Nomes das faixas: o Orange Pi Zero 2W (OceanO) envia por Wi-Fi ao Pico 2 W.

## Restrições elétricas
- O GPIO do Pico é 3,3 V. As entradas do RP2350 aguentam 5 V só com o chip alimentado.
- Saídas de 3,3 V para o LCD de 5 V: testar na bancada. Se não forem confiáveis, usar shifters BSS138.
- Errata E9 do RP2350: evitar os pull-downs internos nas entradas.
- Nunca alimentar VSYS e USB ao mesmo tempo sem o diodo.
- Nunca mexer no lado de 230 V. Conectar e desconectar fios só com o amp fora da tomada.

## Etapas de software
1. Controlar o 1602 reserva a partir do Pico (hello-world e teste de contraste).
2. Sniffer passivo do HD44780 via PIO (latch na borda de descida do E, modos 4 e 8 bits) que reconstrói o buffer 16x2 e o imprime no serial.
3. Camada de reescrita ("PHONO" → "Turntable") que renderiza no LCD reserva.
4. Depois: um endpoint Wi-Fi para o OceanO mandar o "now playing" (overlay temporário).

MicroPython com rp2 PIO se o timing permitir, senão o C SDK. Código simples e bem comentado.

## Descobertas pelas fotos da petervis.com (2026-10-22)

Fotos em `docs/img/petervis/`, do mesmo modelo de placa ("SP103 AMPLIFIER CONTROL BOARD 3", DSP-ISS2, 2007/06/08).

- O trimpot de contraste se chama **VR901** (10k, marcado 103), e não VR301. Fica à esquerda do LCD.
- O módulo LCD tem uma fileira de 16 pinos no canto superior esquerdo e os pads **A** e **K** do backlight na lateral direita.
  O trimpot fica perto da ponta esquerda, o que sugere que o pino 1 é o da esquerda (visto de frente). Falta confirmar.
- Pela foto do lado das soldas, só parte dos 16 pinos tem trilha fina saindo para o controlador, num feixe de umas 6 ou 7 trilhas.
  Isso combina com o **modo 4 bits** (RS, E, D4–D7, com RW ao GND), mas é só uma hipótese até medir.
- A placa de entradas ("SP103 IO BOARD ISS1 VER 1.1") tem **dois PT2314** (U52 e U53) e o conector **CON51**
  com 4 vias: **GND, CL, DA1, DA0**. Ou seja, um SCL comum e um SDA para cada PT2314, porque os dois têm o mesmo
  endereço fixo. Um cabo branco de 4 fios liga o CON51 à placa frontal.
- O display mostra, por exemplo, "Volume -26.25 dB" / "CD".

## Medições com o multímetro (2026-10-22)

Respondidas. Veja o mapa completo em `docs/ligacao-analisador.md`:
- O barramento é de **8 bits**: D0–D7 nas pernas 39–32 (P0).
- O **RW não vai ao GND**: ele está na perna 11 (P3.1). RS na perna 10 (P3.0), E na perna 28 (P2.7).
- O pino 1 do LCD é a ponta esquerda, vista de frente.

## Capturas com o analisador (2026-10-23)

Concluídas. Os detalhes estão em `docs/descobertas-protocolo.md`:
- O controlador **lê o busy flag** antes de cada comando e de cada caractere. O Pico final precisa responder a essas leituras.
- Ele **redesenha as duas linhas inteiras** a cada evento (volume, entrada, menu), posicionando cada caractere (cerca de 8 ms por tela).
- Os dados ficam presos no último byte no repouso, então cortar só o pino E não deve bastar.
- Telas: boas-vindas, modelo e versão, volume + entrada/barra, menus do Function (Bass, Treble, Balance, Loudness, Speakers).
- O controlador manda os comandos do PT2314 no mesmo barramento I2C da 24C01?
