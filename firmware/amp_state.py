"""Leitor de telas do SP103: transforma as 2 linhas do LCD no estado do amplificador.

Roda igual no MicroPython (Pico) e no Python do computador (testes).

Uso:
    st = AmpState()
    if st.update(linha1, linha2, agora_ms):
        print(st.to_dict())      # algo mudou

As linhas são as 16 posições de cada linha do LCD, com os códigos originais
(chr(0) = a caixa das barras, ver docs/descobertas-protocolo.md).

IMPORTANTE: só chame update() com a tela COMPLETA. O controlador redesenha
caractere por caractere (cerca de 8,5 ms por tela), e no meio do caminho a
linha pode misturar o valor velho com o novo ("Volume -27.75" no lugar de
"-27.50"). O sniffer deve esperar alguns milissegundos sem escritas antes de chamar.
"""

BOX = "\x00"                    # caractere personalizado 0: caixa das barras
INPUTS = ("PHONO", "TUNER", "TAPE/AUX", "CD", "DVD", "DAB")
# Identificadores estáveis, em minúsculas, para clientes da API.
INPUT_IDS = {"PHONO": "phono", "TUNER": "tuner", "TAPE/AUX": "tape_aux",
             "CD": "cd", "DVD": "dvd", "DAB": "dab"}
VOLUME_MIN = -78.75             # PT2314: 0 a -78,75 dB, passos de 1,25 dB
STEP = 1.25

# Os campos do estado, na ordem em que aparecem no JSON.
FIELDS = ("power", "volume_db", "input", "input_id", "input_name", "bass_db", "treble_db", "balance",
          "loudness", "speakers", "screen", "firmware", "lcd", "updated_at")


def _db(text):
    """'-28.75' -> -28.75, ou None se não for um número válido."""
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        return None


def _is_step(v, lo, hi):
    """Confere se v está entre lo e hi e é múltiplo de 1,25 dB."""
    if v is None or v < lo or v > hi:
        return False
    k = v / STEP
    return abs(k - round(k)) < 0.001


def _ends_db(line):
    """Tira o ' dB' do fim da linha, ou devolve None se não terminar assim."""
    line = line.rstrip()
    if not line.endswith(" dB"):
        return None
    return line[:-3]


def _bar(line):
    """Barra bipolar da linha 2: '<>' nas colunas 7 e 8, caixas de um lado.

    Devolve (caixas_esquerda, caixas_direita), ou None se a linha não for uma barra.
    """
    if line[7:9] != "<>":
        return None
    left, right = line[:7], line[9:]
    for part in (left, right):
        for c in part:
            if c != BOX and c != " ":
                return None
    # As caixas ficam coladas no "<>": à esquerda terminam na coluna 6, à direita começam na 9.
    nl = len(left) - len(left.rstrip(BOX))
    nr = len(right) - len(right.lstrip(BOX))
    if left.count(BOX) != nl or right.count(BOX) != nr:
        return None
    return nl, nr


def _choice(line):
    """Linha 2 de Loudness/Speakers: 'OFF' e 'ON', a escolhida entre '< >'.

    Devolve True (ON), False (OFF) ou None.
    """
    a, b = line.find("<"), line.find(">")
    if a < 0 or b < a or line.count("<") != 1 or line.count(">") != 1:
        return None
    chosen = line[a + 1:b].strip()
    rest = (line[:a] + " " + line[b + 1:]).split()
    if chosen == "ON" and rest == ["OFF"]:
        return True
    if chosen == "OFF" and rest == ["ON"]:
        return False
    return None


