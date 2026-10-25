"""Planos de escrita: os passos que fazem o display do amp mostrar um nome personalizado.

Roda igual no MicroPython (Pico) e no Python do computador (tools/test_plano.py).
Base: docs/opcoes-intercepcao.md (testes 1 a 4). O Pico só PUXA fios para 0.

O redesenho do controlador (tela normal) tem 32 caracteres, em ordem: linha 1, colunas 0..15;
linha 2, colunas 0..15. Cada caractere k são 4 pulsos do E:

    R (lê o busy flag)   C (comando "vá para o endereço a_k")   R   D (escreve c_k)

Na leitura, o controlador solta só o D7: os outros fios ficam com o último byte escrito.

O que o Pico faz com um caractere ("fonte"):
- HOME: deixa ir para a própria célula, com bits zerados (o valor tem que estar contido na fonte);
- MOVE_I: na leitura depois do caractere anterior, injeta "vá para t" (t contido nos bits do
  caractere anterior) e anula (0x00) o comando do controlador: a fonte cai em t;
- MOVE_II: na leitura depois do comando dela, injeta "vá para t" (t contido no próprio endereço);
- SUPPRESS: no comando dela, espera a leitura do busy flag acabar e puxa o RS e zera os dados
  ANTES da escrita: o LCD recebe o comando 0x00 (ignorado) e a célula não muda.

Tempo: o LCD lê RS e RW na SUBIDA do E e os dados na DESCIDA. O Pico vê um pulso ~3 µs depois
da subida (filtro de ruído), então "agora" só pode zerar dados; RS e RW são puxados antes da
subida ("depois deste pulso", ou "na próxima leitura").

Fontes da linha 1: só as que não mudam com o volume ("Volume", o espaço da coluna 6 e " dB")
e cuja anterior também não muda; a célula delas não é reescrita e continua certa.

Guarda: o Pico aposta que a entrada é a atual. Se o controlador estiver desenhando outra
(troca de entrada), os passos "estritos" não batem e o motor desiste: a tela sai original e o
nome personalizado aparece no redesenho atrasado (2 a 6 s depois). Antes de qualquer passo
destrutivo na linha 2, o motor confere as primeiras `guard` letras do nome original.

Cada passo: (palavra que dispara, falhas permitidas, ação). Ação = máscara dos fios a puxar
(bit 0 = RS, bit 1 = RW, bits 2..9 = D0..D7) + quando: agora (no meio do pulso que disparou),
NEXT_PULSE (antes do pulso seguinte) ou NEXT_READ (antes da próxima leitura do busy flag).
Falhas: quantos pulsos que não batem o motor aceita antes de desistir (ANY = sem limite).
"""

from hd44780 import RS, RW, DATA_SHIFT

AFTER = 1 << 10                 # espera o pulso que disparou acabar
THEN_READ = 1 << 11             # e depois o RW subir (começo da leitura do busy flag)
THEN_END = 1 << 12              # e depois o RW descer (fim da leitura: o próximo pulso é a escrita)
NEXT_READ = AFTER | THEN_READ
AFTER_READ = AFTER | THEN_READ | THEN_END
TRIGGER_MASK = 0x3FF            # o PIO compara E, RS, RW e D0..D6 (sem o D7, que muda nas leituras)
ANY = 0xFFFFFFFF
M_RS, M_RW = 1, 2
LINE1_STATIC = (0, 1, 2, 3, 4, 5, 6, 13, 14, 15)    # "Volume", ' ', ' ', 'd', 'B' (sp103_screens.volume_line)
LINE1_SOURCES = (1, 2, 3, 4, 5, 6, 14, 15)           # fixas e com a anterior também fixa
LINE1_TEXT = "Volume " + " " * 6 + " dB"             # só as colunas fixas importam
MAX_NODES = 3000                                     # limite da busca (no Pico, ~1 s no pior caso)


def data_mask(bits):
    return (bits & 0xFF) << 2


