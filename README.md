# SP103 display proxy

Textos personalizados no display frontal do amplificador **Acoustic Solutions SP103**, com um **Raspberry Pi Pico 2 W**
no meio entre o controlador original (T9311) e o display (LCD 16x2, HD44780).

- O controlador e as funções do amp continuam originais. O Pico muda o que o display mostra: "TUNER" vira
  "Rega Planar 2", e assim por diante.
- O Pico publica o estado do amp (volume, entrada, menus) na rede, em `http://sp103.local/` (só a API: `docs/api-estado.md`).
- Opcional: as duas linhas viram um VU meter (canais L e R, com o pico) enquanto toca música, com os dados do
  groove-detector (`docs/vu.md`).
- O Pico comanda o amp pelo Wi-Fi: manda os códigos do controle remoto direto na linha do IR, por dentro do amp, e aperta
  o botão Function. Com o amp em standby, girar o botão do volume liga o amp (`docs/proxy-ligacao.md`).
- O controle remoto continua funcionando, e o groove-rig segue comandando o amp pelo Broadlink.

## Como funciona

```
controlador T9311 ──(GP2–GP12, 8 bits)──► Pico 2 W ──(GP16–21, 4 bits)──► display do amp
                   ◄── "livre" no D7 ────┘
receptor IR ◄──────(GP15, só puxa para 0)── Pico 2 W
botão do volume ───(GP14, só leitura)─────► Pico 2 W
botão Function ◄───(GP0 lê, GP1 só puxa para 0)── Pico 2 W
```

1. O display foi dessoldado nos pinos 4–14 (2026-10-29). Agora o controlador fala só com o Pico.
2. O Pico lê cada byte que o controlador manda (`firmware/sniffer.py`, PIO + DMA) e responde "livre" às perguntas
   de "ocupado?" (`firmware/busy.py`). Para isso ele só puxa o D7 para 0, nunca manda 1.
3. O Pico remonta a tela (`firmware/hd44780.py`), troca os nomes (`firmware/names.py`) e desenha no display
   (`firmware/lcd1602.py`). O programa principal é o `firmware/proxy.py`.
4. Para comandar o amp, o Pico puxa a linha do IR para 0 nos mesmos tempos do controle remoto (`firmware/ir.py`) e
   imita o botão Function (`firmware/panel.py`). O `firmware/control.py` junta os dois nos ajustes diretos.
5. O Pico é alimentado pelo próprio amp (5 V do pino 2 do display, também em standby) e atualizado pelo Wi-Fi.

## Uso

| Para quê | Como |
|---|---|
| Ver o estado do amp | a app Amp Link (repositório amp-link), aba Now |
| Trocar os nomes das entradas e das telas de início | a app, aba Names (até 16 caracteres, sem acentos) |
| Ligar o VU meter | a app, aba Display (`docs/vu.md`) |
| Comandar o amp | a app, aba Now, ou `curl -X POST "http://sp103.local/control?target=bass&dir=up"` (`docs/api-estado.md`) |
| Ver o barramento | a app, aba Status |
| Baixar o registro | `curl http://sp103.local/bus.csv` |
| Atualizar o programa do Pico | `python3 tools/enviar.py` |
| Testar no computador | `python3 tools/test_proxy.py` (e os outros `tools/test_*.py`); a ponte: `cd relay && make test` |

## Documentos

| Documento | Conteúdo |
|---|---|
| [`docs/proxy-ligacao.md`](docs/proxy-ligacao.md) | **A instalação atual**: ligação, alimentação, regras de segurança, diagnóstico |
| [`docs/api-estado.md`](docs/api-estado.md) | O contrato do `/state`, do `/events` e das rotas `/control` e `/ir` (estado do amp e comandos) |
| [`docs/vu.md`](docs/vu.md) | O VU meter: a ponte no Orange Pi, o protocolo, o que o display mostra, a configuração |
| [`docs/atualizacao-wifi.md`](docs/atualizacao-wifi.md) | Atualizar o Pico pelo Wi-Fi, com volta automática |
| [`docs/descobertas-protocolo.md`](docs/descobertas-protocolo.md) | Como o controlador fala com o display: comandos, telas e parte elétrica |
| [`docs/bancada-ligacao.md`](docs/bancada-ligacao.md) | Display reserva na bancada (mesma ligação 4 bits do display do amp) |
| [`docs/ligacao-analisador.md`](docs/ligacao-analisador.md) | Mapa de pinos do LCD e do T9311, ligação do analisador lógico |
| [`docs/placa-frontal/mapa-pernas.md`](docs/placa-frontal/mapa-pernas.md) | Mapa das pernas do controlador T9311DP, medido com o multímetro, e fotos da placa |
| [`docs/historico/`](docs/historico/) | Registro do projeto: objetivo inicial, opções analisadas e roteiros de medição e captura. Não descrevem o estado atual |

## Pastas

- `firmware/`: o programa do Pico (MicroPython). O `main.py` e o `secrets.py` só vão pelo cabo.
- `relay/`: a ponte do VU (`sp103-vu-relay`, Go), que roda no Orange Pi.
- `tools/`: envio pelo Wi-Fi, testes no computador, leitura do registro e decodificador das capturas.
- `captures/`: capturas `.lac` do analisador lógico, usadas pelos testes.
- `docs/`: documentação e fotos da placa.
