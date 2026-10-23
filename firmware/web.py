"""Wi-Fi e servidor HTTP do Pico: publica o estado do amp na rede.

    GET /         página para ver o estado no celular (atualiza sozinha)
    GET /state    o estado em JSON
    GET /events   Server-Sent Events: um "data: {json}" a cada mudança
    GET /names    os textos personalizados (nomes das entradas e telas de inicialização)
    PUT /names    troca os textos: {"inputs": {"TUNER": "Rega Planar 2"}, "boot": [...], "about": [...]}
                  (texto vazio = original; ver names.py)

Uso (com asyncio):
    wlan = connect_wifi()
    pub = Publisher(state, get_names=g, set_names=s)   # s(cfg) valida, guarda e aplica; levanta ValueError
    asyncio.create_task(pub.serve())
    ...
    pub.changed()      # chame depois de cada state.update() que devolveu True
"""

import json
import time
import network
import asyncio

import secrets

HOSTNAME = "sp103"


def connect_wifi(attempts=4, timeout_s=15, on_attempt=None):
    """Conecta na rede de secrets.py, tentando algumas vezes. Devolve o IP, ou levanta erro.

    Logo depois de um reset, o chip de Wi-Fi às vezes não conecta na primeira tentativa:
    por isso desligamos e tentamos de novo antes de desistir.
    """
    network.hostname(HOSTNAME)
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(pm=0xA11140)            # desliga a economia de energia: responde mais rápido
    for attempt in range(1, attempts + 1):
        if wlan.isconnected():
            break
        if on_attempt:
            on_attempt(attempt)
        wlan.disconnect()
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
        t0 = time.time()
        while not wlan.isconnected() and time.time() - t0 < timeout_s:
            time.sleep(0.5)
        if not wlan.isconnected():
            print("Wi-Fi: attempt %d failed (status %d)" % (attempt, wlan.status()))
    if not wlan.isconnected():
        raise RuntimeError("Wi-Fi failed (status %d)" % wlan.status())
    return wlan.ifconfig()[0]


async def keep_wifi(every_s=30):
    """Se o Wi-Fi cair (roteador reiniciou, por exemplo), conecta de novo."""
    wlan = network.WLAN(network.STA_IF)
    while True:
        await asyncio.sleep(every_s)
        if not wlan.isconnected():
            print("Wi-Fi lost, reconnecting")
            try:
                wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
            except OSError as e:
                print("Wi-Fi:", e)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SP103</title>