def parse(line1, line2):
    """Reconhece uma tela completa.

    Devolve (nome_da_tela, {campo: valor}) com só os campos que a tela mostra,
    ou ("unknown", {}) se a tela não for reconhecida.
    """
    l1, l2 = line1, line2

    # Tela normal ou de volume: "Volume -28.75 dB"
    if l1.startswith("Volume "):
        v = _ends_db(l1[7:])
        v = _db(v) if v is not None else None
        if not _is_step(v, VOLUME_MIN, 0):
            return "unknown", {}
        name = l2.rstrip()
        if name in INPUTS:
            return "normal", {"volume_db": v, "input": name}
        # Barra de volume: caixas a partir da coluna 0, depois só espaços.
        boxes = l2.rstrip(" ")
        if boxes == BOX * len(boxes):
            return "volume", {"volume_db": v}
        return "unknown", {}

    # Bass e Treble: "Bass   2 dB", "Bass -10 dB", "Treble   0 dB" (sem '+')
    for word, field in (("Bass", "bass_db"), ("Treble", "treble_db")):
        if l1.startswith(word + " "):
            v = _ends_db(l1[len(word):])
            v = _db(v) if v is not None else None
            bar = _bar(l2)
            if v is None or v != int(v) or abs(v) > 14 or bar is None:
                return "unknown", {}
            nl, nr = bar
            # Cada caixa vale 2 dB: a barra precisa concordar com o número.
            if (v < 0 and (nr or nl != int(-v) // 2)) or (v > 0 and (nl or nr != int(v) // 2)) \
                    or (v == 0 and (nl or nr)):
                return "unknown", {}
            return word.lower(), {field: int(v)}

    # Balance: "Balance -5.00 dB", "Balance-10.00 dB"; centrado: "Balance <level>"
    if l1.startswith("Balance"):
        bar = _bar(l2)
        if bar is None:
            return "unknown", {}
        nl, nr = bar
        if l1.rstrip() == "Balance <level>":
            if nl or nr:
                return "unknown", {}
            return "balance", {"balance": {"side": None, "db": 0.0}}
        v = _ends_db(l1[7:])
        v = _db(v) if v is not None else None
        if not _is_step(v, VOLUME_MIN, -STEP):
            return "unknown", {}
        # Uma caixa a cada 5 dB, do lado da barra. O número não diz o lado.
        if (nl and nr) or (nl + nr) != int(-v // 5):
            return "unknown", {}
        if nl == 0 and nr == 0:
            side = None             # menos de 5 dB: a barra ainda não aparece
        else:
            side = "L" if nl else "R"
        return "balance", {"balance": {"side": side, "db": v}}

    if l1.strip() == "Loudness":
        on = _choice(l2)
        if on is None:
            return "unknown", {}
        return "loudness", {"loudness": on}

    if l1.strip() == "Speakers":
        on = _choice(l2)
        if on is None:
            return "unknown", {}
        return "speakers", {"speakers": on}

    if l1.strip() == "ACOUSTIC" and l2.strip() == "SOLUTIONS":
        return "boot", {}

    if l1.strip() == "Amplifier SP103" and l2.strip().startswith("SW version "):
        return "about", {"firmware": l2.strip()[len("SW version "):]}

    return "unknown", {}


def lcd_text(line):
    """Linha do LCD em texto legível: a caixa vira '■', outros códigos viram '·'."""
    out = ""
    for c in line:
        if c == BOX:
            out += "■"
        elif " " <= c <= "~":
            out += c
        else:
            out += "·"
    return out


class AmpState:
    """Estado do amplificador, montado a partir das telas que o controlador desenha."""

    def __init__(self, names=None):
        self.names = names or {}    # tabela de nomes (names.py): {"TUNER": "Rega Planar 2"}
        self.power = None           # "on" quando alguma tela é reconhecida
        self.volume_db = None
        self.input = None           # nome original no amp: "TUNER"
        self.input_id = None        # identificador estável da entrada: "tuner"
        self.input_name = None      # nome da tabela, ou o original: "Rega Planar 2"
        self.bass_db = None
        self.treble_db = None
        self.balance = None         # {"side": "L"/"R"/None, "db": -5.0}
        self.loudness = None
        self.speakers = None
        self.screen = None
        self.firmware = None
        self.lcd = ["", ""]
        self.updated_at = None      # milissegundos (relógio de quem chama)
        self.version = 0            # aumenta a cada mudança (útil para /events)

    def update(self, line1, line2, now_ms=None):
        """Lê uma tela completa. Devolve True se algum campo mudou."""
        screen, values = parse(line1, line2)
        changed = False
        lcd = [lcd_text(line1), lcd_text(line2)]
        if lcd != self.lcd:
            self.lcd = lcd
            changed = True
        if screen != self.screen:
            self.screen = screen
            changed = True
        if screen != "unknown" and self.power != "on":
            self.power = "on"
            changed = True
        for key in values:
            if getattr(self, key) != values[key]:
                setattr(self, key, values[key])
                changed = True
        if self._names_changed():
            changed = True
        if changed:
            self.version += 1
            self.updated_at = now_ms
        return changed

    def set_names(self, names, now_ms=None):
        """Troca a tabela de nomes. Devolve True se o input_name mudou."""
        self.names = names
        if self._names_changed():
            self.version += 1
            self.updated_at = now_ms
            return True
        return False

    def _names_changed(self):
        if self.input is None:
            return False
        iid, name = INPUT_IDS[self.input], self.names.get(self.input, self.input)
        if (iid, name) == (self.input_id, self.input_name):
            return False
        self.input_id, self.input_name = iid, name
        return True

    def to_dict(self):
        d = {}
        for key in FIELDS:
            d[key] = getattr(self, key)
        d["version"] = self.version
        return d