def word(rs, data):
    """A palavra que o PIO lê no meio do pulso (E=1), numa escrita."""
    return 1 | (RS if rs else 0) | ((data & 0xFF) << DATA_SHIFT)


def cmd(addr):
    return word(0, 0x80 | addr)


def within(a, b):
    return a & b == a


def pad(text):
    return (text + " " * 16)[:16]


def guard_len(original, inputs):
    """Quantas letras do nome original separam esta entrada de todas as outras (1 ou 2)."""
    me = pad(original)
    for n in range(1, 17):
        if all(pad(o)[:n] != me[:n] for o in inputs if o != original):
            return n
    return 16


class Plan:
    def __init__(self, steps, glyphs_used, guard, risk):
        self.steps = steps              # [(palavra, falhas, ação)]
        self.glyphs = glyphs_used       # códigos de desenho próprio usados
        self.guard = guard
        self.risk = risk                # reservado ao simulador; o planejador estrito sempre deixa vazio

    def words(self):
        """Os passos achatados, na ordem da fila do PIO (a palavra sem o D7: TRIGGER_MASK)."""
        out = []
        for t, m, a in self.steps:
            out += (t & TRIGGER_MASK, m, a)
        return out


def make(original, target, inputs, glyphs=None, current=None):
    """O plano para mostrar `target` quando o controlador desenha a entrada `original`.

    glyphs: {caractere: código} dos desenhos próprios gravados no LCD agora.
    current: a linha 2 que o LCD mostra agora (células já certas não precisam ser escritas),
    ou None. Usa sempre a guarda completa; se o nome não couber sem ambiguidade, não toca no
    LCD. Devolve um Plan, ou None se o nome não couber."""
    full = guard_len(original, inputs)
    # Sem contar com a tela atual o plano escreve todas as células: vale sempre, e a busca é
    # rápida. Contar com ela ("manter" células já certas) às vezes explode a busca: só depois.
    for cur in (None, current) if current is not None else (None,):
        plan = _make(original, target, glyphs or {}, cur, full, [])
        if plan is not None:
            return plan
    return None


