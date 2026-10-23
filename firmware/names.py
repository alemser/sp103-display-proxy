"""Tabela de nomes das entradas: "TUNER" -> "Rega Planar 2".

Fica no arquivo names.json do Pico e é editada pela página web (PUT /names).
Entrada sem nome na tabela continua com o nome original do amp.
"""

import json

from amp_state import INPUTS

FILE = "names.json"
MAX_LEN = 16                    # uma linha do LCD


def load():
    try:
        with open(FILE) as f:
            return validate(json.load(f))
    except (OSError, ValueError):
        return {}               # sem arquivo (ou arquivo estragado): nomes originais


def save(names):
    with open(FILE, "w") as f:
        json.dump(names, f)


def validate(names):
    """Confere a tabela. Devolve uma cópia limpa, ou levanta ValueError com o motivo."""
    if not isinstance(names, dict):
        raise ValueError("the table must be a JSON object")
    clean = {}
    for key, value in names.items():
        if key not in INPUTS:
            raise ValueError("unknown input: %s (use %s)" % (key, ", ".join(INPUTS)))
        if not isinstance(value, str):
            raise ValueError("the name for %s must be text" % key)
        value = value.strip()
        if len(value) > MAX_LEN:
            raise ValueError("'%s' has %d characters; the display fits %d" % (value, len(value), MAX_LEN))
        for c in value:
            # O LCD não tem acentos, e no conjunto de caracteres dele "\" vira "¥" e "~" vira seta.
            if not (" " <= c <= "}") or c == "\\":
                raise ValueError("'%s': the display has no '%s' character (no accents)"
                                 % (value, c))
        if value and value != key:
            clean[key] = value  # vazio ou igual ao original: não precisa guardar
    return clean


def rewrite(line1, line2, names):
    """Troca o nome da entrada na tela normal. As outras telas passam sem mudança."""
    if line1.startswith("Volume ") and line2.rstrip() in names:
        line2 = (names[line2.rstrip()] + " " * MAX_LEN)[:MAX_LEN]
    return line1, line2
