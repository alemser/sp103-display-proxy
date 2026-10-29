# Atualizar o programa do Pico pelo Wi-Fi

Com o Pico instalado dentro do amp, o cabo USB fica difícil de usar (e com o fio do VSYS ligado, é até perigoso: ver
`proxy-ligacao.md`, "Regra do USB"). Por isso o programa novo vai pelo Wi-Fi, com senha, e o Pico **volta sozinho para a
versão anterior** se a nova não funcionar.

Programas: `firmware/ota.py` (no Pico, recebe), `firmware/main.py` (no Pico, decide se volta) e `tools/enviar.py` (no
computador, envia).

## Preparar (uma vez só, pelo cabo)

1. No `firmware/secrets.py` do computador, a linha da senha (já está lá, com uma senha aleatória):

   ```python
   UPDATE_PASSWORD = "..."   # qualquer texto; o enviar.py lê daqui
   ```

2. Com o Pico no USB (e o fio do VSYS solto, se estiver no amp), mande os arquivos:

   ```sh
   cd firmware
   ../.venv/bin/mpremote cp *.py :
   ../.venv/bin/mpremote reset
   ```

Feito em 2026-10-24: o Pico do amp já está assim.

## Mandar uma versão nova

```sh
python3 tools/enviar.py
```

Ele faz tudo sozinho:

1. Pergunta ao Pico (`http://sp103.local/update`) quais arquivos ele tem.
2. Confere a sintaxe dos arquivos de `firmware/` no computador e manda só os que mudaram.
3. Marca para apagar os `.py` que estão no Pico mas não existem mais em `firmware/` (só quando envia a pasta inteira).
4. O Pico guarda **a versão atual inteira** na pasta `old/`, troca e apaga os arquivos.
5. O Pico reinicia e a versão nova fica **em teste**. Ela é confirmada quando, por 20 s seguidos, o programa roda, o
   Wi-Fi está conectado e alguém (o próprio `enviar.py`) consegue falar com o Pico.
6. O `enviar.py` mostra "Pronto: versão ... confirmada", em uns 30 s.

Se a versão nova **falhar**, o Pico volta sozinho para a anterior:

| O que acontece com a versão nova | Quando o Pico volta |
|---|---|
| Dá erro ao começar | uns 40 s (mostra o erro por 30 s e reinicia) |
| Trava, não conecta no Wi-Fi ou não responde | 3 min (o relógio do `main.py` vence e ele reinicia) |
| Falta luz durante o teste | no boot seguinte (por segurança, conta como falha) |

O `enviar.py` avisa: "A versão nova FALHOU e o Pico voltou para a anterior". Para ver o erro, ligue o Pico no cabo e
rode a versão nova com o `mpremote` (com o amp fora da tomada e o fio vermelho solto):

```sh
cd firmware
../.venv/bin/mpremote mount . run proxy.py
```

O `mount` faz o Pico usar os arquivos do computador. Se o `mpremote` for interrompido no meio, o Pico fica esperando o
computador e não volta ao Wi-Fi: desligue e ligue o USB.

## Outros comandos

```sh
python3 tools/enviar.py --estado           # versão atual, estado e versão guardada
python3 tools/enviar.py --voltar           # volta para a versão guardada (a de antes da última atualização)
python3 tools/enviar.py proxy.py           # manda só esse arquivo (se mudou; não apaga nada)
python3 tools/enviar.py --host 192.168.178.108    # se o sp103.local não funcionar
```

A "versão" é um código de 8 letras que muda sempre que algum arquivo muda.

## O que nunca vai pelo Wi-Fi

- **`main.py`**: é o "porteiro" que faz a volta. Se ele estragasse, nada mais voltaria. Mudou o `main.py`? Só pelo cabo.
- **`secrets.py`**: tem as senhas. Para trocar a senha do Wi-Fi ou da atualização, só pelo cabo.
- **`names.json`**: os textos personalizados ficam no Pico e são editados pela página.

## Segurança

- A senha vai no cabeçalho `X-Password`, sem criptografia (HTTP simples). Na rede de casa isso basta. Use uma senha que
  não sirva para mais nada.
- Uma senha errada demora 1 s para ser recusada (para atrasar quem tenta adivinhar).
- Sem a linha `UPDATE_PASSWORD` no `secrets.py` do Pico, a atualização fica desligada.

## Testado

Na bancada (2026-10-24):

- Três atualizações reais (`web.py`, `buslog.py`, `ota.py`): confirmadas em ~30 s.
- Versão que dá erro ao começar: voltou sozinha em 38 s.
- Versão que trava: voltou sozinha em 189 s.
- `--voltar` e reenvio: ok. Senha errada, arquivo com erro de sintaxe e `main.py`: recusados, com mensagem.

No amp (2026-10-29): a primeira versão do proxy deu erro ao começar e voltou sozinha; a correção foi confirmada. O
apagar foi usado para tirar do Pico os arquivos da escrita sem corte. O `ota.py` antigo não sabia apagar, então foram
dois envios: o `enviar.py` avisa quando isso acontece.