<style>
:root{--bg:#f4f4f2;--card:#fff;--fg:#1b1b1b;--dim:#777;--lcd:#2c4fd6;--lcdfg:#eef}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--card:#1f1f1f;--fg:#eee;--dim:#999}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:16px system-ui,sans-serif}
.lcd{background:var(--lcd);color:var(--lcdfg);font:22px/1.3 ui-monospace,Menlo,monospace;
 padding:12px 14px;border-radius:8px;white-space:pre;max-width:max-content;margin:0 auto 16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;max-width:640px;margin:auto}
.c{background:var(--card);border-radius:8px;padding:10px 12px}
.k{color:var(--dim);font-size:13px}.v{font-size:22px;font-weight:600;margin-top:2px}
.st{text-align:center;color:var(--dim);font-size:13px;margin-top:14px}
h3,form{max-width:640px;margin:22px auto 8px}form{display:grid;grid-template-columns:auto 1fr;gap:8px 10px;align-items:center}
input{font:16px ui-monospace,Menlo,monospace;padding:6px 8px;border-radius:6px;border:1px solid var(--dim);
 background:var(--card);color:var(--fg)}button{grid-column:2;padding:8px;font-size:16px;border-radius:6px}
</style></head><body>
<div class="lcd" id="lcd">                \n                </div>
<div class="grid" id="g"></div>
<div class="st" id="st">connecting…</div>
<h3>Custom texts</h3>
<form id="nf"></form>
<div class="st" id="nst"></div>
<script>
const F=[["power","Power"],["volume_db","Volume (dB)"],["input","Input"],["bass_db","Bass (dB)"],
["treble_db","Treble (dB)"],["balance","Balance"],["loudness","Loudness"],["speakers","Speakers"],
["input_name","Name"],["screen","Screen"],["firmware","Firmware"]];
function fmt(k,v){if(v===null||v===undefined)return"?";if(v===true)return"ON";if(v===false)return"OFF";
 if(k=="balance")return v.db==0?"center":v.db.toFixed(2)+" "+(v.side||"");
 if(k=="volume_db")return v.toFixed(2);return v}
function show(s){document.getElementById("lcd").textContent=s.lcd.join("\\n");
 document.getElementById("g").innerHTML=F.map(([k,n])=>'<div class="c"><div class="k">'+n+
 '</div><div class="v">'+fmt(k,s[k])+'</div></div>').join("");
 document.getElementById("st").textContent="updated · version "+s.version}
const es=new EventSource("/events");
es.onmessage=e=>show(JSON.parse(e.data));
es.onerror=()=>document.getElementById("st").textContent="disconnected, retrying…";
const nf=document.getElementById("nf"),nst=document.getElementById("nst");
const q=v=>(v||"").replace(/"/g,"&quot;");
const row=(label,name,ph,v)=>'<label>'+label+'</label><input maxlength="16" name="'+name+'" placeholder="'+
 q(ph)+'" value="'+q(v)+'">';
fetch("/names").then(r=>r.json()).then(d=>{const c=d.config;
 nf.innerHTML='<b>Inputs</b><span></span>'+d.inputs.map(k=>row(k,"i:"+k,k,c.inputs[k])).join("")+
 '<b>Startup</b><span></span>'+["boot","about"].map(s=>[0,1].map(n=>
 row(s+" "+(n+1),s+":"+n,d.defaults[s][n],c[s][n])).join("")).join("")+'<button>Save</button>'});
nf.onsubmit=e=>{e.preventDefault();const b={inputs:{},boot:["",""],about:["",""]};
 for(const i of nf.querySelectorAll("input")){const [g,k]=i.name.split(":");
  if(g=="i")b.inputs[k]=i.value;else b[g][+k]=i.value}
 fetch("/names",{method:"PUT",body:JSON.stringify(b)}).then(r=>r.json()).then(d=>
 nst.textContent=d.error?"Error: "+d.error:"Saved.")};
</script></body></html>
"""


class Publisher:
    def __init__(self, state, get_names=None, set_names=None, port=80):
        self.state = state
        self.get_names = get_names
        self.set_names = set_names
        self.port = port
        self.listeners = []             # conexões abertas em /events

    def _json(self):
        return json.dumps(self.state.to_dict())

    def changed(self):
        """Avisa todos os ouvintes de /events (chamar depois de cada mudança)."""
        msg = ("data: " + self._json() + "\n\n").encode()
        for w in self.listeners:
            try:
                w.write(msg)
            except Exception:
                pass                    # a conexão caiu: o laço dela vai removê-la

    async def serve(self):
        await asyncio.start_server(self._client, "0.0.0.0", self.port)

    async def _client(self, reader, writer):
        try:
            request = await reader.readline()
            length = 0
            while True:                 # cabeçalhos: só interessa o tamanho do corpo
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                if line.lower().startswith(b"content-length:"):
                    length = int(line[15:])
            parts = request.split()
            method = parts[0].decode() if parts else "GET"
            path = parts[1].decode() if len(parts) > 1 else "/"

            if path == "/names":
                await self._names(writer, method, await reader.readexactly(length) if length else b"")
            elif path == "/state":
                body = self._json().encode()
                await self._reply(writer, "200 OK", "application/json", body)
            elif path == "/events":
                await self._events(writer)
                return
            elif path == "/":
                await self._reply(writer, "200 OK", "text/html; charset=utf-8", PAGE.encode())
            else:
                await self._reply(writer, "404 Not Found", "text/plain", b"not found\n")
        except Exception as e:
            print("http:", e)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    async def _names(self, writer, method, body):
        import names
        status, reply = "200 OK", None
        if method == "PUT" and self.set_names:
            try:
                self.set_names(json.loads(body))
            except ValueError as e:     # JSON inválido ou texto recusado por names.validate
                status, reply = "400 Bad Request", {"error": str(e)}
        if reply is None:
            reply = {"config": self.get_names(), "inputs": names.INPUTS,
                     "defaults": {"boot": ["ACOUSTIC", "SOLUTIONS"],
                                  "about": ["Amplifier SP103", "SW version 1.0"]}}
        await self._reply(writer, status, "application/json", json.dumps(reply).encode())

    async def _reply(self, writer, status, ctype, body):
        writer.write(("HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
                      "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n"
                      % (status, ctype, len(body))).encode())
        writer.write(body)
        await writer.drain()

    async def _events(self, writer):
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                     b"Cache-Control: no-cache\r\nAccess-Control-Allow-Origin: *\r\n\r\n")
        writer.write(("data: " + self._json() + "\n\n").encode())   # estado atual logo de cara
        self.listeners.append(writer)
        try:
            while True:
                await writer.drain()    # envia o que changed() escreveu; falha se a conexão caiu
                await asyncio.sleep(1)
                writer.write(b": ping\n\n")   # comentário SSE: mantém a conexão viva
        except Exception:
            pass
        finally:
            self.listeners.remove(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
