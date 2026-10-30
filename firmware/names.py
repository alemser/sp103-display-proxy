"""Textos personalizados do display: nomes das entradas e telas de inicialização.

Ficam no arquivo names.json do Pico e são editados pela página web (PUT /names):

    {"inputs": {"TUNER": "Rega Planar 2", ...},
     "boot":   ["Welcome", "Alessandro"],     # no lugar de "ACOUSTIC" / "SOLUTIONS"
     "about":  ["", ""],                      # no lugar de "Amplifier SP103" / "SW version 1.0"
     "vu":     {"on": False, "auto": True, "floor": -40, "top": 0,     # VU meter (vu.py);
                "layout": "bars", "relay": "192.168.178.105"}}       # floor/top: escala manual
                                                                     # layout: bars, deck, scale

Texto vazio (ou ausente) = o texto original do amp. As linhas das telas de
inicialização são centralizadas, como as originais.

O "relay" é o IP da placa com o sp103-vu-relay: o MicroPython não resolve nomes .local.
"""

import json

from amp_state import INPUTS

FILE = "names.json"
MAX_LEN = 16                    # uma linha do LCD
SCREENS = ("boot", "about")
VU_DEFAULT = {"on": False, "auto": True, "floor": -40, "top": 0, "layout": "bars",
              "relay": "192.168.178.105"}
VU_LAYOUTS = ("bars", "deck", "scale")   # os mesmos de vu.LAYOUTS
VU_FLOOR = (-60, -10)           # o piso da escala do VU, em dBFS
VU_TOP = (-30, 0)               # o topo (barra cheia), em dBFS
VU_SPAN = 10                    # o topo fica pelo menos 10 dB acima do piso


def load():
    try:
        with open(FILE) as f:
            return validate(json.load(f))
    except (OSError, ValueError):
        return validate({})     # sem arquivo (ou arquivo estragado): textos originais


def save(cfg):
    with open(FILE, "w") as f:
        json.dump(cfg, f)


def _text(value, what):
    """Confere um texto para o LCD e devolve sem espaços nas pontas."""
    if not isinstance(value, str):
        raise ValueError("%s must be text" % what)
    value = value.strip()
    if len(value) > MAX_LEN:
        raise ValueError("'%s' has %d characters; the display fits %d" % (value, len(value), MAX_LEN))
    for c in value:
        # O LCD não tem acentos, e no conjunto de caracteres dele "\" vira "¥" e "~" vira seta.
        if not (" " <= c <= "}") or c == "\\":
            raise ValueError("'%s': the display has no '%s' character (no accents)" % (value, c))
    return value


def validate(cfg):
    """Confere a configuração. Devolve uma cópia completa e limpa, ou levanta ValueError."""
    if not isinstance(cfg, dict):
        raise ValueError("the configuration must be a JSON object")
    if cfg and "inputs" not in cfg and "vu" not in cfg and not any(k in cfg for k in SCREENS):
        cfg = {"inputs": cfg}   # formato antigo: só a tabela de entradas
    inputs = cfg.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise ValueError("'inputs' must be a JSON object")
    clean = {"inputs": {}}
    for key, value in inputs.items():
        if key not in INPUTS:
            raise ValueError("unknown input: %s (use %s)" % (key, ", ".join(INPUTS)))
        value = _text(value, "the name for " + key)
        if value and value != key:
            clean["inputs"][key] = value
    for screen in SCREENS:
        lines = cfg.get(screen) or ["", ""]
        if not isinstance(lines, list) or len(lines) != 2:
            raise ValueError("'%s' must be a list with 2 lines" % screen)
        clean[screen] = [_text(v, screen + " line") for v in lines]
    clean["vu"] = _vu(cfg.get("vu") or {})
    return clean


def _vu(vu):
    if not isinstance(vu, dict):
        raise ValueError("'vu' must be a JSON object")
    out = dict(VU_DEFAULT)
    out.update(vu)
    for key in ("on", "auto"):
        if not isinstance(out[key], bool):
            raise ValueError("vu '%s' must be true or false" % key)
    floor = out["floor"]
    if isinstance(floor, bool) or not isinstance(floor, (int, float)) \
            or not VU_FLOOR[0] <= floor <= VU_FLOOR[1]:
        raise ValueError("the VU floor must be a number from %d to %d dB" % VU_FLOOR)
    top = out["top"]
    if isinstance(top, bool) or not isinstance(top, (int, float)) \
            or not VU_TOP[0] <= top <= VU_TOP[1]:
        raise ValueError("the VU top must be a number from %d to %d dB" % VU_TOP)
    if top - floor < VU_SPAN:
        raise ValueError("the VU top must be at least %d dB above the floor" % VU_SPAN)
    if out["layout"] not in VU_LAYOUTS:
        raise ValueError("the VU layout must be one of: " + ", ".join(VU_LAYOUTS))
    relay = out["relay"]
    parts = relay.split(".") if isinstance(relay, str) else []
    if len(parts) != 4 or not all(p.isdigit() and int(p) < 256 for p in parts):
        raise ValueError("the VU source must be an IP address, like 192.168.178.105")
    return {"on": out["on"], "auto": out["auto"], "floor": int(floor), "top": int(top),
            "layout": out["layout"], "relay": relay}


def _center(text):
    left = (MAX_LEN - len(text)) // 2
    return (" " * left + text + " " * MAX_LEN)[:MAX_LEN]


def rewrite(line1, line2, cfg):
    """Troca os textos personalizados numa tela completa. As outras telas passam sem mudança."""
    name = line2.rstrip()
    if line1.startswith("Volume ") and name in cfg["inputs"]:
        return line1, (cfg["inputs"][name] + " " * MAX_LEN)[:MAX_LEN]
    if line1.strip() == "ACOUSTIC" and line2.strip() == "SOLUTIONS":
        screen = "boot"
    elif line1.strip() == "Amplifier SP103" and line2.strip().startswith("SW version "):
        screen = "about"
    else:
        return line1, line2
    new1, new2 = cfg[screen]
    return (_center(new1) if new1 else line1), (_center(new2) if new2 else line2)
