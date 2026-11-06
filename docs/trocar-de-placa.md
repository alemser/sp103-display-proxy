# Instalar a ponte numa placa

O VU e as telas de informação dependem do `sp103-vu-relay`, um programa que roda na placa com o groove-detector. Ele
**não vem na imagem do Oceano**, de propósito: só o SP103 usa, e o Oceano não sabe que o SP103 existe. A ponte é só mais
um leitor do que o detector publica (`docs/contracts.md` do groove-detector).

Por isso, faça estes passos sempre que a captura mudar de placa, ou depois de gravar uma imagem nova no cartão.

## Passos

Serve qualquer placa Linux com o groove-detector, de 32 ou 64 bits. Na pasta do repositório, com o usuário e o IP da
placa:

1. Instalar:

   ```sh
   make -C relay deploy HOST=usuario@ip
   ```

2. Na app, aba Display, colocar o IP da placa em **VU source (IP)**. O Pico não resolve nomes `.local`.

3. Conferir, com música tocando:

   ```sh
   make -C relay check HOST=usuario@ip
   ```

   Tudo certo é ver os dois serviços `active`, os quadros chegando e `gate: música`.

## Se não funcionar

| O que aparece | Causa provável |
|---|---|
| App: "No data from ... Is the VU relay running there?" | A ponte não está instalada nessa placa, ou o IP na app é de outra |
| `make check`: nenhum quadro, com os dois serviços `active` | O firewall da placa bloqueia a porta UDP 7091 (abaixo) |
| `make check`: `gate: sem música`, com música tocando | O detector não está vendo o sinal: confira a captura dele |
| `make deploy`: "não tem o grupo groove" | A placa ainda não tem o groove-detector |

Se a placa usa o `ufw`, libere a porta para a rede local (troque pela faixa da sua rede):

```sh
sudo ufw allow from 192.168.1.0/24 to any port 7091 proto udp comment sp103-vu-relay
```

Ao sair de uma placa, a ponte pode ficar lá: sem pedidos do Pico, ela não envia nada.
