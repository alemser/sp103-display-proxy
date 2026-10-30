# Contrato das telas de informação (fonte → Pico)

O Pico do SP103 pode mostrar no display o que está tocando: artista e música, faixa e posição, tempo até o fim do
lado, horas da agulha. Ele não sabe de onde vêm esses dados: só conhece este contrato. Quem fala este contrato é uma
**fonte**. A fonte de hoje é o `sp103-vu-relay` no Pi 5, que lê o groove-identity e o groove-catalog
(`relay/nowplaying.go`); outra fonte (Volumio, Home Assistant) só precisa mandar os mesmos pacotes.

Tudo vai por UDP, na porta **7091** da fonte, a mesma do VU (`docs/vu.md`).

## Pedido (Pico → fonte)

| Pacote | Bytes | O quê |
|---|---|---|
| `"SUB1"` | 4 | Só o VU (o formato antigo; continua valendo) |
| `"SUB2"` + máscara | 5 | Máscara: bit 0 = VU, bit 1 = telas |

O pedido vale 6 s; o Pico repete a cada 2 s. Sem pedido válido, a fonte não manda nada. Uma fonte que só tem as telas
ignora o bit 0, e uma que só tem o VU ignora o bit 1.

## Telas (fonte → Pico)

```
"NP" versão(1) flags  campo 0x1F campo 0x1F ... campo
```

- `versão` = 1. O Pico ignora pacotes de outra versão.
- `flags`: bit 0 = tocando agora; bit 1 = o lado acabou (mostra "Flip the record").
- Os campos vêm sempre nesta ordem, separados pelo byte 0x1F. **Campo vazio = não se sabe**: a tela que depende dele
  não aparece, e as outras continuam.
- Texto só em ASCII de `" "` a `"}"`, sem `"\"` (a ROM do display não tem acentos; nela `"\"` vira `"¥"` e `"~"` vira
  seta). A fonte tira os acentos (`ã` → `a`) e corta cada texto em 40 caracteres.
- Números são inteiros em decimal.

| # | Campo | Exemplo | Tela |
|---|---|---|---|
| 0 | artista | `Pink Floyd` | Artist and title |
| 1 | música | `Time` | Artist and title, Track |
| 2 | faixa no disco | `A4` | Track |
| 3 | posição na faixa (s) | `161` | Track |
| 4 | duração da faixa (s) | `421` | Track |
| 5 | lado | `A` | Side |
| 6 | faixa no lado | `4` | Side |
| 7 | faixas no lado | `5` | Side |
| 8 | tempo até o fim do lado (s) | `608` | Side, fim do lado |
| 9 | horas da agulha | `312` | Stylus |
| 10 | desgaste da agulha (%) | `62` | Stylus |

Um pacote fica com uns 60 a 120 bytes. Campos a mais no fim são ignorados (para versões futuras com campos novos).

### Quando mandar

- Quando qualquer campo ou flag muda (faixa nova, lado acabou, agulha).
- A cada 5 s enquanto houver pedido, mesmo sem mudança.

As posições e o tempo do lado valem **no instante do envio**. Com o bit "tocando", o Pico soma o tempo que passou desde
que o pacote chegou, então a fonte não precisa mandar um pacote por segundo. O Pico só corrige o relógio dele quando
um pacote novo difere mais de 2 s do que ele contou, para a contagem não pular à toa.

Sem pacote por 15 s, o Pico descarta os dados e volta à tela do amp.

## Fonte de hoje: sp103-vu-relay no Pi 5

| Campo | De onde vem |
|---|---|
| artista, música, faixa no disco, posição, duração | groove-identity `GET /status` → `playback` (`artist`, `title`, `track_position`, `position_ms`, `duration_ms`), a cada 1 s |
| lado, faixa no lado, tempo do lado | a letra da `track_position` e a lista de faixas do disco: `album_programme.release_source` / `release_id` → groove-catalog `GET /catalog/library/releases/{source}/{id}/tracks` (`track_position`, `duration_ms`), uma vez por disco |
| agulha | groove-catalog `GET /catalog/stylus` → `metrics.stylus_hours_total`, `metrics.wear_percent`, a cada 10 min; vazio se `active` for falso |
| lado acabou | a última faixa do lado chegou ao fim e o reconhecimento parou (`playback.active` falso); vale até a próxima faixa ou 15 min |

Os endereços dos dois serviços são opções da ponte (`-identity`, `-catalog`; padrão `127.0.0.1`).
