# API do estado do amp (para o groove-rig e outros clientes)

O Pico publica o que o display do SP103 mostra, já interpretado, em `http://sp103.local/` (ou o IP do Pico,
192.168.178.108). Só leitura: o Pico nunca manda nada para o amp. Este é o contrato em que o groove-rig (o "state
provider" do amplificador) pode confiar; mudanças nele precisam mudar também os clientes.

## Rotas

| Rota | O quê |
|---|---|
| `GET /state` | O estado atual, em JSON |
| `GET /events` | Server-Sent Events: um `data: {json}` com o estado atual logo ao conectar, e outro a cada mudança. Um comentário `: ping` a cada 1 s mantém a conexão viva: sem nada por uns 5 s, o cliente deve reconectar |

O JSON é o mesmo nas duas. Exemplo:

```json
{"power": "on", "volume_db": -20.0, "input": "DAB", "input_id": "dab", "input_name": "AirPlay/BT - DAC",
 "bass_db": 2, "treble_db": 0, "balance": {"side": "L", "db": -5.0}, "loudness": false, "speakers": true,
 "screen": "normal", "firmware": "1.0", "lcd": ["Volume -20.00 dB", "DAB             "],
 "updated_at": 3747990, "version": 5}
```

## Campos

`null` em qualquer campo = ainda não se sabe. O Pico só sabe um valor depois que o amp o mostra no display: depois de
o Pico reiniciar, o bass fica `null` até alguém mexer nele.

| Campo | Valores | Observação |
|---|---|---|
| `power` | `"on"`, `"standby"`, `null` | `"on"`: o amp mostrou uma tela conhecida. `"standby"`: o controlador apagou a tela (ver abaixo). `null`: o Pico ligou e o amp ainda não mostrou nada |
| `volume_db` | −78.75 a 0, passos de 1.25 | O número da tela de volume |
| `input` | `PHONO`, `TUNER`, `TAPE/AUX`, `CD`, `DVD`, `DAB` | O nome original no amp |
| `input_id` | `phono`, `tuner`, `tape_aux`, `cd`, `dvd`, `dab` | Estável, para programas; os mesmos ids do perfil `acoustic_solutions_sp103` do groove-rig |
| `input_name` | texto | O nome personalizado (página do Pico), ou o original |
| `bass_db`, `treble_db` | −14 a 14, inteiros | |
| `balance` | `{"side": "L"/"R"/null, "db": −78.75..0}` | `db` 0 = centro. `side` null abaixo de 5 dB: a barra do amp ainda não mostra o lado |
| `loudness`, `speakers` | `true`, `false` | |
| `screen` | `normal`, `volume`, `bass`, `treble`, `balance`, `loudness`, `speakers`, `boot`, `about`, `standby`, `unknown` | A tela que o amp está mostrando. `bass`/`treble`: o amp está no modo em que Volume ± muda o tom (até 6 s depois da última tecla) |
| `firmware` | texto | Da tela "SW version" |
| `lcd` | 2 textos de 16 | As linhas originais do controlador (a caixa das barras vira `■`) |
| `updated_at` | ms | Relógio interno do Pico, na última mudança. Só serve para comparar com outro `updated_at` |
| `version` | inteiro | Aumenta a cada mudança. Volta a 0 quando o Pico reinicia |

## Standby

Ao ir para o standby, o controlador escreve espaços nas duas linhas e para; o `power` vira `"standby"` e a `screen`
também. Ao sair do standby, ele desenha direto a tela normal (volume e entrada), e o `power` vira `"on"`. Só quando o
amp recebe energia da tomada ele apaga a tela ("Clear display") e mostra "ACOUSTIC SOLUTIONS". Confirmado no amp em
2026-10-29: standby → `"standby"` em 0,1 s; ligar → `"on"`. Os outros campos guardam o último valor durante o standby (o amp volta com o mesmo volume e a mesma entrada).

O Pico é alimentado pelo amp também em standby. Se ele reiniciar com o amp em standby, o `power` fica `null` até o amp
ser ligado: um cliente que precisa saber deve tratar `null` como "não sei", nunca como desligado.

## Para o cliente

- Prefira o `/events`: cada mudança chega na hora (uns 10 ms depois de o controlador terminar a tela, mais o Wi-Fi).
- Se o Pico sumir (sem `ping` por uns 5 s), considere o estado desconhecido e reconecte com espera crescente.
- O Pico atende poucas conexões ao mesmo tempo: um `/events` por cliente, não um por tela.
- O `sp103.local` funciona no iOS e no macOS. O groove-rig (Go sem cgo) **não** resolve nomes `.local`: use o IP,
  que é fixo pelo roteador (`http://192.168.178.108/events`).
- No groove-rig, este é o "state provider" do perfil SP103: o contrato genérico está no `docs/state-provider.md` de lá.
