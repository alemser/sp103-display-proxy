"""Estatísticas do barramento do LCD e registro das últimas palavras lidas, com horário.

    GET  /bus          página com as estatísticas (atualiza sozinha) e o botão de download
    GET  /bus.json     as estatísticas em JSON
    GET  /bus.csv      as últimas palavras, da mais antiga para a mais nova
                       (?tz=<minutos>: fuso horário; a página manda o do navegador)
    POST /bus/clear    zera o registro e as estatísticas (para começar um teste limpo)

Colunas do CSV: time (horário, se o Pico já acertou o relógio pela internet), ms (relógio
interno do Pico, em ms), rs, rw, byte (hex), meaning (ver hd44780.describe). O CSV abre no
Numbers/Excel e no tools/ler_bus.py, que remonta as telas.

O horário de cada palavra é o da LEITURA pelo Python, que pega as palavras em lotes (a
cada ~1 ms, ou mais quando o Wi-Fi está ocupado): palavras do mesmo lote têm o mesmo
horário, mas a ordem é sempre a certa. Para tempos finos, use o analisador lógico.

Roda igual no MicroPython (Pico) e no Python do computador (tools/test_buslog.py).
"""

import gc
import time
from array import array

from amp_state import lcd_text
from hd44780 import RS, RW, DATA_SHIFT, describe

try:
    from time import ticks_diff
except ImportError:             # no computador o relógio não dá a volta
    def ticks_diff(a, b):
        return a - b

SIZE = 8192                     # palavras guardadas (umas 50 telas; 48 KB de RAM: o escrita.py também precisa)
WARN_BATCH = 3000               # o sniffer guarda 4096: um lote perto disso pode ter perdido palavras


