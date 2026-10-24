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

A seção "Arquitetura decidida" (no fim) atualiza esta lista.

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

## Arquitetura decidida (2026-10-23)

O Pico **não** substitui o controlador e **não** emite IR. O controle do amp por IR já existe no projeto
**groove-rig** (Broadlink, API na porta 7075, no Orange Pi "oceano").

O papel do Pico:
1. **Observar** tudo o que o controlador escreve no LCD.
2. **Guardar o estado do amp na memória**, atualizado a cada mudança.
3. **Oferecer esse estado pela rede** a quem quiser: groove-rig, app, página web.
4. Reescrever ou desenhar as telas no LCD (o objetivo original).

### Estado

```json
{
  "power": "on",
  "volume_db": -28.75,
  "input": "PHONO",
  "bass_db": 2,
  "treble_db": 0,
  "balance": { "side": "R", "db": -5.0 },
  "loudness": false,
  "speakers": true,
  "screen": "normal",
  "lcd": ["Volume -28.75 dB", "PHONO           "],
  "updated_at": 1234567
}
```

- Um **leitor de telas** reconhece cada tela redesenhada e atualiza só os campos que ela mostra.
  A tela "Bass 2 dB", por exemplo, atualiza só o `bass_db`.
- O lado do balance (L/R) sai da posição da barra: o número é negativo dos dois lados.
- Volume e entrada aparecem sempre na tela normal. Bass, treble, balance, loudness e speakers só aparecem quando alguém
  abre o menu Function. Até lá ficam como "desconhecido" (`null`), ou com o último valor visto, guardado na flash.
  O controlador guarda esses valores na EEPROM, então o último valor visto costuma continuar valendo depois de desligar.
- Mais tarde, opcional: ouvir também o I2C do CON51 (os valores reais dos PT2314, mandados todos ao ligar o amp).

### Interface (Wi-Fi)

| Endpoint | Para quê |
|---|---|
| `GET /state` | o JSON acima |
| `GET /events` | Server-Sent Events: um aviso a cada mudança (para o groove-rig fazer ciclo fechado, por exemplo "vá para -30 dB") |
| `GET /` | página simples para ver o estado no celular |
| `GET /bus` | estatísticas do barramento e download das últimas palavras (CSV com horário) |
| `GET /update` | atualização do programa pelo Wi-Fi, com senha (`docs/atualizacao-wifi.md`) |

Wi-Fi em vez de Bluetooth: o OceanO e o groove-rig já estão na rede, e o navegador do celular basta (sem app).

### Em aberto

- **Saber quando o amp desliga.** Ao desligar, o controlador não escreve nada no LCD. As opções são alimentar o Pico separado
  e medir o 5 V do amp num GPIO (com divisor), ou o groove-rig tratar "Pico não responde" como "amp desligado".
  Decidir na instalação final.

### Ordem das etapas

| # | Etapa | Precisa do amp? |
|---|---|---|
| 1 | Bancada: o Pico desenha no display reserva as telas capturadas, a partir de um estado | não |
| 2 | Leitor de telas (tela → estado), testado no Mac com as capturas `.lac` | não |
| 3 | Wi-Fi: `/state`, `/events` e página, com estado de teste | não |
| 4 | Sniffer real (PIO) no barramento do LCD do amp | sim, só ouvindo |
| 5 | Integração com o groove-rig | sim |
| 6 | Instalação final (interceptar o LCD, alimentação, detecção de power) | sim |

### Andamento

- **Etapa 2 feita (2026-10-23):** `firmware/amp_state.py` (leitor de telas, compatível com MicroPython) e
  `tools/test_amp_state.py` (18 telas escritas à mão + reprodução das capturas `.lac`). Todas as telas boas das
  capturas viram estado; telas estragadas por fio solto são rejeitadas (`screen: "unknown"`, sem mudar os campos).
