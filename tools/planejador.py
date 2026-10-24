#!/usr/bin/env python3
"""Planejador da escrita sem corte: dá para mostrar cada nome personalizado na troca de entrada?

    python3 tools/planejador.py                          # os nomes de firmware/names.json
    python3 tools/planejador.py DAB "Streaming"          # um nome qualquer
    python3 tools/planejador.py --host 192.168.178.108   # os nomes que estão no Pico (GET /names)
    python3 tools/planejador.py --paleta DAB             # que caracteres cabem em cada coluna

O modelo (docs/opcoes-intercepcao.md, "Opções para mudar os caracteres"):

- Na troca de entrada, o controlador redesenha a tela UMA vez: 32 caracteres, na ordem
  (linha 1, colunas 0..15; linha 2, colunas 0..15). A linha 1 não muda (o volume é o mesmo),
  então as letras dela podem ser "emprestadas": a original continua na tela.
- Cada caractere do controlador (a "fonte") pode:
    * ir para a própria célula, com bits zerados (o valor tem que estar contido na fonte);
    * ir para outra célula: o endereço injetado tem que estar contido (em bits) na fonte
      ANTERIOR (o controlador solta só o D7 para ler o busy flag) ou no próprio endereço;
    * não ser escrito (comando nulo).
- Os desenhos próprios (CGRAM, códigos 1..7) valem até desligar o amp e são os mesmos para
  todos os nomes. Para mostrar o desenho k, a fonte precisa ter os bits de k. Maiúsculas só
  cabem no desenho 7 (ver glyph_codes).
- Só a tela normal (troca de entrada). As telas ao ligar mudam as duas linhas e quase não
  sobram fontes: "Oceano Amplifier" / "SP103" não sai.
- Precisa: o RW e o RS fracos no 1 (medido) e o LCD ignorar o comando 0x00 (falta testar).

Saída: para cada nome, em quantos dos 64 volumes (-78.75 a 0 dB) o nome sai inteiro, e
quais desenhos próprios ele usa.
"""

import argparse

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

from sp103_screens import volume_line   # noqa: E402

VOLUMES = [-78.75 + 1.25 * i for i in range(64)]
GLYPH_CODES = range(1, 8)       # o 0 (caixa) é usado na barra de volume: fica como está
# Ao ligar, o desenho k tem as linhas (8-k)..7 cheias; o Pico só apaga pontos. Maiúsculas, dígitos
# e minúsculas altas usam 7 linhas: só cabem no 7 (1 ponto mais baixas). Minúsculas baixas e com
# perna usam as linhas 2-7: cabem no 6 ou no 7.
SHORT = "acemnorsuvwxzgpqy"


def glyph_codes(ch):
    return (6, 7) if ch in SHORT else (7,)
LAST_BYTE_BEFORE = 0x20         # o último caractere do redesenho anterior (um espaço, quase sempre)


def contained(a, b):
    """Os bits de a estão todos em b?"""
    return a & b == a


def slots(line1, line2):
    """(fonte, endereço próprio, byte anterior no barramento) dos 32 caracteres, em ordem."""
    out, prev = [], LAST_BYTE_BEFORE
    for base, line in ((0x00, line1), (0x40, line2)):
        for col, c in enumerate(line):
            out.append((ord(c), base + col, prev))
            prev = ord(c)
    return out


def can_place(value, addr, slot):
    src, home, prev = slot
    return contained(value, src) and (contained(addr, home) or contained(addr, prev & 0x7F))


def match(targets, sources, glyphs):
    """Emparelhamento máximo (caminhos aumentantes): célula da linha 2 -> fonte.

    targets: [(endereço, caractere)]; glyphs: {caractere: código}. Devolve {célula: fonte}."""
    edges = []
    for addr, ch in targets:
        values = [ord(ch)] + ([glyphs[ch]] if ch in glyphs else [])
        edges.append([i for i, s in enumerate(sources) if any(can_place(v, addr, s) for v in values)])
    owner = {}

    def augment(t, seen):
        for i in edges[t]:
            if i not in seen:
                seen.add(i)
                if i not in owner or augment(owner[i], seen):
                    owner[i] = t
                    return True
        return False

    for t in range(len(targets)):
        augment(t, set())
    return {t: i for i, t in owner.items()}


def plan(original, name, glyphs, volume):
    """Quantas células da linha 2 saem certas, e o emparelhamento."""
    line2 = (original + " " * 16)[:16]
    target = (name + " " * 16)[:16]
    sources = slots(volume_line(volume), line2)
    cells = [(0x40 + col, ch) for col, ch in enumerate(target)]
    got = match(cells, sources, glyphs)
    return len(got), got, sources, cells


def score(names, glyphs):
    """Para cada nome, em quantos volumes ele sai inteiro."""
    return {orig: sum(plan(orig, name, glyphs, v)[0] == 16 for v in VOLUMES)
            for orig, name in names.items()}


def cells_ok(names, glyphs):
    """Total de células certas, somando todos os nomes e volumes (para comparar desenhos)."""
    return sum(plan(orig, name, glyphs, v)[0] for orig, name in names.items() for v in VOLUMES)


