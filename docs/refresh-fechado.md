# Escrita persistente sem dependências externas

## Regra física

O T9311 continua sendo o mestre do LCD. O Pico não gera `E` nem toma o
barramento: ele só pode alterar uma transação que o controlador já iniciou,
puxando sinais para 0 e soltando-os de volta. Por isso uma escrita não é um
overlay permanente. Quando o controlador redesenha, ele pode apagar o texto do
Pico.

Persistir significa observar cada tela completa, verificar o resultado modelado
e armar o plano estrito para o próximo redraw real. O Pico não envia IR, HTTP
ou comandos de qualquer tipo ao amplificador, ao groove-rig ou a outro host.
Ele continua funcional sem rede, além da página/OTA opcionais.

## Ciclo implementado

```text
redraw completo do amplificador
  → fecha e avalia o plano do redraw que acabou
  → atualiza o modelo HD44780 a partir do barramento observado
  → arma o plano guardado para o próximo redraw elegível
  → em outro redraw, compara a linha 2 modelada com o nome esperado
      → confere: complete
      → não confere: waiting_redraw/degraded; segue armado para o próximo
```

A primeira tela de uma fonte nova já terminou quando o sniffer consegue
identificá-la. Sem um sinal passivo que revele a fonte antes do LCD, não há
como alterá-la com segurança usando apenas esta topologia. Se não ocorrer outro
redraw natural, uma segunda pressão local na mesma fonte é hoje a próxima
oportunidade física de aplicar o plano. Isso não é uma decisão de software: é a
consequência de o Pico não ser mestre do LCD.

O rearme depois de `PUT /names` acontece no laço da escuta, quando o barramento
fica 2 ms sem escritas. Assim o Pico não solta os fios no meio de um redraw nem
monta um plano com a tela pela metade.

O resultado vem do modelo HD44780 alimentado pelas palavras observadas no
barramento; não é leitura elétrica de volta da memória do LCD nem confirmação
óptica. A guarda em `plano.py` continua sendo a última barreira antes de cada
modificação.

## Observabilidade

`GET /names` expõe em `refresh`:

- `phase`: `idle`, `waiting_redraw`, `waiting_glyphs`, `complete`, `degraded`
  ou `cancelled`;
- `redraws_seen`, `first_redraw_ms` e `first_verified_ms`: tempos desde a troca
  observada até o redraw e a primeira confirmação;
- `original_redraws`: redesenhos em que a linha 2 ainda era o nome original do
  controlador (a injeção não aconteceu ou foi desfeita);
- `unexpected_redraws`: redesenhos com outra linha 2, nem o nome esperado nem o
  original (menu, transição ou plano recusado);
- `integrity_errors`: o código DDRAM confere, mas o desenho CGRAM necessário não
  foi confirmado — a letra visível não pode ser dada como certa;
- `last_actual_matches`, `last_actual` e `last_plan`: comparação da tela
  modelada, o texto lido nela e o resultado do plano imediatamente anterior.

Não há uma lista de eventos no Pico: o log circular `/bus` é a fonte de
diagnóstico detalhada e evita reter dicionários/alocações a cada tela no caminho
de escrita.

O log `/bus` registra palavras e telas, mas não botões físicos. Assim, duas
telas separadas por segundos demonstram que houve redraw, mas não permitem
dizer se foi espontâneo ou causado por um segundo toque. Essa distinção precisa
ser medida mantendo os botões quietos durante o ensaio.

O status `complete` quer dizer que uma tela normal da entrada-alvo foi
reconstruída pelo sniffer com a linha 2 exatamente igual ao texto configurado e
com os desenhos CGRAM necessários observados. Não garante a aparência óptica.

## Limites de segurança

- DAB → Air não tem plano estrito viável. O plano só pode agir quando encontra
  toda a guarda; `D` isolado é ambíguo com DVD. DAB deve continuar `DAB` no LCD
  principal até existir uma estratégia que preserve essa guarda.
- A referência anterior a `ViD` foi um typo, provavelmente `Vir`, sem captura
  que comprove qualquer um deles. Porém, o log de 2026-10-25 trouxe transientes
  `TUGE` e `TEGA` durante trocas rápidas; eles são falhas reais de integridade a
  investigar, não um comportamento aceito. A guarda identifica a entrada antes
  da primeira alteração, mas não consegue prever uma mudança que aconteça no
  meio do mesmo redraw.
- `waiting_glyphs` indica que o caractere CGRAM ainda não foi confirmado. Um
  novo redraw pode resolver; não há ação externa que deva ser enviada para isso.
- Não levantar `E`, não dirigir nível alto em paralelo e não alterar volume,
  fonte ou qualquer controle do amplificador a partir do Pico.

## Próximas alternativas sem corte

1. **Medir redraw natural.** Depois de uma troca, não toque em nada por 10 s e
   salve `/bus` e `/names`. Isso determina se a persistência pode ocorrer sem a
   segunda pressão.
2. **Capturar passivamente sinais anteriores ao LCD.** Observar SCL/DA0/DA1 dos
   PT2314 ou o receptor IR/botões pode revelar a fonte antes do primeiro redraw.
   Primeiro mapear todas as transações, com sonda de alta impedância; não
   transmitir no barramento.
3. **Pré-armar por uma indicação local passiva.** Se uma assinatura inequívoca
   surgir antes da tela, ela pode alimentar o planejador sem depender de outro
   equipamento. Deve expirar rápido e só valer depois que a tela confirmar.
4. **Interposer removível.** Um adaptador no conector do LCD permitiria isolar
   linhas e criar um mestre independente, mas é uma intervenção física de risco
   maior e fica fora desta fase sem placa reserva.

## Roteiro de validação

1. Abra `/bus` e `/names`, escolha TUNER ou TAPE uma única vez e não toque em
   mais nada por 10 s.
2. Verifique se há segundo redraw, se `redraws_seen` aumenta e se
   `first_verified_ms` é preenchido. Se a linha 2 ficar no nome original, o
   problema é ausência de oportunidade de escrita, não uma confirmação falsa.
3. Faça DAB → DVD e DVD → DAB repetidamente. Nenhuma fonte errada pode ganhar
   texto personalizado.
4. Teste volume, menus, power-cycle e trocas rápidas. Registre qualquer linha
   transitória híbrida no `/bus`; esta é uma falha que o firmware não deve
   mascarar como sucesso.
