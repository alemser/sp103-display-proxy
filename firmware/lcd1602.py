"""Driver simples para LCD 16x2 (HD44780) em modo 4 bits, só escrita (RW no GND).

Ligação na bancada (docs/bancada-ligacao.md): RS=GP16, E=GP17, D4..D7=GP18..GP21.
Como o RW fica no GND, não dá para ler o busy flag: esperamos o tempo máximo
de cada comando (datasheet do HD44780).
"""

import time
from machine import Pin


class Lcd1602:
    def __init__(self, rs=16, e=17, d4=18):
        self.rs = Pin(rs, Pin.OUT, value=0)
        self.e = Pin(e, Pin.OUT, value=0)
        self.d = [Pin(d4 + i, Pin.OUT, value=0) for i in range(4)]
        self.reset()

    # --- baixo nível -------------------------------------------------------

    def _nibble(self, n):
        for i in range(4):
            self.d[i].value((n >> i) & 1)
        self.e.value(1)
        time.sleep_us(1)                # o pulso do E precisa de pelo menos 450 ns
        self.e.value(0)
        time.sleep_us(1)

    def _byte(self, b, rs):
        self.rs.value(rs)
        self._nibble(b >> 4)
        self._nibble(b & 0x0F)
        time.sleep_us(50)               # a maioria dos comandos leva 37 µs

    def command(self, b):
        self._byte(b, 0)
        if b in (0x01, 0x02):           # Clear e Home levam 1,52 ms
            time.sleep_ms(2)

    def data(self, b):
        self._byte(b, 1)

    def reset(self):
        """Reinicia o display. Também corrige o "texto quebrado" do modo 4 bits:
        se um mau contato fizer o display perder meio byte, ele passa a juntar
        as metades erradas até ser reiniciado. Esta sequência resincroniza."""
        time.sleep_ms(50)
        self.on = True
        self.resync()
        self.command(0x01)              # limpa

    def resync(self):
        """A parte do reset() que resincroniza o modo 4 bits, sem apagar a tela.
        No meio da sequência o display só recebe comandos de configuração e de
        endereço; quem chama reescreve o texto e os desenhos depois."""
        # Sequência do datasheet para entrar no modo 4 bits, partindo de qualquer estado.
        self.rs.value(0)
        for wait_us in (4500, 150, 150):
            self._nibble(0x3)
            time.sleep_us(wait_us)
        self._nibble(0x2)               # agora em 4 bits
        time.sleep_us(150)
        self.command(0x28)              # 4 bits, 2 linhas, 5x8
        self.command(0x0C if self.on else 0x08)   # display ligado (ou não), sem cursor
        self.command(0x06)              # escreve da esquerda para a direita

    def display(self, on):
        self.on = on
        self.command(0x0C if on else 0x08)

    # --- alto nível --------------------------------------------------------

    def define_char(self, code, rows):
        """Grava um caractere personalizado (código 0 a 7, 8 linhas de 5 pontos)."""
        self.command(0x40 | (code << 3))
        for r in rows:
            self.data(r)
        self.command(0x80)              # volta para a DDRAM

    def write_line(self, row, text):
        """Escreve as 16 posições de uma linha (completa com espaços)."""
        text = (text + " " * 16)[:16]
        self.command(0x80 | (0x40 if row else 0x00))
        for c in text:
            self.data(ord(c))

    def show(self, line1, line2):
        self.write_line(0, line1)
        self.write_line(1, line2)
