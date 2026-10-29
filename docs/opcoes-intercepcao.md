# Como o Pico pode mudar o texto do display do amp (opções de interceptação)

**Decidido e feito em 2026-10-29: opção 3b, display dessoldado nos pinos 4–14, com o Pico como proxy.** Instalação:
`proxy-ligacao.md`.

Este documento resume por que o Pico precisa ficar no meio, as opções analisadas e o que a tentativa "sem corte"
(2026-10-24 a 10-28) ensinou. O código e os testes dessa tentativa (`escrita.py`, `plano.py`, `refresh.py`,
`tools/planejador.py` e os `tools/teste_*_pico.py` da escrita) estão no histórico do git, até o commit `6be4eb2`.

## Por que "sobrescrever em paralelo" não funciona

A ideia era deixar tudo ligado como estava e o Pico reescrever o display logo depois do controlador. Isso não dá, por
motivo elétrico:

- **E (perna 28, P2.7):** no repouso, o controlador segura o E em 0 com força. Se o Pico levantasse o E, os dois
  brigariam pelo fio.
- **Dados (pernas 32–39, P0):** no repouso, ficam presos no último byte escrito. Os bits em 0 são segurados com força
  pelo controlador; os resistores de 4,7 kΩ (R907/R908) só puxam para 5 V os bits em 1. O Pico consegue baixar uma
  linha, mas não levantar.

Não existe uma janela em que o Pico escreva sozinho sem brigar com o controlador.

## O que as fotos mostraram

| Foto | O que mostra |
|---|---|
| ![controlador](img/minha-placa/controlador-t9311-sem-soquete.jpg) | O T9311 está **soldado direto na placa, sem soquete** |
| ![lateral](img/minha-placa/lcd-pinos-lateral.jpg) | O display está preso por uma barra de 16 pinos, soldada nas duas placas, com um **espaçador de plástico** entre elas. As pontas dos pinos sobram acima da placa do display |
| ![solda](img/minha-placa/lcd-lado-solda-trilhas.jpg) | No lado das soldas, sai **uma trilha de cada pino**, separadas logo depois da solda. Mais adiante elas se juntam num feixe fino até o controlador |

## Opções

| # | Opção | Veredito |
|---|---|---|
| 1 | Adaptador no lugar do controlador (soquete "sanduíche" de 40 pinos) | Descartada: o chip está soldado; seria preciso desoldar 40 pernas |
| 2 | Cortar 11 trilhas no lado das soldas, logo depois dos pinos do display | Possível, sem mexer no display; risco de cortar uma trilha vizinha |
| 3a | Cortar os pinos entre as placas | Inviável: o espaçador de plástico não deixa o alicate entrar |
| 3b | Desoldar o display e soldar de novo só os pinos 1–3, 15 e 16; os furos 4–14 recebem os fios do lado do controlador | **Escolhida e feita (2026-10-29)** |
| — | Escrita "sem corte": o Pico só puxa fios para 0 durante as transações do controlador | Testada e aposentada (abaixo) |

Na 3b, cada um dos 11 sinais fica com dois lados:
- **Controlador → Pico**: os 11 fios (RS, RW, E, D0–D7) em GP2–GP12. O Pico finge ser o display e responde "livre" às
  leituras do busy flag; sem resposta, o controlador pergunta para sempre.
- **Pico → display**: só 6 fios (RS, E, D4–D7) em GP16–21, modo 4 bits, com o RW do display no GND. O display nunca manda
  sinal de volta, então não entra 5 V no Pico por esse lado.
- **Para voltar ao original**: 11 jumpers ligando cada fio do controlador ao do display.

## A tentativa sem corte (2026-10-24 a 10-28)

O Pico ficava em paralelo, com o display ligado ao controlador, e só puxava fios para 0. Os quatro truques funcionaram
no amp:

| Truque | Como |
|---|---|
| Trocar bits de uma letra | zerar bits do caractere que o controlador manda ("PHONO" → "PHONE") |
| Desenhos próprios | ao ligar, zerar pontos dos desenhos das barras (CGRAM) para virarem letras |
| Mover letras | numa leitura do busy flag, puxar o RW: o LCD recebe um comando "vá para..." com os bits do último byte |
| Congelar células | transformar uma escrita em comando 0x00, que o LCD ignora |

Mas o Pico só consegue **apagar bits** dos bytes que o controlador já manda. Por isso:

- Só nomes curtos e escolhidos com cuidado saíam (REGA, TAPE). Nomes como "Rega Planar 2" eram impossíveis.
- O nome só aparecia a partir do segundo redesenho de uma entrada: no primeiro toque, ao ligar e depois do menu Function,
  aparecia o nome original.
- DAB e DVD só se distinguem pela segunda letra. O plano seguro para DAB → "Air" não existia, e em trocas rápidas
  apareceram telas misturadas (`TUGE`, `TEGA`).

Com o proxy, nenhum desses limites existe: qualquer texto de até 16 caracteres, desde a primeira tela.

### O que ficou aprendido

Os fatos sobre o controlador estão em `descobertas-protocolo.md` ("Elétrica das portas e leitura do busy flag"): RS e
RW são fracos no 1, o E e os dados em 0 são fortes, o controlador solta só o D7 para ler o busy flag e pergunta de novo
se lê "ocupado", e o LCD ignora o comando 0x00.

Armadilhas do PIO no MicroPython, que custaram tentativas e valem para qualquer programa novo:

| Armadilha | Como evitar |
|---|---|
| `mov(pindirs, ...)` gera o mesmo código que `mov(exec, ...)`: o PIO executa o valor como instrução | mudar a direção dos pinos só com `out(pindirs, n)` ou `set(pindirs, n)` |
| Dentro de uma função `@rp2.asm_pio`, as variáveis do arquivo não existem (`NameError`) | escrever os números direto (por exemplo, `wait(1, gpio, 2)`) |
| `autopull=True` faz o `pull()` não fazer nada se o OSR estiver cheio | sem autopull; `pull(ifempty)` quando precisar |
| O padrão é `out_shiftdir=SHIFT_LEFT`: `out()` pega os bits do topo do OSR | `out_shiftdir=SHIFT_RIGHT` quando a máscara está nos bits baixos |
| Ruído no E com fios longos: pulsos falsos de até ~1 µs | aceitar um pulso só depois de 3 µs em 1 (o filtro do `sniffer.py`) |
| Cada bloco PIO tem só 32 instruções | o sniffer fica no PIO0; o `busy.py`, no PIO1 |
| `Pin(n, Pin.IN)` tira o pino do PIO | criar o `Sniffer` antes do `Responder` do `busy.py` |
