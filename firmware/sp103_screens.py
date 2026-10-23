"""Desenha as telas do SP103 a partir de um estado (o caminho inverso de amp_state.parse).

Formatos tirados das capturas (docs/descobertas-protocolo.md). Os marcados com
"suposição" ainda não foram vistos no amp.
"""

BOX = "\x00"

# Caracteres personalizados que o controlador grava ao ligar (CGRAM).
CGRAM = [
    [0x00, 0x1F, 0x11, 0x11, 0x11, 0x11, 0x1F, 0x00],     # 0: caixa vazia (barras)
] + [
    [0x1F if row >= 8 - n else 0x00 for row in range(8)]  # 1..7: barras de n linhas
    for n in range(1, 8)
]


def _pad(text):
    return (text + " " * 16)[:16]


def volume_line(db):
    # "Volume -28.75 dB". Com um dígito só ("-5.00"), suposição: alinhado à direita.
    return _pad("Volume" + ("%7.2f" % db) + " dB")


def normal(volume_db, input_name):
    return volume_line(volume_db), _pad(input_name)


def volume_bar(volume_db):
    # 10 caixas a -28,75 dB: proporcional a (78,75 + dB) / 78,75 das 16 colunas.
    n = int((78.75 + volume_db) / 78.75 * 16)
    return volume_line(volume_db), _pad(BOX * n)


def bipolar_bar(left, right):
    """Barra com '<>' nas colunas 7 e 8 e caixas coladas de um lado."""
    return _pad(" " * (7 - left) + BOX * left + "<>" + BOX * right)


def tone(word, db):
    """Bass ou Treble: 'Bass   2 dB', 'Bass -10 dB'. Uma caixa a cada 2 dB."""
    n = abs(db) // 2
    bar = bipolar_bar(n, 0) if db < 0 else bipolar_bar(0, n)
    return _pad(word + ("%4d" % db) + " dB"), bar


def balance(side, db):
    if side is None and db == 0:
        return _pad("Balance <level>"), bipolar_bar(0, 0)
    n = int(-db // 5)                   # uma caixa a cada 5 dB
    bar = bipolar_bar(n, 0) if side == "L" else bipolar_bar(0, n)
    return _pad("Balance" + ("%6.2f" % db) + " dB"), bar


def choice(word, on):
    # Visto: Loudness OFF e Speakers ON. Os outros dois casos são suposição.
    line2 = "   OFF   < ON > " if on else " < OFF >   ON   "
    return _pad("   " + word), line2


def boot():
    return "    ACOUSTIC    ", "    SOLUTIONS   "


def about(version="1.0"):
    return "Amplifier SP103 ", _pad(" SW version " + version)
