"""Wi-Fi e servidor HTTP do Pico: publica o estado do amp na rede.

    GET /         página para ver o estado no celular (atualiza sozinha)
    GET /state    o estado em JSON
    GET /events   Server-Sent Events: um "data: {json}" a cada mudança
    GET /names    os textos personalizados (nomes das entradas e telas de inicialização)
    PUT /names    troca os textos: {"inputs": {"TUNER": "Rega Planar 2"}, "boot": [...], "about": [...],
                  "vu": {"on": true, "auto": true, "floor": -40, "top": 0, "layout": "bars",
                         "relay": "192.168.178.105"},
                   "info": {"on": true, "mode": "temp", ...}}      (telas de informação)
                  (texto vazio = original; ver names.py)
    outras        rotas extras, por prefixo: routes={"/update": ota.handle, "/bus": log.handle}

Uso (com asyncio):
    asyncio.create_task(wifi_task(aviso))   # nunca trava nem levanta erro
    pub = Publisher(state, get_names=g, set_names=s)   # s(cfg) valida, guarda e aplica; levanta ValueError
    (routes: handler(req, writer) assíncrono; req = Request, ver abaixo; responde com reply())
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


async def wifi_task(on_first_result=None, quick_tries=3, timeout_s=15, retry_s=30):
    """Conecta e mantém o Wi-Fi conectado, em segundo plano. Nunca levanta erro:
    sem Wi-Fi, o resto do programa (o display) segue normal, só sem rede.

    Logo depois de um reset, a primeira tentativa costuma falhar (status -1): o roteador
    ainda "lembra" a conexão que o reset cortou. Por isso as primeiras tentativas são
    rápidas (a cada 2 s); depois, uma a cada retry_s.

    on_first_result(ok, info) é chamado uma vez: quando conecta, ou quando as tentativas
    rápidas acabam sem conectar (info = IP, ou o motivo da falha).
    """
    wlan = None
    tries = 0
    reported = False
    while True:
        result = None
        try:
            if wlan is None:
                network.hostname(HOSTNAME)
                wlan = network.WLAN(network.STA_IF)
                wlan.active(True)
                wlan.config(pm=0xA11140)    # desliga a economia de energia: responde mais rápido
            if not wlan.isconnected():
                if tries:
                    # Só nas tentativas seguintes: com o chip recém-ligado, um disconnect()
                    # antes do connect() faz a primeira tentativa falhar (status -1).
                    wlan.disconnect()
                tries += 1
                wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASSWORD)
                t0 = time.time()
                # status < 0 = falhou de vez (-1 falha, -2 rede não encontrada, -3 senha errada)
                while not wlan.isconnected() and wlan.status() >= 0 and time.time() - t0 < timeout_s:
                    await asyncio.sleep(0.25)
                if wlan.isconnected():
                    ip = wlan.ifconfig()[0]
                    print("Wi-Fi ok. Open http://%s/  (or http://%s.local/)" % (ip, HOSTNAME))
                    result = (True, ip)
                else:
                    print("Wi-Fi attempt %d failed (status %d)" % (tries, wlan.status()))
                    result = (False, "status %d" % wlan.status())
            elif not reported:
                # Já conectado (programa reiniciado pelo mpremote, sem reset do chip de Wi-Fi).
                ip = wlan.ifconfig()[0]
                print("Wi-Fi ok. Open http://%s/  (or http://%s.local/)" % (ip, HOSTNAME))
                result = (True, ip)
        except Exception as e:              # chip de Wi-Fi com problema, senha ausente etc.
            print("Wi-Fi error:", e)
            result = (False, str(e))
        if wlan is not None and wlan.isconnected():
            tries = 0                       # se cair depois, recomeça com tentativas rápidas
        if result and not reported and (result[0] or tries >= quick_tries):
            reported = True
            if on_first_result:
                on_first_result(*result)
        await asyncio.sleep(2 if 0 < tries < quick_tries else retry_s)


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
.amp{grid-column:2;color:var(--dim);font-size:12px;margin-top:-4px}
input,select{font:16px ui-monospace,Menlo,monospace;padding:6px 8px;border-radius:6px;border:1px solid var(--dim);
 background:var(--card);color:var(--fg)}button{grid-column:2;padding:8px;font-size:16px;border-radius:6px}
.chk{display:flex;gap:8px;align-items:center}.chk input{width:18px;height:18px}
#vupv{grid-column:2;width:100%;max-width:420px;border-radius:6px}
</style></head><body>
<div class="lcd" id="lcd">                \n                </div>
<div class="grid" id="g"></div>
<div class="st" id="st">connecting…</div>
<h3>Custom texts</h3>
<form id="nf"></form>
<div class="st" id="nst"></div>
<div class="st"><a href="/bus">bus statistics and log</a></div>
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
function loadNames(){fetch("/names").then(r=>r.json()).then(d=>{const c=d.config;
 const amp=d.amp||{};
 nf.innerHTML='<b>Inputs</b><span></span>'+d.inputs.map(k=>row(k,"i:"+k,k,c.inputs[k])+
 (amp[k]?'<span class="amp">'+amp[k]+'</span>':'')).join("")+
 '<b>Startup</b><span></span>'+["boot","about"].map(s=>[0,1].map(n=>
 row(s+" "+(n+1),s+":"+n,d.defaults[s][n],c[s][n])).join("")).join("")+
 '<b>Display</b><span></span><label for="vuon">VU meter</label><label class="chk"><input type="checkbox" '+
 'id="vuon" name="vu:on"'+(c.vu.on?" checked":"")+'> only while music plays</label>'+
 '<label for="vuau">VU scale</label><label class="chk"><input type="checkbox" id="vuau" name="vu:auto"'+
 (c.vu.auto?" checked":"")+'> automatic (follows the music)</label>'+
 '<label for="vuly">VU layout</label><select id="vuly" name="vu:layout">'+VL.map(([k,n])=>'<option value="'+k+'"'+
 (c.vu.layout==k?" selected":"")+'>'+n+'</option>').join("")+'</select><canvas id="vupv" width="404" height="74" '+
 'aria-label="VU layout preview"></canvas><span class="amp">preview with made-up music, automatic scale</span>'+
 '<label for="vufl">Manual floor (dB)</label><input type="number" id="vufl" name="vu:floor" min="-60" max="-10" '+
 'step="1" value="'+c.vu.floor+'"><label for="vutp">Manual top (dB)</label><input type="number" id="vutp" '+
 'name="vu:top" min="-30" max="0" step="1" value="'+c.vu.top+'"><label for="vuip">VU source (IP)</label><input id="vuip" name="vu:relay" '+
 'value="'+q(c.vu.relay)+'"><span class="amp">'+vuText(d.vu)+'</span>'+infoForm(c.info,d)+'<button>Save</button>';
 VG=d.vu_glyphs||null;ly=c.vu.layout;nf.querySelector("#vuly").onchange=e=>{ly=e.target.value};
 nf.querySelector("#inmo").onchange=imode;imode()})}
// VU layout preview: the same drawing as vu.py, fed with made-up music on the automatic scale
const VL=[["bars","Thin bars"],["deck","Cassette deck"],["scale","Printed scale"],["kx393","Yamaha KX-393"]];
const FT={L:[16,16,16,16,16,16,31],R:[30,17,17,30,20,18,17],"0":[14,17,19,21,25,17,14],"1":[4,12,4,4,4,4,14],
 "2":[14,17,1,2,4,8,31],"3":[31,2,4,2,1,17,14],"4":[2,6,10,18,31,2,2],"6":[6,8,16,30,17,17,14],
 "7":[31,1,2,4,8,8,8],"8":[14,17,17,14,17,17,14]};
const KX=[-30,-25,-20,-17,-14,-12,-10,-8,-6,-4,-2,0,2,4,6,8];
function kxl(m){const z=vtop-10,lv=KX.filter(d=>m.lv>=z+d).length,pk=KX.filter(d=>m.pk>=z+d).length;
 return KX.map((_,i)=>i<lv||(pk>lv&&i==pk-1)||(i==15&&m.c>0))}
const TK=[7,10,12],RU="20      10 6 3 0",DT=1/21.5;
let VG=null,ly="bars",vt=0,vtop=-40,vacc=0,vlast=0;const VM=[{lv:-99,pk:-99,h:0,c:0},{lv:-99,pk:-99,h:0,c:0}];
const cl=(v,a,b)=>Math.max(a,Math.min(b,v)),vpx=(d,n)=>cl(Math.round((d-vtop+20)/20*n),0,n);
function vsrc(t,ch){const k=Math.exp(-((t*2)%1)*7),p=.5+.5*Math.sin(t*.35+ch),n=(Math.sin(t*13.1+ch*2.3)+Math.sin(t*29.7+ch))/2;
 return Math.sin(t*.21)>.995?0:-24+k*14+p*6+n*2.5-ch*1.5}
function vstep(){vt+=DT;const d=[vsrc(vt,0),vsrc(vt,1)],w=Math.max(d[0],d[1])+5;
 vtop=cl(w>vtop?w:Math.max(w,vtop-DT),-40,0);
 VM.forEach((m,i)=>{m.lv=d[i]>m.lv?d[i]:Math.max(d[i],m.lv-40*DT);if(m.lv>=m.pk){m.pk=m.lv;m.h=1}
  else if((m.h-=DT)<=0)m.pk=Math.max(m.lv,m.pk-20*DT);m.c=d[i]>-1?1:Math.max(0,m.c-DT)})}
function bars(m){const lv=vpx(m.lv,75),pk=vpx(m.pk,75),pc=pk>lv?Math.floor((pk-1)/5):-1,o=[];
 for(let c=0;c<15;c++){const f=lv-5*c;o.push(c==14&&m.c?7:f>=5?4:f>0?f-1:c==pc?5:TK.includes(c)?6:" ")}return o}
function deck(m){const lv=vpx(m.lv,30);let pk=vpx(m.pk,30);if(pk<=lv)pk=0;const o=[];
 for(let c=0;c<15;c++){const x=c==14&&m.c,a=lv>=2*c+1||pk==2*c+1||x,b=lv>=2*c+2||pk==2*c+2||x;
  o.push(a||b?(c>=12?3:0)+(a&&b?1:a?0:2):TK.includes(c)?6:" ")}return o}
function half(lv,pk,c){const s=cl(lv-2*c,0,2);return s||pk<=lv||Math.floor((pk-1)/2)!=c?s:pk%2?1:2}
function vrows(){if(ly=="scale"){const l=vpx(VM[0].lv,32),r=vpx(VM[1].lv,32),pl=vpx(VM[0].pk,32),pr=vpx(VM[1].pk,32),b=[];
  for(let c=0;c<16;c++){const x=half(l,pl,c),y=half(r,pr,c);b.push(x||y?3*x+y-1:" ")}
  const u=Array.from(RU);if(VM[0].c||VM[1].c)u[15]=255;return[b,u]}
 if(ly=="kx393"){const l=kxl(VM[0]),r=kxl(VM[1]);
  return[KX.map((d,i)=>l[i]||r[i]?(d>0?3:0)+(l[i]&&r[i]?2:r[i]?1:0):" "),Array.from("30 17 10 4 0 4 8")]}
 const f=ly=="deck"?deck:bars;return[["L",...f(VM[0])],["R",...f(VM[1])]]}
function vdraw(ts){requestAnimationFrame(vdraw);const cv=document.getElementById("vupv");if(!cv||!VG)return;
 vacc+=Math.min(.1,(ts-vlast)/1000);vlast=ts;while(vacc>=DT){vacc-=DT;vstep()}
 const g=cv.getContext("2d"),cs=getComputedStyle(document.body),u=4;
 g.fillStyle=cs.getPropertyValue("--lcd");g.fillRect(0,0,cv.width,cv.height);
 vrows().forEach((row,r)=>row.forEach((ch,c)=>{const bm=ch===255?[31,31,31,31,31,31,31,31]:
  typeof ch=="number"?VG[ly].slice(8*ch,8*ch+8):FT[ch]||[];
  for(let y=0;y<8;y++)for(let x=0;x<5;x++){g.fillStyle=(bm[y]||0)&(16>>x)?"#eef":"rgba(238,238,255,.12)";
   g.fillRect(6+(c*6+x)*u,5+(r*9+y)*u,u-.6,u-.6)}}))}
requestAnimationFrame(vdraw);
function vuText(v){if(v&&v.error)return"VU turned off after an error: "+v.error;if(!v||!v.on)return"VU off";if(v.showing)return"VU on the display now, scale "+v.floor+" to "+v.top+" dB";
 if(v.last_frame_ms===null||v.last_frame_ms>1000)return"no data from the VU source";
 return v.music?"amp screen for a moment":"waiting for music"}
// Info screens (screens.py): what is playing, from the source in docs/api-telas.md
const IK=[["track","Artist and title"],["pos","Track and position"],["side","Time left on the side"],["stylus","Stylus hours"]];
const chk=(id,name,on,text)=>'<label class="chk"><input type="checkbox" id="'+id+'" name="'+name+'"'+(on?" checked":"")+'> '+text+'</label>';
function infoForm(c,d){return'<b>Info screens</b><span></span><label for="inon">Info screens</label>'+
 chk("inon","info:on",c.on,"show what is playing")+
 '<label for="inmo">While playing</label><select id="inmo" name="info:mode"><option value="temp"'+(c.mode=="temp"?" selected":"")+
 '>Temporary: when the track changes</option><option value="fixed"'+(c.mode=="fixed"?" selected":"")+'>Fixed: one screen all the time</option></select>'+
 '<label class="mt" for="inse">Seconds per screen</label><input class="mt" type="number" id="inse" name="info:secs" min="3" max="60" step="1" value="'+c.secs+'">'+
 '<label class="mt">Screens</label><span class="mt">'+IK.map(([k,n])=>chk("ins"+k,"info:show:"+k,c.show.includes(k),
  n+(k=="stylus"?" (when a side starts)":""))).join("")+'</span>'+
 '<span class="amp mt">each screen in turn when the track changes; then the VU, if it is on</span>'+
 '<label class="mf" for="infx">Screen</label><select class="mf" id="infx" name="info:fixed">'+IK.map(([k,n])=>'<option value="'+k+'"'+
  (c.fixed==k?" selected":"")+'>'+n+'</option>').join("")+'</select><span class="amp mf">all the time while playing; the VU is not shown</span>'+
 '<label>Stylus screen on</label><span>'+d.inputs.map(k=>chk("intt"+k.replace("/",""),"info:turntable:"+k,
  c.turntable.includes(k),k+(d.config.inputs[k]?" ("+d.config.inputs[k]+")":""))).join("")+'</span>'+
 '<span class="amp">the inputs with a turntable</span>'+
 '<label for="inal">End of side</label>'+chk("inal","info:alert",c.alert,"last minute and &quot;Flip the record&quot;")+
 '<label for="incl">Standby</label>'+chk("incl","info:clock",c.clock,"show the clock")+
 '<label for="insc">Long names</label>'+chk("insc","info:scroll",c.scroll,"scroll")+
 '<label for="intz">UTC offset (h)</label><input type="number" id="intz" name="info:utc_offset" min="-12" max="14" step="0.25" value="'+c.utc_offset+'">'+
 '<label for="inds">Summer time</label>'+chk("inds","info:eu_dst",c.eu_dst,"European rule (+1 h)")+
 '<label for="insr">Info source (IP)</label><input id="insr" name="info:source" placeholder="same as the VU source" value="'+q(c.source)+'">'+
 '<span class="amp">'+infoText(d.info,d.screens)+'</span>'}
// Only the fields of the chosen mode: temporary (.mt) or fixed (.mf)
function imode(){const f=nf.querySelector("#inmo").value=="fixed";
 nf.querySelectorAll(".mt").forEach(e=>e.style.display=f?"none":"");nf.querySelectorAll(".mf").forEach(e=>e.style.display=f?"":"none")}
function infoText(i,s){if(s&&s.error)return"Info screens turned off after an error: "+s.error;if(!i||!i.on)return"Info screens off";
 if(i.last_packet_ms===null||i.last_packet_ms>15000)return"no data from the info source";
 const now=i.playing&&i.title?"playing: "+(i.artist?i.artist+" – ":"")+i.title:i.side_end?"side ended":"nothing playing";
 return now+(s&&s.showing?" - on the display: "+s.showing:"")}
loadNames();
nf.onsubmit=e=>{e.preventDefault();const b={inputs:{},boot:["",""],about:["",""],vu:{},info:{show:[],turntable:[]}};
 for(const i of nf.querySelectorAll("input,select")){const [g,k,x]=i.name.split(":");
  if(g=="i")b.inputs[k]=i.value;else if(g=="vu")b.vu[k]=k=="on"||k=="auto"?i.checked:k=="floor"||k=="top"?Number(i.value):i.value;
  else if(g=="info"){if(k=="show"||k=="turntable"){if(i.checked)b.info[k].push(x)}
   else b.info[k]=["on","alert","clock","scroll","eu_dst"].includes(k)?i.checked:k=="secs"||k=="utc_offset"?Number(i.value):i.value}
  else b[g][+k]=i.value}
 fetch("/names",{method:"PUT",body:JSON.stringify(b)}).then(r=>r.json()).then(d=>{
 nst.textContent=d.error?"Error: "+d.error:"Saved.";if(!d.error)loadNames()})};
</script></body></html>
"""


