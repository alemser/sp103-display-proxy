"""Os códigos do controle remoto do SP103, como pulsos na linha do IR.

Decodificados do perfil do groove-rig (internal/catalog/profiles/acoustic_solutions_sp103.yaml,
capturados com um Broadlink RM4): início longo, os bytes 20 E1 DB, o byte do comando, o inverso
dele e dois bits 1, sempre com o bit menos significativo primeiro. Depois de 24 ms vem o aviso
de repetição, igual ao que o controle manda. tools/test_ir.py confere os bits contra o perfil.

frame() roda igual no MicroPython (Pico) e no Python do computador.
"""

COMMANDS = {"power_toggle": 0x77, "volume_up": 0x7F, "volume_down": 0x7B, "bass": 0x6F, "treble": 0x73,
            "select_phono": 0x63, "select_tuner": 0x57, "select_tape_aux": 0x5B, "select_cd": 0x67,
            "select_dvd": 0x6B, "select_dab": 0x5F}

PREFIX = (0x20, 0xE1, 0xDB)
# Tempos em µs medidos na própria linha do IR, com o controle real (2026-11-06). Os do Broadlink
# são cerca de 5% mais longos, e com eles o controlador não reagiu.
LEADER_MARK, LEADER_SPACE = 9030, 4470
MARK, SPACE_0, SPACE_1 = 600, 545, 1665
REPEAT_GAP = 22750
END_SPACE = 1000                        # a lista sempre termina em espaço (ver ir.py)


def frame(command):
    """Os tempos em µs de um comando: linha em 0, linha solta, linha em 0, e assim por diante."""
    code = COMMANDS[command]
    words = [LEADER_MARK, LEADER_SPACE]
    for byte in PREFIX + (code, code ^ 0xFF):
        for bit in range(8):
            words += [MARK, SPACE_1 if byte >> bit & 1 else SPACE_0]
    words += [MARK, SPACE_1, MARK, SPACE_1]
    words += [MARK, REPEAT_GAP, LEADER_MARK, LEADER_SPACE, MARK, END_SPACE]
    return words
