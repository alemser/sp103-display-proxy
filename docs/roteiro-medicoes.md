# Roteiro de medições: placa frontal do SP103

> **Concluído em 2026-10-22.** Os resultados estão em `docs/ligacao-analisador.md`.

Objetivo: descobrir como o controlador (T9311DP) fala com o LCD, **sem ligar nada no amplificador**.
Ao final, saberemos quantos fios o analisador lógico precisa e onde prendê-los.

Preencha as tabelas à medida que for medindo. Se algo não bater com o esperado, **anote mesmo assim**:
o inesperado é justamente o que queremos descobrir.

---

## 0. Segurança e preparação

- [ ] Amplificador **desligado e fora da tomada**. Espere **5 minutos** antes de abrir.
      Os capacitores da fonte demoram a descarregar.
- [ ] Não toque na placa da fonte nem no transformador (lado de 230 V). Só vamos mexer na placa frontal.
- [ ] Tire **fotos** dos dois lados da placa frontal (componentes e trilhas) antes de começar
      e salve em `docs/img/`. Elas ajudam a seguir as trilhas.
- [ ] Multímetro no modo **continuidade** (símbolo de som/diodo). Encoste uma ponta na outra:
      ele tem que **apitar**. Se apitar, o modo está certo.

**Como medir continuidade:** encoste uma ponta em cada ponto. Se apitar, os pontos estão ligados por uma trilha.
Se **não** apitar, passe o multímetro para **resistência (Ω, escala 20k)** e meça de novo:

| Leitura | Significado |
|---|---|
| menos de 10 Ω | ligação direta (trilha) |
| 10 Ω a 1 kΩ | ligado através de um resistor em série; conta como "ligado" e anote o valor |
| cerca de 4,7 kΩ | ligado através do resistor de pull-up (as redes R907/R908) |
| sem leitura (OL / 1) | não ligado |

Dica: meça nas **soldas** do lado de baixo da placa, onde as pontas firmam melhor.
Cuidado para a ponta não escorregar e encostar em duas soldas ao mesmo tempo.

---

## 1. Como contar os pinos

**Chip de 40 pernas (controlador T9311DP)** e **chip de 8 pernas (24C01, IC801)**: procure o
**chanfro** (meia-lua) ou a **bolinha** numa ponta do chip. Visto **por cima** (lado dos componentes):

```
          chanfro
      ┌─────◡─────┐
   1  │●          │ 40          (no 24C01:  1 ┤ ├ 8
   2  │           │ 39                      2 ┤ ├ 7
   3  │           │ 38                      3 ┤ ├ 6  = SCL
  ... │           │ ...           GND = 4 ┤ ├ 5  = SDA )
  20  │           │ 21
      └───────────┘
```

O pino 1 fica ao lado do chanfro, e a contagem desce por um lado e **sobe pelo outro**.
**Atenção:** visto **por baixo** (lado das soldas), tudo fica **espelhado**: o pino 1 passa para o outro lado.

---

## 2. Achar o GND e confirmar o controlador

O pino 4 da 24C01 é o GND com certeza. Vamos usá-lo como referência.

| # | Ponta A | Ponta B | Esperado | Resultado |
|---|---|---|---|---|
| 2.1 | 24C01 pino 4 (GND) | controlador pino **20** | apita (8051: pino 20 = GND) | |
| 2.2 | 24C01 pino 8 (VCC) | controlador pino **40** | apita (8051: pino 40 = +5 V) | |
| 2.3 | 24C01 pino 4 (GND) | 24C01 pino 8 (VCC) | **não** apita (senão, há curto) | |

Se 2.1 e 2.2 apitarem, o controlador é da família 8051, e o resto do roteiro vale como está.
Se não apitarem, anote qual pino do controlador apita com o GND e com o VCC, e me avise.

---

## 3. Orientação do LCD (onde fica o pino 1)

O LCD tem uma fileira de 16 pinos. Meça **as duas pontas da fileira** contra o GND (24C01 pino 4):

| # | Ponta A | Ponta B | Resultado |
|---|---|---|---|
| 3.1 | pino da **ponta esquerda** da fileira | 24C01 pino 4 (GND) | |
| 3.2 | pino da **ponta direita** da fileira | 24C01 pino 4 (GND) | |

A ponta que apitar é o **pino 1 (VSS)**. Marque esse pino com uma caneta ou um pedaço de fita.

Confirme a seguir, contando a partir do pino 1:

| # | Pino do LCD | Ponta B | Esperado | Resultado |
|---|---|---|---|---|
| 3.3 | pino 2 (VDD) | 24C01 pino 8 (VCC) | apita | |
| 3.4 | pino 3 (VO) | pino do meio do trimpot **VR901** (10k, à esquerda do LCD) | apita | |
| 3.5 | pinos 15 e 16 (ou pads A/K) | — | anote para onde vão | |

---

## 4. As três perguntas principais

### 4.1 O RW (pino 5) está ligado ao GND?