class Request:
    """Um pedido HTTP já lido até os cabeçalhos. O corpo fica em reader (length bytes)."""

    def __init__(self, method, path, headers, reader):
        self.method = method
        self.path, _, query = path.partition("?")
        self.query = {}                 # "?tz=120&x=1" -> {"tz": "120", "x": "1"}
        for p in query.split("&"):
            key, _, value = p.partition("=")
            self.query[key] = value
        self.headers = headers          # nomes em minúsculas
        self.reader = reader
        self.length = int(headers.get("content-length", 0))


async def reply(writer, status, ctype, body):
    writer.write(("HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
                  "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n"
                  % (status, ctype, len(body))).encode())
    writer.write(body)
    await writer.drain()


async def reply_json(writer, obj, status="200 OK"):
    await reply(writer, status, "application/json", json.dumps(obj).encode())


class Publisher:
    def __init__(self, state, get_names=None, set_names=None, port=80, routes=None, names_extra=None):
        self.state = state
        self.get_names = get_names
        self.set_names = set_names
        self.names_extra = names_extra  # campos a mais no GET /names (ex.: as contagens do proxy)
        self.port = port
        self.routes = routes or {}
        self.listeners = []             # conexões abertas em /events
        self.served = 0                 # pedidos respondidos desde que o Pico ligou

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
            headers = {}
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                name, _, value = line.decode().partition(":")
                headers[name.strip().lower()] = value.strip()
            parts = request.split()
            req = Request(parts[0].decode() if parts else "GET",
                          parts[1].decode() if len(parts) > 1 else "/", headers, reader)
            path = req.path
            route = path.split("/")[1].split(".")[0]    # "/bus.csv" -> "bus"; "/update/x" -> "update"
            self.served += 1

            if path == "/names":
                await self._names(writer, req.method,
                                  await reader.readexactly(req.length) if req.length else b"")
            elif path == "/state":
                await reply(writer, "200 OK", "application/json", self._json().encode())
            elif path == "/events":
                await self._events(writer)
                return
            elif path == "/":
                await reply(writer, "200 OK", "text/html; charset=utf-8", PAGE.encode())
            elif "/" + route in self.routes:
                await self.routes["/" + route](req, writer)
            else:
                await reply(writer, "404 Not Found", "text/plain", b"not found\n")
        except Exception as e:
            print("http:", e)
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass

    async def _names(self, writer, method, body):
        import names
        status, answer = "200 OK", None
        if method == "PUT" and self.set_names:
            try:
                self.set_names(json.loads(body))
            except ValueError as e:     # JSON inválido ou texto recusado por names.validate
                status, answer = "400 Bad Request", {"error": str(e)}
        if answer is None:
            answer = {"config": self.get_names(), "inputs": names.INPUTS,
                      "defaults": {"boot": ["ACOUSTIC", "SOLUTIONS"],
                                   "about": ["Amplifier SP103", "SW version 1.0"]}}
            if self.names_extra:
                answer.update(self.names_extra())
        await reply_json(writer, answer, status)

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