- Abaixo de 5 dB de balance a barra não aparece, então o lado fica `null` até passar de 5 dB.
- Falta confirmar qual canal a barra indica (barra à direita = canal direito atenuado, ou o som foi para a direita?).
- **Etapa 1 feita (2026-10-23):** `firmware/lcd1602.py` (driver 4 bits, só escrita), `firmware/sp103_screens.py`
  (estado → tela, com o CGRAM do amp) e `firmware/demo_telas.py`. Todas as telas e as 8 figuras aparecem certas no
  1602 azul, com os sinais de 3,3 V do Pico (sem conversor de nível). O VO foi direto ao GND.
  Mau contato nos fios só enfiados nos furos embaralha o modo 4 bits; o programa reinicia o display antes de cada tela
  para se recuperar sozinho. Solução definitiva: soldar barra de pinos.
- **Etapa 3 feita (2026-10-23):** Wi-Fi em segundo plano (sem rede, o display segue normal), `/state`, `/events`,
  `/names` e página; nomes das entradas e textos de inicialização personalizáveis pela página (`firmware/names.json`
  no Pico); `main.py` roda tudo sozinho ao ligar.
- **Interceptação (etapa 6), em análise:** ver `docs/opcoes-intercepcao.md`. Sobrescrever em paralelo é inviável
  (o controlador segura E e dados com força). O T9311 não tem soquete. A opção menos intrusiva é cortar 11 trilhas no lado
  das soldas, sem tocar no display. A etapa 4 (só escutar) não precisa de nenhuma intervenção.
- **Etapa 4, firmware pronto (2026-10-24):** `firmware/escuta.py` + `sniffer.py` (PIO + DMA circular) + `hd44780.py`.
  Testado com as capturas (`tools/test_sniffer.py`) e no Pico sem o amp (`tools/teste_sniffer_pico.py`); `main.py` agora
  roda a escuta. Sem resistores em série, e o Pico alimentado pelo pino 2 do LCD (5 V presente mesmo em standby) no VSYS.
  Ligação e testes que faltam: `docs/escuta-ligacao.md`.
- **Atualização pelo Wi-Fi e página /bus (2026-10-24):** `firmware/ota.py` + `main.py` (volta automática para a versão
  anterior) e `tools/enviar.py`, ver `docs/atualizacao-wifi.md`. `firmware/buslog.py`: estatísticas do barramento e
  download das últimas palavras (hoje 8192) com horário (`tools/ler_bus.py` remonta as telas). Testado na bancada com um
  amp de mentira (`tools/teste_bus_pico.py`), incluindo as voltas automáticas.
- **Escrita sem corte, testada (2026-10-24):** o RW e o RS são fracos no 1 (o Pico pode puxá-los com segurança), mas o
  controlador solta só o D7 para ler o busy flag. O Pico só consegue injetar o último byte com bits zerados, não qualquer
  comando. Trocar nomes livremente exige cortar as trilhas. Ver `docs/opcoes-intercepcao.md`. Fios soldados nas pontas
  dos pinos do display; o sniffer ganhou um filtro contra o ruído do E.
- **Escrita sem corte, os quatro truques comprovados no amp (2026-10-24):** o LCD ignora o comando 0x00 (teste 2),
  uma letra da linha 1 vai para a linha 2 (teste 4: "oAPE"), e um desenho próprio é criado ao ligar e mostrado no lugar
  de uma letra (teste 3: "rolume"). `tools/planejador.py` diz quais nomes cabem; os escolhidos são REGA, TAPE e Air.
  Falta o programa final em tempo real. Armadilhas do PIO em `docs/opcoes-intercepcao.md`.
- **Escrita sem corte, programa final no Pico (2026-10-24):** `firmware/escrita.py` (motor PIO + DMA) e
  `firmware/plano.py` (planos a partir dos nomes da página; `tools/test_plano.py` simula). REGA, TAPE e Air aparecem
  depois de girar o volume ou de apertar de novo a entrada. Limites do método: no 1º toque de outra entrada, ao ligar
  e depois do Function aparece o nome original até o próximo redesenho. Ideias para ir além sem cortar (o dono quer
  continuar por aqui): `docs/opcoes-intercepcao.md`, "Etapa final sem corte".
- **Instalação dentro do amp (2026-10-24):** o Pico fica dentro, alimentado pelo pino 2 do LCD (fio vermelho no VSYS,
  pino 39); atualização só pelo Wi-Fi (`tools/enviar.py`). Ver `docs/escuta-ligacao.md`, "Pico dentro do amp".
