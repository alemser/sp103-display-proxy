# Refresh fechado sem cortar trilhas

O controlador só escreve no LCD enquanto ele próprio redesenha uma tela. Depois
de uma troca de entrada, o Pico já sabe qual entrada chegou, mas a escrita dessa
primeira tela acabou. Este modo pede ao `groove-rig` dois toques IR de volume para
criar um redraw novo e conhecido:

```
entrada nova -> Pico reconhece -> volume +1/-1 -> barra vista -> arma plano -> redraw normal -> confere
```

O Pico nunca considera o `POST` ao groove-rig como sucesso. Ele só considera
completo quando o sniffer recebe a barra, o redraw normal posterior e o motor PIO
termina todos os passos. Erro, timeout ou tela inesperada deixam o LCD original.

## Ativar depois do teste no amp

Em `firmware/secrets.py`, adicionar (não em `secrets.example.py`):

```python
GROOVE_RIG_HOST = "oceano.local"  # ou IP do Orange Pi
GROOVE_RIG_PORT = 7075
```

O endpoint usado é `POST /targets/amplifier/actions/volume_up` e
`volume_down`. No volume 0 dB a ordem é `down`, `up`; nos demais valores é
`up`, `down`. Assim o valor final deve voltar ao original, e o sniffer confere
isso antes de a tela personalizada ser considerada confiável.

## Política de segurança

`plano.make()` agora exige a guarda completa por padrão. Um texto que só cabe
reduzindo a guarda — hoje `DAB -> Air`, confundível com `DVD` no primeiro `D` —
fica marcado como não suportado no LCD do amp. Continua disponível no display
reserva e na página. O refresh fechado só é disparado para planos seguros.

## Roteiro de bancada para amanhã

1. Atualize o Pico com o modo ainda **desligado** (sem `GROOVE_RIG_HOST`) e
   confira que o amp continua normal.
2. Configure o host, salve, atualize e abra `GET /names`: TUNER e TAPE/AUX devem
   aparecer como `amp display: ok`; DAB/Air deve aparecer como não suportado.
3. Aperte Tuner e Tape/Aux. Espere o ciclo: barra, retorno ao mesmo volume e nome
   personalizado. Confirme no `/bus` as três telas.
4. Faça uma troca para DVD enquanto o refresh está aguardando. O resultado
   permitido é a tela original; caracteres híbridos não são permitidos.
5. Se qualquer passo falhar, remova `GROOVE_RIG_HOST` e atualize: o firmware volta
   ao modo passivo de escrita sem reiniciar ou alterar o amplificador.
