"""GET /device: quem é esta ponte e o que ela sabe fazer.

O contrato está no repositório amp-link (docs/contrato.md). Tudo aqui é fixo enquanto o programa
roda: o cliente lê uma vez ao conectar. A versão é a mesma do GET /update.

describe() roda igual no MicroPython (Pico) e no Python do computador (tools/test_device.py).
"""

from amp_state import INPUTS, INPUT_IDS, STEP, VOLUME_MIN

API = 1                         # só muda quando algo deixa de ser compatível
MODEL = "Acoustic Solutions SP103"
TONE_DB = 14                    # bass e treble: de -14 a 14, de 1 em 1
COLUMNS, ROWS = 16, 2
FEATURES = ("tone", "balance", "loudness", "speakers", "config", "vu", "info_screens", "bus_log", "update")


def describe(version):
    return {"api": API, "model": MODEL, "bridge_version": version,
            "volume_db": {"min": VOLUME_MIN, "max": 0, "step": STEP},
            "tone_db": {"min": -TONE_DB, "max": TONE_DB, "step": 1},
            "inputs": [{"id": INPUT_IDS[name], "name": name} for name in INPUTS],
            "display": {"columns": COLUMNS, "rows": ROWS},
            "features": list(FEATURES)}


async def handle(req, writer):
    """Rota /device (ver web.Publisher)."""
    import ota
    from web import reply, reply_json
    if req.path != "/device":
        return await reply(writer, "404 Not Found", "text/plain", b"not found\n")
    await reply_json(writer, describe(await ota.current_version()))