def _make(original, target, glyphs, current, guard, risk):
    orig, tgt = pad(original), pad(target)
    # As fontes, em ordem: (k, endereço, caractere, anterior ou None).
    slots = []
    for k in range(32):
        line2 = k >= 16
        col = k - 16 if line2 else k
        ch = orig[col] if line2 else LINE1_TEXT[col]
        prev = None
        if line2:
            prev = ord(orig[col - 1]) if col else ord("B")
        elif k in LINE1_SOURCES:
            prev = ord(LINE1_TEXT[col - 1])
        slots.append((k, (0x40 if line2 else 0) + col, ord(ch), prev))
    # A última letra da guarda já pode agir no próprio D (se bateu, a entrada é certa); as
    # anteriores só conferem. first_free = a 1ª fonte da linha 2 que pode ser destrutiva.
    first_free = 16 + guard - 1

    # Candidatos para cada célula da linha 2: (fonte, método, alvo, valor).
    cands = []
    for col in range(16):
        addr, want = 0x40 + col, ord(tgt[col])
        values = [want] + ([glyphs[tgt[col]]] if tgt[col] in glyphs else [])
        opts = []
        dirty = col < guard
        if dirty:
            # Conferida pela guarda: o controlador escreve o original (a última letra da guarda pode
            # ter máscara); se não for o alvo, outra fonte (depois da guarda) escreve por cima.
            if orig[col] == tgt[col] or (16 + col == first_free and within(want, ord(orig[col]))):
                opts.append((16 + col, "HOME", addr, want))
        elif current is not None and current[col] == tgt[col]:
            opts.append((None, "KEEP", addr, want))
        for k, a, c, prev in slots:
            if k < 16 and (k not in LINE1_SOURCES or dirty):
                continue            # (a linha 1 vem antes: a guarda escreveria por cima)
            if 16 <= k <= first_free:
                continue            # as fontes da guarda só escrevem na própria célula (acima)
            for v in values:
                if not within(v, c):
                    continue
                if k >= 16 and a == addr:
                    opts.append((k, "HOME", addr, v))
                if prev is not None and within(addr, prev & 0x7F) and a != addr and k != first_free:
                    if k < 16 or k > first_free:
                        opts.append((k, "MOVE_I", addr, v))
                if k > first_free and a != addr and within(addr, a):
                    opts.append((k, "MOVE_II", addr, v))
        # Preferir: o controlador escrever sem mudança (nenhum passo), manter a célula, sem
        # máscara, fontes da linha 2. O resto só desempata, para o Pico (cuja ordenação não é
        # estável) e o computador acharem o mesmo plano.
        opts.sort(key=lambda o: (not (o[1] == "HOME" and o[3] == want), o[1] != "KEEP", o[3] != want,
                                 o[0] is not None and o[0] < 16, -1 if o[0] is None else o[0], o[1], o[3]))
        cands.append(opts)

    chosen = {}                     # célula -> candidato
    method = {}                     # fonte -> candidato
    nodes = [0]

    def masked(k):
        """A fonte k tem passo no próprio D (máscara) ou em volta dele (supressão)? Então a
        seguinte não pode ser MOVE_I (que precisa do D desta para injetar). None = sem escolha."""
        o = method.get(k)
        return None if o is None else o[3] != slots[k][2]

    def clash(o):
        """A escolha o é impossível com o que já foi escolhido? (fonte já usada, ou a regra do
        MOVE_I: a fonte anterior não pode ter ação "agora" no D, que é o mesmo pulso.)"""
        k = o[0]
        if k is None:
            return False
        if k in method:
            return True
        if o[1] == "MOVE_I" and masked(k - 1):
            return True
        if o[1] == "MOVE_I" and k - 1 > first_free and masked(k - 1) is None:
            return True             # a anterior ainda sem célula: seria suprimida (conferir já poda muito)
        nxt = method.get(k + 1)
        return o[3] != slots[k][2] and nxt is not None and nxt[1] == "MOVE_I"

    def leaf_ok():
        # As fontes da linha 2 sem célula (depois da guarda) são suprimidas, antes do D delas: não
        # podem vir antes de um MOVE_I. (As da guarda sem célula escrevem a própria, e outra cobre.)
        for k in range(first_free + 1, 32):
            if k not in method and k + 1 < 32 and (method.get(k + 1) or "  ")[1] == "MOVE_I":
                return False
        return True

    def search(left):
        nodes[0] += 1
        if nodes[0] > MAX_NODES:
            return False
        if not left:
            return leaf_ok()
        # A célula com menos opções que ainda valem; se alguma ficou sem nenhuma, este caminho morreu.
        best, best_opts = None, None
        for col in left:
            opts = [o for o in cands[col] if not clash(o)]
            if not opts:
                return False
            if best_opts is None or len(opts) < len(best_opts):
                best, best_opts = col, opts
        rest = [c for c in left if c != best]
        for o in best_opts:
            chosen[best] = o
            if o[0] is not None:
                method[o[0]] = o
            if search(rest):
                return True
            del chosen[best]
            if o[0] is not None:
                del method[o[0]]
        return False

    if not search(list(range(16))):
        return None
    return Plan(_steps(slots, chosen, first_free), sorted({o[3] for o in chosen.values() if o[3] < 8}),
                guard, risk)