def missing_chars(names):
    """Caracteres que faltam em algum volume, sem desenhos próprios (os candidatos a desenho)."""
    need = set()
    for orig, name in names.items():
        for v in VOLUMES:
            n, got, _, cells = plan(orig, name, {}, v)
            if n < 16:
                need |= {cells[t][1] for t in range(16) if t not in got}
    return sorted(need)


def best_glyphs(names, limit):
    """Escolhe até `limit` caracteres para virar desenho, e o código de cada um.

    Busca gulosa: a cada passo, o par (caractere, código) que mais aumenta o total de
    volumes em que os nomes saem inteiros. (Testar todas as combinações levaria horas.)"""
    glyphs = {}
    best = cells_ok(names, glyphs)
    while len(glyphs) < limit:
        step = None
        for ch in missing_chars(names):
            if ch in glyphs:
                continue
            for k in glyph_codes(ch):
                if k in glyphs.values():
                    continue
                n = cells_ok(names, dict(glyphs, **{ch: k}))
                if n > (step[1] if step else best):
                    step = ((ch, k), n)
        if step is None:
            break                       # nenhum desenho a mais ajuda
        glyphs[step[0][0]] = step[0][1]
        best = step[1]
    return glyphs, score(names, glyphs)


def palette(orig, cols=16):
    """Os caracteres que cabem em cada coluna da linha 2, em todos os volumes (cada célula
    sozinha: duas células podem disputar a mesma fonte; confira o nome com o planejador)."""
    chars = [chr(c) for c in range(0x20, 0x7F)]
    screens = [slots(volume_line(v), (orig + " " * 16)[:16]) for v in VOLUMES]
    for col in range(cols):
        ok = [ch for ch in chars
              if all(any(can_place(ord(ch), 0x40 + col, s) for s in sources) for sources in screens)]
        print("  col %2d: %s" % (col + 1, "".join(ok).replace(" ", "␣")))


def show_plan(orig, name, glyphs, volume):
    n, got, sources, cells = plan(orig, name, glyphs, volume)
    print("    volume %.2f, linha 1 %r, original %r:" % (volume, volume_line(volume), orig))
    for t, (addr, ch) in enumerate(cells):
        if t in got:
            src, home, _ = sources[got[t]]
            how = "desenho %d" % glyphs[ch] if ch in glyphs and not contained(ord(ch), src) else repr(ch)
            where = "própria célula" if home == addr else "desviada da %s col %d" % (
                "linha 1" if home < 0x40 else "linha 2", home % 0x40 + 1)
            print("      col %2d %-12s <- fonte %r (%s)" % (addr - 0x3F, how, chr(src), where))
        else:
            print("      col %2d %r          <- SEM FONTE" % (addr - 0x3F, ch))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pairs", nargs="*", help="ENTRADA NOME [ENTRADA NOME ...]")
    ap.add_argument("--host", help="lê os nomes do Pico (GET /names)")
    ap.add_argument("--desenhos", type=int, default=7, help="desenhos próprios disponíveis (0 a 7)")
    ap.add_argument("--detalhe", type=float, metavar="VOLUME", help="mostra o plano neste volume")
    ap.add_argument("--paleta", metavar="ENTRADA", help="caracteres possíveis em cada coluna (ex.: DAB)")
    args = ap.parse_args()

    if args.paleta:
        print("Paleta da entrada %s (linha 2, sem desenhos próprios):" % args.paleta)
        palette(args.paleta, 8)
        return

    if args.pairs:
        names = dict(zip(args.pairs[::2], args.pairs[1::2]))
    elif args.host:
        from urllib.request import urlopen
        names = json.load(urlopen("http://%s/names" % args.host, timeout=10))["config"]["inputs"]
    else:
        with open(os.path.join(HERE, "..", "firmware", "names.json")) as f:
            names = json.load(f)["inputs"]

    print("Sem desenhos próprios:")
    for orig, ok in score(names, {}).items():
        print("  %-9s -> %-16r sai inteiro em %2d de %d volumes" % (orig, names[orig], ok, len(VOLUMES)))
    print("  células certas (de %d): %d" % (16 * len(names) * len(VOLUMES), cells_ok(names, {})))
    print("  faltam (em algum volume):", " ".join(repr(c) for c in missing_chars(names)))

    glyphs, s = best_glyphs(names, args.desenhos)
    print("\nCom até %d desenhos próprios: %s" % (
        args.desenhos, ", ".join("%r = código %d" % kv for kv in sorted(glyphs.items())) or "nenhum ajuda"))
    for orig, ok in s.items():
        print("  %-9s -> %-16r sai inteiro em %2d de %d volumes" % (orig, names[orig], ok, len(VOLUMES)))
    print("  células certas (de %d): %d" % (16 * len(names) * len(VOLUMES), cells_ok(names, glyphs)))

    if args.detalhe is not None:
        print()
        for orig, name in names.items():
            print("  %s -> %r" % (orig, name))
            show_plan(orig, name, glyphs, args.detalhe)


if __name__ == "__main__":
    main()