| Pino do LCD | Ponta B | Resultado |
|---|---|---|
| pino 5 (RW) | 24C01 pino 4 (GND) | |

- **Apitou:** o controlador só escreve no LCD. Um fio a menos para capturar.
- **Não apitou:** o RW vai ao controlador. Achamos qual pino na seção 5.

### 4.2 Modo 4 ou 8 bits? (pinos 7 a 10 = D0 a D3)

Meça cada um contra o GND e depois **contra os pinos vizinhos**:

| Pino do LCD | contra o GND | contra o VCC | Observação |
|---|---|---|---|
| pino 7 (D0) | | | |
| pino 8 (D1) | | | |
| pino 9 (D2) | | | |
| pino 10 (D3) | | | |

- **Todos ligados ao GND, ou soltos (sem solda/trilha):** **modo 4 bits**. Só D4–D7 levam dados.
- **Cada um vai para um pino do controlador:** **modo 8 bits** (confirmamos na seção 5).

### 4.3 O I2C sai da placa frontal?

As fotos da petervis.com mostram que a **placa de entradas** ("SP103 IO BOARD ISS1") tem **dois PT2314**
(U52 e U53) e um conector de 4 vias, **CON51**, marcado **GND, CL, DA1, DA0**:
um relógio (SCL) comum aos dois e **um SDA separado para cada PT2314**. Isso é necessário porque os dois
têm o mesmo endereço I2C fixo. O cabo branco de 4 fios vai do CON51 até a placa frontal.

| # | Ponta A | Ponta B | Resultado |
|---|---|---|---|
| 4.3a | 24C01 pino 5 (SDA) | cada pino do conector do cabo de 4 fios na placa frontal | pino nº ___ |
| 4.3b | 24C01 pino 6 (SCL) | cada pino desse mesmo conector | pino nº ___ |
| 4.3c | cada pino desse conector | pernas do controlador | CL → ___, DA0 → ___, DA1 → ___ |

O CON51 é um ótimo lugar para prender o analisador no I2C: são só 3 sinais mais o GND, e os pinos ficam acessíveis.

---

## 5. Mapa LCD → controlador

Para cada pino do LCD, deixe uma ponta nele e **passe a outra pelas 40 pernas** do controlador
até apitar. Comece pelos grupos sugeridos, porque é ali que costumam estar:

- **Pernas 32 a 39** (porta P0 do 8051): essa porta precisa de pull-ups externos (as redes R907/R908
  de 4,7k). Mas nas fotos as redes ficam do lado das pernas 1–20, então talvez sirvam aos 7 botões.
- **Pernas 21 a 28** (P2), **1 a 8** (P1) e **10 a 17** (P3).

Pino 1 do controlador: na foto, o chanfro fica do lado **esquerdo** (onde está o logotipo "T"). Visto por cima,
o pino 1 é o **canto inferior esquerdo**: a fileira de baixo vai de 1 a 20 (da esquerda para a direita) e a de cima
de 21 a 40 (da direita para a esquerda).

| Pino do LCD | Sinal | Perna do controlador | Leitura (apito / Ω) | Observação |
|---|---|---|---|---|
| 4 | RS | | | |
| 5 | RW | | | (pule se 4.1 apitou) |
| 6 | E | | | |
| 7 | D0 | | | (pule se 4 bits) |
| 8 | D1 | | | (pule se 4 bits) |
| 9 | D2 | | | (pule se 4 bits) |
| 10 | D3 | | | (pule se 4 bits) |
| 11 | D4 | | | |
| 12 | D5 | | | |
| 13 | D6 | | | |
| 14 | D7 | | | |

E as linhas do I2C:

| Pino da 24C01 | Sinal | Perna do controlador | Observação |
|---|---|---|---|
| 5 | SDA | | |
| 6 | SCL | | |

Se um pino do LCD **não apitar com nenhuma perna**, meça em resistência: ele pode passar por um resistor
em série. Se mesmo assim não achar, siga a trilha pela foto e anote até onde ela vai.

---

## 6. (Opcional) Medir tensão com o amplificador ligado

Faça **só depois** de todas as medições acima, e só se se sentir seguro. Prenda a ponta **preta**
com uma garra jacaré no GND **antes** de ligar o amplificador. Com a ponta vermelha, encoste
**apenas** no ponto indicado. Multímetro em **tensão contínua (V⎓, escala 20 V)**.

| Ponto (ponta vermelha) | Esperado | Resultado |
|---|---|---|
| LCD pino 2 (VDD) | cerca de 5 V | |
| LCD pino 3 (VO) | 0,3 a 1,5 V | |

Desligue o amplificador da tomada antes de soltar a garra.

---

## Quando terminar

Mande as tabelas preenchidas, ou fotos delas, junto com as fotos da placa. Com isso eu preparo:

1. O **plano de ligação** do analisador: qual fio vai de qual ponto da placa para qual pino do Pico,
   com os resistores de proteção de 1 kΩ.
2. A **configuração de captura**: canais, trigger no E e frequência.