def _steps(slots, chosen, first_free):
    by_slot = {o[0]: o for o in chosen.values() if o[0] is not None}
    steps = []
    anchored = set()                # fontes cujo C já tem passo

    def anchor(k, action=0, misses=ANY):
        steps.append((cmd(slots[k][1]), misses, action))
        anchored.add(k)

    def d_step(k, action, misses):
        steps.append((word(1, slots[k][2]), misses, action))

    for k, a, c, prev in slots:
        o = by_slot.get(k)
        nxt = by_slot.get(k + 1) if k < 31 else None
        inject_next = nxt is not None and nxt[1] == "MOVE_I"
        # O 'V' da coluna 1 é sempre conferido: só a tela de volume começa com 'V' (os menus e as
        # telas de ligar, não), e sem isso um menu com letras iguais nas mesmas colunas
        # ("Speakers" tem um 'e' onde "Volume" tem) receberia os passos.
        suppress = o is None and k > first_free
        plain = o is None or (o[1] == "HOME" and o[3] == c)    # o controlador escreve sem mudança
        if plain and not 16 <= k <= first_free and not inject_next and not suppress and k:
            continue                # nada a fazer nesta fonte
        if suppress:
            # No comando: espera a leitura do busy flag acabar e puxa antes da escrita.
            steps.append((cmd(a), ANY, AFTER_READ | M_RS | data_mask(0xFF)))
            continue
        # 1. O comando do controlador para esta fonte.
        if o is not None and o[1] == "MOVE_II":
            inject = (a & 0x7F) & ~o[2]
            anchor(k, NEXT_READ | M_RW | data_mask(inject))
            d_misses = 2            # a escrita injetada e a nova leitura do busy flag
        elif o is not None and o[1] == "MOVE_I":
            steps.append((cmd(a), 3, data_mask(0xFF)))      # anula o comando (vira 0x00)
            d_misses = 1
        else:
            if k not in anchored:
                anchor(k)
            d_misses = 1
        # 2. O caractere: conferir (estrito) e agir.
        if o is not None:
            action = data_mask(c & ~o[3])                   # zerar bits até o valor
        else:
            action = 0                                      # só conferir (guarda ou linha 1)
        if inject_next:
            if action:
                raise ValueError("MOVE_I depois de uma ação no D")  # garantido pela busca
            t = by_slot[k + 1][2]
            action = NEXT_READ | M_RW | data_mask((c & 0x7F) & ~t)
        if action or 16 <= k <= first_free or inject_next or k == 0 or (o is not None and o[1] != "HOME"):
            d_step(k, action, d_misses)
    return steps


# Desenhos próprios. Ao ligar, o controlador grava o desenho k com as linhas (8-k)..7 cheias; o
# Pico só apaga pontos. Os desenhos 6 e 7 servem para letras (o 6 tem as linhas 2-7, o 7 as 1-7).
GLYPH_CODES = (6, 7)
# Minúsculas da fonte do HD44780 (5x8; bit 4 = ponto da esquerda).
FONT = {
    "a": (0x00, 0x00, 0x0E, 0x01, 0x0F, 0x11, 0x0F, 0x00), "b": (0x10, 0x10, 0x16, 0x19, 0x11, 0x11, 0x1E, 0x00),
    "c": (0x00, 0x00, 0x0E, 0x10, 0x10, 0x11, 0x0E, 0x00), "d": (0x01, 0x01, 0x0D, 0x13, 0x11, 0x11, 0x0F, 0x00),
    "e": (0x00, 0x00, 0x0E, 0x11, 0x1F, 0x10, 0x0E, 0x00), "f": (0x06, 0x09, 0x08, 0x1C, 0x08, 0x08, 0x08, 0x00),
    "g": (0x00, 0x0F, 0x11, 0x11, 0x0F, 0x01, 0x0E, 0x00), "h": (0x10, 0x10, 0x16, 0x19, 0x11, 0x11, 0x11, 0x00),
    "i": (0x04, 0x00, 0x0C, 0x04, 0x04, 0x04, 0x0E, 0x00), "j": (0x02, 0x00, 0x06, 0x02, 0x02, 0x12, 0x0C, 0x00),
    "k": (0x10, 0x10, 0x12, 0x14, 0x18, 0x14, 0x12, 0x00), "l": (0x0C, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E, 0x00),
    "m": (0x00, 0x00, 0x1A, 0x15, 0x15, 0x11, 0x11, 0x00), "n": (0x00, 0x00, 0x16, 0x19, 0x11, 0x11, 0x11, 0x00),
    "o": (0x00, 0x00, 0x0E, 0x11, 0x11, 0x11, 0x0E, 0x00), "p": (0x00, 0x00, 0x1E, 0x11, 0x1E, 0x10, 0x10, 0x00),
    "q": (0x00, 0x00, 0x0D, 0x13, 0x0F, 0x01, 0x01, 0x00), "r": (0x00, 0x00, 0x16, 0x19, 0x10, 0x10, 0x10, 0x00),
    "s": (0x00, 0x00, 0x0E, 0x10, 0x0E, 0x01, 0x1E, 0x00), "t": (0x08, 0x08, 0x1C, 0x08, 0x08, 0x09, 0x06, 0x00),
    "u": (0x00, 0x00, 0x11, 0x11, 0x11, 0x13, 0x0D, 0x00), "v": (0x00, 0x00, 0x11, 0x11, 0x11, 0x0A, 0x04, 0x00),
    "w": (0x00, 0x00, 0x11, 0x11, 0x15, 0x15, 0x0A, 0x00), "x": (0x00, 0x00, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x00),
    "y": (0x00, 0x00, 0x11, 0x11, 0x0F, 0x01, 0x0E, 0x00), "z": (0x00, 0x00, 0x1F, 0x02, 0x04, 0x08, 0x1F, 0x00),
}


