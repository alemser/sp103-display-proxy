"""Cópia da memória do LCD do amp (HD44780), montada com os bytes que o sniffer lê do barramento.

Roda igual no MicroPython (Pico) e no Python do computador (tools/test_sniffer.py).

Cada "palavra" é o barramento no instante em que o E desce (é nessa borda que o LCD lê o byte),
na ordem dos fios GP2..GP12 (docs/ligacao-analisador.md):

    bit 0 = E   bit 1 = RS   bit 2 = RW   bits 3..10 = D0..D7

Uso:
    bus = Bus()
    for palavra in sniffer.read():
        bus.feed(palavra)
    ...depois de ~2 ms sem palavras novas (o controlador terminou de redesenhar):
    if bus.pending:
        linha1, linha2 = bus.take()
"""

RS = 1 << 1
RW = 1 << 2
DATA_SHIFT = 3


class Lcd:
    """A parte do HD44780 que importa para reconstruir a tela (ver tools/hd44780_decode.py)."""

    def __init__(self):
        self.ddram = bytearray(b" " * 0x80)   # 0x00-0x27 = linha 1, 0x40-0x67 = linha 2
        self.addr = 0
        self.inc = 1
        self.shift = 0                        # deslocamento do display (comando shift)
        self.cgram_mode = False

    def command(self, b):
        if b & 0x80:
            self.addr, self.cgram_mode = b & 0x7F, False
        elif b & 0x40:
            self.cgram_mode = True
        elif b & 0x20:
            pass                              # Function set: o amp usa sempre 8 bits
        elif b & 0x10:
            if b & 0x08:
                self.shift += -1 if b & 0x04 else 1
        elif b & 0x04:
            self.inc = 1 if b & 0x02 else -1
        elif b & 0x02:
            self.addr, self.shift, self.cgram_mode = 0, 0, False
        elif b & 0x01:
            for i in range(0x80):
                self.ddram[i] = 0x20
            self.addr, self.shift, self.inc, self.cgram_mode = 0, 0, 1, False

    def data(self, b):
        if self.cgram_mode:
            return                            # desenho de caractere personalizado: ignoramos
        self.ddram[self.addr] = b
        a = self.addr + self.inc
        # O HD44780 pula de 0x27 para 0x40 e de 0x67 para 0x00.
        if a == 0x28:
            a = 0x40
        elif a == 0x68:
            a = 0x00
        elif a == 0x3F:
            a = 0x27
        elif a == -1:
            a = 0x67
        self.addr = a & 0x7F

    def lines(self):
        """As duas linhas visíveis, com os códigos originais (chr(0) = caixa das barras)."""
        return tuple("".join(chr(self.ddram[base + (col + self.shift) % 40]) for col in range(16))
                     for base in (0x00, 0x40))


class Bus:
    def __init__(self):
        self.lcd = Lcd()
        self.pending = False                  # houve escrita desde o último take()
        self.writes = 0
        self.reads = 0
        self.clears = 0                       # "Clear display": o controlador acabou de ligar

    def feed(self, word):
        if word & RW:
            self.reads += 1                   # leitura do busy flag: não muda a tela
            return
        value = (word >> DATA_SHIFT) & 0xFF
        if word & RS:
            self.lcd.data(value)
        else:
            if value == 0x01:
                self.clears += 1
            self.lcd.command(value)
        self.writes += 1
        self.pending = True

    def take(self):
        self.pending = False
        return self.lcd.lines()
