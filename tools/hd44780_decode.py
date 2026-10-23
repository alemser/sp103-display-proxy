#!/usr/bin/env python3
"""
Decodificador do barramento HD44780 (LCD 16x2) a partir de uma captura do
LogicAnalyzer (gusmanb).

Uso:
    python3 tools/hd44780_decode.py captura.lac
    python3 tools/hd44780_decode.py captura.csv --freq 10000000

O que ele faz:
  1. Procura cada borda de DESCIDA do sinal E (é nela que o LCD "lê" o byte).
  2. Nesse instante, lê RS, RW e D0..D7.
       RS=0 -> comando     RS=1 -> caractere
       RW=1 -> leitura (o controlador está lendo o LCD, normalmente o busy flag)
  3. Traduz cada comando para texto e mantém uma cópia da memória do LCD
     (DDRAM), para mostrar como a tela fica depois de cada bloco de escrita.

Ligação esperada (canal do analisador -> sinal do LCD), igual ao docs/ligacao-analisador.md:
    CH1=E  CH2=RS  CH3=RW  CH4..CH11=D0..D7
Se você deu nomes aos canais no programa (E, RS, RW, D0..D7), os nomes têm prioridade.
"""

import argparse
import base64
import csv
import json
import sys

# Ligação padrão: número do canal (1 = Channel 1) para cada sinal.
DEFAULT_MAP = {"E": 1, "RS": 2, "RW": 3,
               "D0": 4, "D1": 5, "D2": 6, "D3": 7,
               "D4": 8, "D5": 9, "D6": 10, "D7": 11}

SIGNALS = list(DEFAULT_MAP)

# Silêncio no barramento maior que isso (em µs) encerra um "bloco" de escrita.
BURST_GAP_US = 2000


# ---------------------------------------------------------------------------
# Leitura dos arquivos
# ---------------------------------------------------------------------------

def load_lac(path):
    """Arquivo .lac = JSON salvo pelo LogicAnalyzer (File > Save)."""
    with open(path, encoding="utf-8-sig") as f:
        doc = json.load(f)
    settings = doc["Settings"]
    freq = settings["Frequency"]
    pre = settings.get("PreTriggerSamples", 0)
    # Modo burst: a captura é feita de vários trechos de PostTriggerSamples amostras,
    # cada um começando num novo trigger. Os trechos ficam colados um no outro.
    # O LoopCount nem sempre vem salvo no arquivo; então também detectamos o burst
    # pelo tamanho: mais amostras do que presamples + postsamples.
    post = settings["PostTriggerSamples"]
    burst = 0
    by_number, by_name = {}, {}
    for ch in settings["CaptureChannels"]:
        raw = ch.get("Samples")
        if raw is None:
            continue
        samples = base64.b64decode(raw) if isinstance(raw, str) else bytes(raw)
        number = ch["ChannelNumber"] + 1          # no arquivo começa em 0
        by_number[number] = samples
        if len(samples) > pre + post:
            burst = post
        name = (ch.get("ChannelName") or "").strip().upper()
        if name:
            by_name[name] = samples
    return freq, pre, burst, by_number, by_name