class BusLog:
    def __init__(self, bus, size=SIZE):
        self.bus = bus                          # o hd44780.Bus da escuta (contagens)
        self.size = size
        self.words = array("H", bytes(2 * size))
        self.ticks = array("I", bytes(4 * size))
        self.clock = None                       # (segundos desde 1970, ticks_ms) do acerto pela internet
        self.clear(None)

    def clear(self, now_ms):
        self.n = 0                              # palavras guardadas desde o início (dá a volta no buffer)
        self.since = now_ms
        self.screens = 0
        self.unknown = 0                        # telas que o leitor (amp_state) não reconheceu
        self.last_screen = None
        self.max_gap = 0                        # maior pausa entre duas leituras do sniffer (ms)
        self.max_batch = 0                      # mais palavras numa leitura só
        self.last_poll = None
        self.base = (self.bus.writes, self.bus.reads, self.bus.clears)

    def poll(self, now_ms, count):
        """Chamar a cada leitura do sniffer, com o número de palavras lidas."""
        if self.last_poll is not None:
            self.max_gap = max(self.max_gap, ticks_diff(now_ms, self.last_poll))
        self.last_poll = now_ms
        self.max_batch = max(self.max_batch, count)

    def add(self, now_ms, word):
        i = self.n % self.size
        self.words[i] = word
        self.ticks[i] = now_ms
        self.n += 1

    def screen(self, now_ms, known):
        self.screens += 1
        self.unknown += not known
        self.last_screen = now_ms

    def set_clock(self, epoch_s, now_ms):
        self.clock = (epoch_s, now_ms)

    def _wall(self, t_ms, tz_min):
        """'2026-10-24 21:15:03.120' (com o fuso tz_min), ou '' sem o relógio acertado."""
        if not self.clock:
            return ""
        ms = self.clock[0] * 1000 + ticks_diff(t_ms, self.clock[1]) + tz_min * 60000
        t = time.gmtime(ms // 1000)
        return "%04d-%02d-%02d %02d:%02d:%02d.%03d" % (t[0], t[1], t[2], t[3], t[4], t[5], ms % 1000)

    def stats(self, now_ms):
        writes, reads, clears = (a - b for a, b in zip(
            (self.bus.writes, self.bus.reads, self.bus.clears), self.base))
        kept = min(self.n, self.size)
        oldest = self.ticks[(self.n - kept) % self.size] if kept else None
        return {
            "since_s": ticks_diff(now_ms, self.since) // 1000 if self.since is not None else None,
            "words": self.n, "writes": writes, "reads": reads, "power_ons": clears,
            "screens": self.screens, "unknown_screens": self.unknown,
            "last_screen_s": ticks_diff(now_ms, self.last_screen) // 1000 if self.last_screen else None,
            "max_gap_ms": self.max_gap, "max_batch": self.max_batch,
            "maybe_lost": self.max_batch >= WARN_BATCH,
            "log_words": kept, "log_size": self.size,
            "log_span_s": ticks_diff(now_ms, oldest) // 1000 if kept else 0,
            "clock": self._wall(now_ms, 0) or None,
            "lcd": [lcd_text(line) for line in self.bus.lcd.lines()],
        }

    def csv(self, tz_min=0, chunk=100):
        """O registro em CSV, em pedaços de texto (gerador). Vai só até a última palavra do
        início do download. Sem cópia (não cabe na memória): as palavras que chegam entre um
        pedaço e outro vão para o fim do buffer; se chegarem tantas que sobrescrevam as que
        ainda não saíram, essas são puladas."""
        size, end = self.size, self.n
        k = max(0, end - size)
        yield "time,ms,rs,rw,byte,meaning\n"
        while k < end:
            k = max(k, self.n - size)
            stop = min(k + chunk, end)
            lines = []
            for j in range(k, stop):
                w, t = self.words[j % size], self.ticks[j % size]
                lines.append('%s,%d,%d,%d,%02X,"%s"\n' % (
                    self._wall(t, tz_min), t, (w & RS) > 0, (w & RW) > 0, (w >> DATA_SHIFT) & 0xFF,
                    describe(w).replace('"', '""')))
            k = stop
            if lines:
                yield "".join(lines)
            gc.collect()                        # pedaços pequenos e memória limpa: o Pico tem pouca

    async def handle(self, req, writer):
        """Rota /bus (ver web.Publisher)."""
        from web import reply, reply_json
        now = time.ticks_ms()
        if req.path == "/bus":
            await reply(writer, "200 OK", "text/html; charset=utf-8", PAGE.encode())
        elif req.path == "/bus.json":
            await reply_json(writer, self.stats(now))
        elif req.path == "/bus/clear" and req.method == "POST":
            self.clear(now)
            await reply_json(writer, self.stats(now))
        elif req.path == "/bus.csv":
            try:
                tz = int(req.query.get("tz", 0))
            except ValueError:
                tz = 0
            name = "sp103-bus.csv"
            if self.clock:
                name = "sp103-bus-%s.csv" % self._wall(now, tz)[:16].replace(" ", "-").replace(":", "")
            # Sem Content-Length: o tamanho só se sabe no fim; a conexão fecha ao terminar.
            writer.write(("HTTP/1.1 200 OK\r\nContent-Type: text/csv; charset=utf-8\r\n"
                          "Content-Disposition: attachment; filename=\"%s\"\r\n"
                          "Connection: close\r\n\r\n" % name).encode())
            for part in self.csv(tz):
                writer.write(part.encode())
                await writer.drain()            # aqui a escuta continua rodando entre os pedaços
        else:
            await reply(writer, "404 Not Found", "text/plain", b"not found\n")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SP103 bus</title>
<style>
:root{--bg:#f4f4f2;--card:#fff;--fg:#1b1b1b;--dim:#777;--lcd:#2c4fd6;--lcdfg:#eef;--warn:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1f1f1f;--fg:#eee;--dim:#999;--warn:#f2b8b5}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:16px system-ui,sans-serif}
.lcd{background:var(--lcd);color:var(--lcdfg);font:22px/1.3 ui-monospace,Menlo,monospace;
 padding:12px 14px;border-radius:8px;white-space:pre;max-width:max-content;margin:0 auto 16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;max-width:640px;margin:auto}
.c{background:var(--card);border-radius:8px;padding:10px 12px}
.k{color:var(--dim);font-size:13px}.v{font-size:22px;font-weight:600;margin-top:2px}
.w .v{color:var(--warn)}
.bar{max-width:640px;margin:16px auto;display:flex;gap:10px;flex-wrap:wrap}
.bar a,.bar button{padding:8px 12px;font-size:16px;border-radius:6px;border:1px solid var(--dim);
 background:var(--card);color:var(--fg);text-decoration:none;cursor:pointer}
.st{text-align:center;color:var(--dim);font-size:13px;margin-top:14px}
</style></head><body>
<div class="lcd" id="lcd">                \\n                </div>
<div class="grid" id="g"></div>
<div class="bar"><a id="dl" href="/bus.csv">Download log (CSV)</a>
<button id="clr">Clear log</button><a href="/">Amp state</a></div>
<div class="st" id="st">loading…</div>
<script>
const tz=-new Date().getTimezoneOffset();
document.getElementById("dl").href="/bus.csv?tz="+tz;
const ago=s=>s===null?"–":s<60?s+" s ago":s<3600?Math.floor(s/60)+" min ago":Math.floor(s/3600)+" h ago";
const dur=s=>s<60?s+" s":s<3600?Math.floor(s/60)+" min":(s/3600).toFixed(1)+" h";
const F=[["words","Words read"],["writes","Writes"],["reads","Busy reads"],["screens","Screens"],
["unknown_screens","Unknown screens",d=>d.unknown_screens>0],["power_ons","Power-ons (clear)"],
["last_screen_s","Last screen",null,ago],["max_gap_ms","Longest pause (ms)"],
["max_batch","Biggest batch",d=>d.maybe_lost],["log_words","Words in log",null,(v,d)=>v+" / "+d.log_size],
["log_span_s","Log covers",null,dur],["since_s","Counting for",null,dur]];
function show(d){document.getElementById("lcd").textContent=d.lcd.join("\\n");
 document.getElementById("g").innerHTML=F.map(([k,n,w,f])=>'<div class="c'+(w&&w(d)?' w':'')+
 '"><div class="k">'+n+'</div><div class="v">'+(f?f(d[k],d):d[k])+'</div></div>').join("");
 document.getElementById("st").textContent=(d.maybe_lost?"Some words may have been lost. ":"")+
 (d.clock?"Pico clock (UTC) "+d.clock:"Pico clock not set yet: the CSV has no time column")}
function load(){fetch("/bus.json").then(r=>r.json()).then(show).catch(()=>
 document.getElementById("st").textContent="disconnected, retrying…")}
document.getElementById("clr").onclick=()=>{if(confirm("Clear the log and the counters?"))
 fetch("/bus/clear",{method:"POST"}).then(r=>r.json()).then(show)};
load();setInterval(load,2000);
</script></body></html>
"""
