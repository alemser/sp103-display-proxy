"""Textos personalizados do display: nomes das entradas e telas de inicialização.

Ficam no arquivo names.json do Pico e são editados pela página web (PUT /names):

    {"inputs": {"TUNER": "Rega Planar 2", ...},
     "boot":   ["Welcome", "Alessandro"],     # no lugar de "ACOUSTIC" / "SOLUTIONS"
     "about":  ["", ""],                      # no lugar de "Amplifier SP103" / "SW version 1.0"
     "vu":     {"on": False, "auto": True, "floor": -40, "top": 0,     # VU meter (vu.py);
                "layout": "bars", "relay": "192.168.178.105"}}       # floor/top: escala manual
                                                                     # layout: bars, deck, scale, kx393
     "info":   {"on": False, "mode": "temp", "fixed": "track",          # telas de informação
                "show": ["track", "pos", "side", "stylus"], "secs": 8,  # (screens.py, info.py)
                "alert": True, "clock": True, "scroll": True,
                "utc_offset": 0, "eu_dst": True, "source": "",          # source "" = a do VU
                "turntable": ["PHONO", "TUNER"]}}                       # a agulha só nessas entradas

Texto vazio (ou ausente) = o texto original do amp. As linhas das telas de
inicialização são centralizadas, como as originais.

O "relay" é o IP da placa com o sp103-vu-relay: o MicroPython não resolve nomes .local.
O "source" das telas é o IP de quem fala o contrato docs/api-telas.md; vazio = o mesmo do VU.
"""

import json

from amp_state import INPUTS

FILE = "names.json"
MAX_LEN = 16                    # uma linha do LCD
SCREENS = ("boot", "about")
VU_DEFAULT = {"on": False, "auto": True, "floor": -40, "top": 0, "layout": "bars",
              "relay": "192.168.178.105"}
VU_LAYOUTS = ("bars", "deck", "scale", "kx393")   # os mesmos de vu.LAYOUTS
VU_FLOOR = (-60, -10)           # o piso da escala do VU, em dBFS
VU_TOP = (-30, 0)               # o topo (barra cheia), em dBFS
VU_SPAN = 10                    # o topo fica pelo menos 10 dB acima do piso
INFO_DEFAULT = {"on": False, "mode": "temp", "fixed": "track", "show": ["track", "pos", "side", "stylus"],
                "secs": 8, "alert": True, "clock": True, "scroll": True, "utc_offset": 0, "eu_dst": True,
                "source": "", "turntable": ["PHONO", "TUNER"]}
INFO_KINDS = ("track", "pos", "side", "stylus")   # os mesmos de screens.KINDS
INFO_SECS = (3, 60)
INFO_OFFSET = (-12, 14)         # horas a partir do UTC


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
    if cfg and not any(k in cfg for k in ("inputs", "vu", "info") + SCREENS):
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
    clean["info"] = _info(cfg.get("info") or {})
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
    if not _is_ip(out["relay"]):
        raise ValueError("the VU source must be an IP address, like 192.168.178.105")
    return {"on": out["on"], "auto": out["auto"], "floor": int(floor), "top": int(top),
            "layout": out["layout"], "relay": out["relay"]}


def _is_ip(text):
    parts = text.split(".") if isinstance(text, str) else []
    return len(parts) == 4 and all(p.isdigit() and int(p) < 256 for p in parts)


def _info(info):
    if not isinstance(info, dict):
        raise ValueError("'info' must be a JSON object")
    out = dict(INFO_DEFAULT)
    out.update(info)
    for key in ("on", "alert", "clock", "scroll", "eu_dst"):
        if not isinstance(out[key], bool):
            raise ValueError("info '%s' must be true or false" % key)
    if out["mode"] not in ("temp", "fixed"):
        raise ValueError("the info mode must be temp or fixed")
    if out["fixed"] not in INFO_KINDS:
        raise ValueError("the fixed screen must be one of: " + ", ".join(INFO_KINDS))
    show = out["show"]
    if not isinstance(show, list) or any(k not in INFO_KINDS for k in show):
        raise ValueError("info 'show' must be a list with some of: " + ", ".join(INFO_KINDS))
    secs = out["secs"]
    if isinstance(secs, bool) or not isinstance(secs, int) or not INFO_SECS[0] <= secs <= INFO_SECS[1]:
        raise ValueError("the seconds per screen must be a whole number from %d to %d" % INFO_SECS)
    offset = out["utc_offset"]
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) \
            or not INFO_OFFSET[0] <= offset <= INFO_OFFSET[1] or offset * 4 != int(offset * 4):
        raise ValueError("the UTC offset must be in hours, from %d to %d (quarters allowed)" % INFO_OFFSET)
    turntable = out["turntable"]
    if not isinstance(turntable, list) or any(k not in INPUTS for k in turntable):
        raise ValueError("info 'turntable' must be a list with some of: " + ", ".join(INPUTS))
    source = out["source"].strip() if isinstance(out["source"], str) else None
    if source is None or (source and not _is_ip(source)):
        raise ValueError("the info source must be an IP address, or empty to use the VU source")
    return {"on": out["on"], "mode": out["mode"], "fixed": out["fixed"],
            "show": [k for k in INFO_KINDS if k in show], "secs": secs, "alert": out["alert"],
            "clock": out["clock"], "scroll": out["scroll"], "utc_offset": offset, "eu_dst": out["eu_dst"],
            "source": source, "turntable": [k for k in INPUTS if k in turntable]}


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
