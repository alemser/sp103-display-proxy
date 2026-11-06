"""Wi-Fi e servidor HTTP do Pico: publica o estado do amp na rede.

    GET /state    o estado em JSON
    GET /events   Server-Sent Events: um "data: {json}" a cada mudança
    GET /names    os textos personalizados (nomes das entradas e telas de inicialização)
    PUT /names    troca os textos: {"inputs": {"TUNER": "Rega Planar 2"}, "boot": [...], "about": [...],
                  "vu": {"on": true, "layout": "bars", "relay": "192.168.1.50"},
                   "info": {"on": true, "mode": "temp", ...}}      (telas de informação)
                  (texto vazio = original; ver names.py)
    outras        rotas extras, por prefixo: routes={"/update": ota.handle, "/bus": log.handle, "/device": device.handle}

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
from listeners import make_room

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
                    print("Wi-Fi ok: http://%s/device  (or http://%s.local/device)" % (ip, HOSTNAME))
                    result = (True, ip)
                else:
                    print("Wi-Fi attempt %d failed (status %d)" % (tries, wlan.status()))
                    result = (False, "status %d" % wlan.status())
            elif not reported:
                # Já conectado (programa reiniciado pelo mpremote, sem reset do chip de Wi-Fi).
                ip = wlan.ifconfig()[0]
                print("Wi-Fi ok: http://%s/device  (or http://%s.local/device)" % (ip, HOSTNAME))
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


CHUNK = 1024                    # o corpo vai em pedaços: o Wi-Fi do Pico tem pouca memória


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
    # no-store: tudo aqui muda com o estado e com as atualizações por OTA.
    writer.write(("HTTP/1.1 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: no-store\r\n"
                  "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n"
                  % (status, ctype, len(body))).encode())
    await writer.drain()
    # Em pedaços: uma resposta grande de uma vez aperta a memória do Wi-Fi (issue #2).
    for i in range(0, len(body), CHUNK):
        writer.write(body[i:i + CHUNK])
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
        self.listeners = []             # conexões abertas em /events: (ip, writer), ver listeners.py
        self.served = 0                 # pedidos respondidos desde que o Pico ligou

    def _json(self):
        return json.dumps(self.state.to_dict())

    def changed(self):
        """Avisa todos os ouvintes de /events (chamar depois de cada mudança)."""
        msg = ("data: " + self._json() + "\n\n").encode()
        for _, w in self.listeners:
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
        try:
            ip = writer.get_extra_info("peername")[0]
        except Exception:
            ip = None
        make_room(self.listeners, ip)
        writer.write(("data: " + self._json() + "\n\n").encode())   # estado atual logo de cara
        entry = (ip, writer)
        self.listeners.append(entry)
        try:
            while entry in self.listeners:      # fora da lista = outra conexão tomou o lugar
                await writer.drain()    # envia o que changed() escreveu; falha se a conexão caiu
                await asyncio.sleep(1)
                if entry in self.listeners:
                    writer.write(b": ping\n\n")   # comentário SSE: mantém a conexão viva
        except Exception:
            pass
        finally:
            if entry in self.listeners:
                self.listeners.remove(entry)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