def load_csv(path):
    """Arquivo .csv = File > Export. Não tem frequência, só 0/1 por coluna."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = [h.strip() for h in rows[0]]
    cols = list(zip(*rows[1:]))
    by_number, by_name = {}, {}
    for i, h in enumerate(header):
        samples = bytes(int(v) for v in cols[i])
        if h.upper().startswith("CHANNEL "):
            # O CSV numera pela ordem das colunas, não pelo canal físico.
            # Funciona se os canais marcados forem 1..11 em sequência.
            by_number[int(h.split()[1])] = samples
        else:
            by_name[h.upper()] = samples
            by_number[i + 1] = samples
    return by_number, by_name


def pick_signals(by_number, by_name):
    sig = {}
    for s in SIGNALS:
        if s in by_name:
            sig[s] = by_name[s]
        elif DEFAULT_MAP[s] in by_number:
            sig[s] = by_number[DEFAULT_MAP[s]]
    missing = [s for s in ("E", "RS") if s not in sig]
    if missing:
        sys.exit(f"Faltam os sinais {missing} na captura.")
    return sig


# ---------------------------------------------------------------------------
# Tradução dos comandos
# ---------------------------------------------------------------------------

def describe_command(b):
    if b & 0x80:
        return f"Set DDRAM addr 0x{b & 0x7F:02X}"
    if b & 0x40:
        return f"Set CGRAM addr 0x{b & 0x3F:02X}"
    if b & 0x20:
        return ("Function set: " + ("8 bits" if b & 0x10 else "4 bits") + ", "
                + ("2 linhas" if b & 0x08 else "1 linha") + ", "
                + ("5x10" if b & 0x04 else "5x8"))
    if b & 0x10:
        return ("Shift " + ("display" if b & 0x08 else "cursor") + " para a "
                + ("direita" if b & 0x04 else "esquerda"))
    if b & 0x08:
        return ("Display " + ("ON" if b & 0x04 else "OFF")
                + ", cursor " + ("ON" if b & 0x02 else "OFF")
                + ", pisca " + ("ON" if b & 0x01 else "OFF"))
    if b & 0x04:
        return ("Entry mode: " + ("incrementa" if b & 0x02 else "decrementa")
                + (", desloca display" if b & 0x01 else ""))
    if b & 0x02:
        return "Return home"
    if b & 0x01:
        return "Clear display"
    return "NOP (0x00)"


class Lcd:
    """Cópia simplificada da memória do HD44780, para reconstruir a tela."""

    def __init__(self):
        self.ddram = [0x20] * 0x80      # 0x00-0x27 = linha 1, 0x40-0x67 = linha 2
        self.addr = 0
        self.inc = 1
        self.shift = 0                  # deslocamento do display (comando shift)
        self.cgram_mode = False
        self.eight_bit = True

    def command(self, b):
        if b & 0x80:
            self.addr, self.cgram_mode = b & 0x7F, False
        elif b & 0x40:
            self.cgram_mode = True
        elif b & 0x20:
            self.eight_bit = bool(b & 0x10)
        elif b & 0x10:
            if b & 0x08:
                self.shift += -1 if b & 0x04 else 1
        elif b & 0x04:
            self.inc = 1 if b & 0x02 else -1
        elif b & 0x02:
            self.addr, self.shift, self.cgram_mode = 0, 0, False
        elif b & 0x01:
            self.ddram = [0x20] * 0x80
            self.addr, self.shift, self.inc, self.cgram_mode = 0, 0, 1, False

    def data(self, b):
        if self.cgram_mode:
            return                      # caractere personalizado: ignoramos
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

    def screen(self):
        lines = []
        for base in (0x00, 0x40):
            row = ""
            for col in range(16):
                b = self.ddram[base + (col + self.shift) % 40]
                row += chr(b) if 0x20 <= b < 0x7F else "·"
            lines.append(row)
        return lines


# ---------------------------------------------------------------------------
# Decodificação
# ---------------------------------------------------------------------------

def decode(sig, freq, pre):
    e = sig["E"]
    n = len(e)
    us = 1e6 / freq
    data_bits = [sig.get(f"D{i}") for i in range(8)]

    def byte_at(i, bits):
        v = 0
        for k, ch in bits:
            if ch is not None and ch[i]:
                v |= 1 << k
        return v

    events = []
    falls = []
    rise = None
    widths = []
    for i in range(1, n):
        if e[i] and not e[i - 1]:
            rise = i
        elif e[i - 1] and not e[i]:
            j = i - 1                   # última amostra com E alto: dados estáveis
            if rise is not None:
                widths.append(i - rise)
            rs = sig["RS"][j]
            rw = sig["RW"][j] if "RW" in sig else 0
            full = byte_at(j, list(enumerate(data_bits)))
            nib = byte_at(j, [(k - 4, data_bits[k]) for k in range(4, 8)])
            events.append(((i - pre) * us, rs, rw, full, nib))
            falls.append(i)

    # Repouso: como cada fio fica quando o controlador NÃO está escrevendo.
    # Olhamos o meio de cada intervalo longo (> 200 µs) sem pulsos no E,
    # inclusive antes do primeiro pulso e depois do último.
    idle = []
    min_gap = int(200 / us)
    bounds = [0] + falls + [n - 1]
    for a, b in zip(bounds, bounds[1:]):
        if b - a > min_gap:
            m = (a + b) // 2
            idle.append((e[m], sig["RS"][m], sig["RW"][m] if "RW" in sig else 0,
                         byte_at(m, list(enumerate(data_bits)))))
    return events, widths, us, idle


def report_idle(idle):
    if not idle:
        print("Repouso: não houve intervalos longos sem escrita nesta captura.\n")
        return
    print(f"Repouso (nível dos fios entre as escritas, {len(idle)} intervalos):")
    counts = {}
    for state in idle:
        counts[state] = counts.get(state, 0) + 1
    for (e, rs, rw, d), c in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  E={e} RS={rs} RW={rw} dados=0x{d:02X}  ({c}x)")
    datas = {d for (_, _, _, d) in idle}
    if datas == {0xFF}:
        print("  -> os dados ficam todos em 1 (soltos) no repouso.")
    else:
        print("  -> os dados NÃO voltam a 0xFF no repouso (ficam com algum valor).")
    print()


def run(events, widths, us, show_all, burst=0):
    lcd = Lcd()
    if not events:
        print("Nenhuma borda de descida no E. Confira a ligação do CH1 (E).")
        return

    reads = sum(1 for ev in events if ev[2])
    print(f"Bordas de descida no E: {len(events)}   leituras (RW=1): {reads}")
    if widths:
        print(f"Largura do pulso E: mín {min(widths) * us:.2f} µs, "
              f"máx {max(widths) * us:.2f} µs "
              f"({min(widths)} amostras no mais curto)")
        if min(widths) < 3:
            print("  ATENÇÃO: o pulso mais curto tem menos de 3 amostras. "
                  "Aumente a frequência de captura.")
    print()

    pending_nibble = None
    text_run = ""
    text_start = None
    last_t = None

    def flush_text():
        nonlocal text_run, text_start
        if text_run:
            print(f"{text_start:12.1f} µs  DADOS  \"{text_run}\"")
            text_run, text_start = "", None

    def show_screen():
        l1, l2 = lcd.screen()
        print("              ┌────────────────┐")
        print(f"              │{l1}│")
        print(f"              │{l2}│")
        print("              └────────────────┘")

    current_burst = 0
    for t, rs, rw, full, nib in events:
        if burst:
            b = max(0, int(round(t / us)) // burst)
            if b != current_burst:
                flush_text()
                show_screen()
                print(f"=== trecho {b + 1} (novo trigger; o tempo parado antes dele não foi gravado) ===")
                current_burst, last_t = b, None
        if last_t is not None and t - last_t > BURST_GAP_US:
            flush_text()
            show_screen()
            print(f"--- pausa de {(t - last_t) / 1000:.1f} ms ---")
        last_t = t

        if rw:
            flush_text()
            print(f"{t:12.1f} µs  LEITURA RS={rs} valor=0x{full:02X}"
                  + ("  (busy flag = 1)" if (rs == 0 and full & 0x80) else ""))
            continue

        # Modo 4 bits: cada byte chega em duas metades (primeiro a alta).
        if not lcd.eight_bit:
            if pending_nibble is None:
                pending_nibble = (rs, nib)
                continue
            value = (pending_nibble[1] << 4) | nib
            pending_nibble = None
        else:
            value = full

        if rs:
            if text_start is None:
                text_start = t
            text_run += chr(value) if 0x20 <= value < 0x7F else f"\\x{value:02X}"
            lcd.data(value)
        else:
            flush_text()
            if show_all or value != 0x00:
                print(f"{t:12.1f} µs  CMD 0x{value:02X}  {describe_command(value)}")
            lcd.command(value)

    flush_text()
    print("\nTela final:")
    show_screen()


def main():
    ap = argparse.ArgumentParser(description="Decodifica o barramento HD44780 de uma captura do LogicAnalyzer.")
    ap.add_argument("arquivo", help="captura .lac (recomendado) ou .csv")
    ap.add_argument("--freq", type=int, help="frequência de captura em Hz (obrigatória para .csv)")
    ap.add_argument("--todos", action="store_true", help="mostra também comandos 0x00")
    ap.add_argument("--sem-rw", action="store_true",
                    help="use quando o fio do RW falhou: trata RS=0 com valor < 0x80 como leitura "
                         "(vale fora da inicialização, onde só há 'Set DDRAM' e caracteres)")
    args = ap.parse_args()

    if args.arquivo.lower().endswith(".lac"):
        freq, pre, burst, by_number, by_name = load_lac(args.arquivo)
    else:
        if not args.freq:
            sys.exit("Para .csv informe a frequência, por exemplo: --freq 10000000")
        by_number, by_name = load_csv(args.arquivo)
        freq, pre, burst = args.freq, 0, 0

    sig = pick_signals(by_number, by_name)
    print(f"Arquivo: {args.arquivo}   frequência: {freq / 1e6:g} MHz   "
          f"amostras: {len(sig['E'])}   sinais: {', '.join(s for s in SIGNALS if s in sig)}\n")

    # Um fio que não muda nunca, enquanto o E pulsa, provavelmente está solto
    # ou no pino errado (texto de verdade faz quase todos os bits mudarem).
    stuck = [f"{s}={sig[s][0]}" for s in SIGNALS
             if s != "E" and s in sig and len(set(sig[s])) == 1]
    if stuck and len(set(sig["E"])) > 1:
        print("ATENÇÃO: estes fios ficaram parados durante toda a captura: " + ", ".join(stuck))
        print("  Pode ser normal para um ou dois, mas vários parados indicam fio solto ou fora do lugar.\n")
    events, widths, us, idle = decode(sig, freq, pre)
    report_idle(idle)
    if args.sem_rw:
        events = [(t, rs, 1 if (rs == 0 and full < 0x80) else 0, full, nib)
                  for t, rs, rw, full, nib in events]
    run(events, widths, us, args.todos, burst)


if __name__ == "__main__":
    main()