def glyph_rows(ch, code):
    """As 8 linhas do desenho `code` para a letra `ch`, ou None se não couber. Letras altas no
    desenho 7 descem 1 ponto (a linha 0 não está cheia ao ligar)."""
    rows = FONT.get(ch)
    if rows is None:
        return None
    full = [0x1F if r >= 8 - code else 0 for r in range(8)]
    for shift in (0, 1):
        moved = (0,) * shift + rows[:8 - shift]
        if not any(rows[8 - shift:]) and all(m & ~f == 0 for m, f in zip(moved, full)):
            return moved
    return None


def shown(target, glyphs):
    """O que o LCD mostra com o nome personalizado (letras com desenho viram o código)."""
    return "".join(chr(glyphs[c]) if c in glyphs else c for c in pad(target))


def choose(names, inputs):
    """Planos para todos os nomes {original: personalizado}, escolhendo até 2 desenhos próprios
    (os mesmos para todos). Devolve ({letra: código}, {original: Plan ou None}). O plano de verdade
    é feito a cada redesenho, com a tela do momento (make com current)."""
    def plans(glyphs):
        # Possível se sair contando com a tela que o LCD terá: o nome original (logo depois da
        # troca de entrada) ou o próprio nome personalizado (os redesenhos seguintes).
        out = {}
        for o, t in names.items():
            out[o] = make(o, t, inputs, glyphs, pad(o)) and make(o, t, inputs, glyphs, shown(t, glyphs))
        return out
    base = plans({})
    letters = sorted({c for o, t in names.items() if base[o] is None for c in t if c in FONT})
    best = ({}, base)
    score = lambda r: sum(p is not None for p in r.values())
    options = [{c: k} for c in letters for k in GLYPH_CODES if glyph_rows(c, k)]
    options += [{a: 6, b: 7} for a in letters for b in letters if a != b and glyph_rows(a, 6) and glyph_rows(b, 7)]
    for g in options:
        if score(best[1]) == len(names):
            break
        r = plans(g)
        if score(r) > score(best[1]):
            best = (g, r)
    return best


def describe(plan):
    """Os passos em texto (para conferir)."""
    from hd44780 import describe as dw
    out = []
    for t, m, a in plan.steps:
        what = []
        if a & THEN_END:
            what.append("antes da escrita seguinte")
        elif a & THEN_READ:
            what.append("na leitura seguinte")
        elif a & AFTER:
            what.append("antes do pulso seguinte")
        if a & M_RS:
            what.append("RS")
        if a & M_RW:
            what.append("RW")
        if (a >> 2) & 0xFF:
            what.append("D=%02X" % ((a >> 2) & 0xFF))
        out.append("%-40s falhas %-3s %s" % (dw(t), "∞" if m == ANY else m, " ".join(what) or "(só conferir)"))
    return "\n".join(out)
