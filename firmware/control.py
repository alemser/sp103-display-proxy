"""Ajustes diretos do amp: um pedido só, e os cliques e códigos ficam por conta do Pico.

    POST /control?target=volume&dir=up       volume, bass, treble ou balance; dir = up ou down
    POST /control?target=loudness&on=1       loudness ou speakers; on = 1 ou 0

O caminho no amp (docs/api-estado.md):
- bass e treble têm tecla própria no IR; balance, loudness e speakers só pelo botão Function
  (panel.py), que anda pelo menu: Bass, Treble, Balance, Loudness, Speakers, tela normal;
- dentro de um menu, volume + e − ajustam esse menu. Fora dele, ajustam o volume;
- o primeiro toque no volume só abre a tela, então cada ajuste confere o valor e repete uma vez;
- um clique no Function às vezes também escolhe PHONO: _goto() percebe e volta à entrada anterior.

Roda igual no MicroPython (Pico) e no Python do computador (tools/test_control.py).
"""

import asyncio

MENUS = ("bass", "treble", "balance", "loudness", "speakers")
STEPPED = ("volume", "bass", "treble", "balance")
SWITCHES = ("loudness", "speakers")
KEYS = {"up": "volume_up", "down": "volume_down"}
POLL_MS = 20
SCREEN_MS = 900                 # o amp redesenha a tela bem antes disso
SETTLE_MS = 300                 # o mesmo do perfil do groove-rig
MENU_END_MS = 7500              # um menu fecha sozinho em cerca de 6 s
MAX_PRESSES = 12                # duas voltas no menu


async def _until(ready, ms):
    for _ in range(ms // POLL_MS):
        if ready():
            return True
        await asyncio.sleep_ms(POLL_MS)
    return ready()


class Control:
    def __init__(self, state, remote, panel):
        self.state = state
        self.remote = remote
        self.panel = panel
        self.busy = False

    def _value(self, target):
        st = self.state
        if target == "volume":
            return st.volume_db
        if target == "bass":
            return st.bass_db
        if target == "treble":
            return st.treble_db
        if target == "balance":
            return st.balance
        return st.loudness if target == "loudness" else st.speakers

    async def _ir(self, command):
        await _until(lambda: not self.remote.sending(), SCREEN_MS)
        self.remote.send(command)

    async def _goto(self, target):
        """Clica no Function até abrir o menu. Se o amp pular de entrada, devolve a anterior."""
        st = self.state
        wanted = st.input_id
        for _ in range(MAX_PRESSES):
            if st.screen == target:
                await asyncio.sleep_ms(SETTLE_MS)
                return
            before = st.screen
            self.panel.press()
            await _until(lambda: st.screen != before or st.input_id != wanted, SCREEN_MS)
            if wanted and st.input_id != wanted:
                await self._ir("select_" + wanted)
                await _until(lambda: st.input_id == wanted, SCREEN_MS)
        raise ValueError("The amp didn't open " + target)

    async def _open(self, target):
        st = self.state
        if target == "volume":
            if not await _until(lambda: st.screen not in MENUS, MENU_END_MS):
                raise ValueError("The amp is still in a menu")
        elif target == "balance":
            await self._goto(target)
        elif st.screen != target:
            await self._ir(target)
            await _until(lambda: st.screen == target, SCREEN_MS)
            await asyncio.sleep_ms(SETTLE_MS)

    async def adjust(self, target, direction):
        await self._open(target)
        old = self._value(target)
        for _ in range(2):
            await self._ir(KEYS[direction])
            if await _until(lambda: self._value(target) != old, SCREEN_MS):
                return

    async def switch(self, target, on):
        await self._goto(target)
        if self._value(target) != on:
            await self._ir(KEYS["up" if on else "down"])
            if not await _until(lambda: self._value(target) == on, SCREEN_MS):
                raise ValueError("The amp didn't change " + target)

    async def run(self, query):
        """Faz o pedido. Levanta ValueError, com o texto para mostrar, se não der."""
        target = query.get("target")
        if self.state.power != "on":
            raise ValueError("The amp isn't on")
        if self.busy:
            raise ValueError("Still working on the last change")
        if target in STEPPED and query.get("dir") in KEYS:
            work = self.adjust(target, query["dir"])
        elif target in SWITCHES and query.get("on") in ("0", "1"):
            work = self.switch(target, query["on"] == "1")
        else:
            raise ValueError("Unknown control")
        self.busy = True
        try:
            await work
        finally:
            self.busy = False

    async def handle(self, req, writer):
        """Rota /control (ver web.Publisher)."""
        from web import reply, reply_json
        if req.path != "/control" or req.method != "POST":
            return await reply(writer, "404 Not Found", "text/plain", b"not found\n")
        try:
            await self.run(req.query)
        except ValueError as e:
            return await reply_json(writer, {"error": str(e)}, "400 Bad Request")
        await reply_json(writer, self.state.to_dict())
