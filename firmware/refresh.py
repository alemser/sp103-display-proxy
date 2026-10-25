"""Redesenho fechado sem cortar as trilhas.

O SP103 só dá uma chance de alterar uma tela durante o próprio redraw. Depois de
uma troca de entrada o Pico só então sabe qual entrada veio, portanto pede ao
groove-rig um +1/-1 de volume para provocar um redraw conhecido. A tela final só
é considerada sucesso quando o sniffer a vê; enviar IR nunca é prova de sucesso.

Por segurança, este módulo só é usado com planos de guarda completa. O motor de
escrita continua a ser a última barreira: qualquer tela inesperada o faz soltar o
barramento sem alterar nada.
"""

import asyncio
import time


class GrooveRig:
    """Cliente mínimo da API documentada do groove-rig, sem dependências HTTP."""

    def __init__(self, host, port=7075):
        self.host, self.port = host, port

    async def action(self, name):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            path = "/targets/amplifier/actions/" + name
            request = ("POST %s HTTP/1.1\r\nHost: %s\r\nContent-Length: 0\r\n"
                       "Connection: close\r\n\r\n") % (path, self.host)
            writer.write(request.encode())
            await writer.drain()
            line = await reader.readline()
            if not line.startswith(b"HTTP/1.1 2"):
                raise OSError("groove-rig: " + line.decode().strip())
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


class Refresh:
    """Uma transação por vez: pedido IR -> barra vista -> plano armado -> redraw."""

    def __init__(self, rig=None, delay_ms=180, timeout_ms=9000):
        self.rig = rig
        self.delay_ms = delay_ms
        self.timeout_ms = timeout_ms
        self.input = None
        self.started = None
        self.phase = "off" if rig is None else "idle"
        self.error = None

    def status(self):
        return {"phase": self.phase, "input": self.input, "error": self.error}

    def request(self, input_name, volume_db):
        """Inicia um refresh apenas quando nenhum outro está em curso."""
        if self.rig is None or self.phase != "idle":
            return False
        self.input, self.error = input_name, None
        self.phase = "sending"
        self.started = time.ticks_ms()
        asyncio.create_task(self._nudge(volume_db))
        return True

    async def _nudge(self, volume_db):
        # No limite superior não existe +1; desce e volta. Em qualquer outro
        # ponto sobe e volta. O estado final é conferido pelo sniffer.
        first = "volume_down" if volume_db is not None and volume_db >= 0 else "volume_up"
        second = "volume_up" if first == "volume_down" else "volume_down"
        try:
            await self.rig.action(first)
            await asyncio.sleep_ms(self.delay_ms)
            await self.rig.action(second)
            self.phase = "waiting_bar"
        except Exception as e:
            self.error, self.phase = str(e), "failed"

    def screen(self, screen, writer, lcd, input_name):
        """Chamado depois de cada tela completa; devolve True se consumiu a tela."""
        if self.phase == "waiting_bar" and screen == "volume":
            # Só agora armamos: o próximo redraw normal é o que queremos editar.
            writer.after_screen(lcd, self.input)
            self.phase = "armed"
            return True
        if self.phase == "armed" and screen == "normal" and input_name == self.input:
            writer.stop()               # fixa a telemetria antes de declarar resultado
            self.phase = "complete" if writer.result == "complete" else "failed"
            if self.phase == "failed":
                self.error = "write plan aborted"
            return True
        if self.phase in ("sending", "waiting_bar", "armed") and self.started is not None \
                and time.ticks_diff(time.ticks_ms(), self.started) > self.timeout_ms:
            writer.stop()
            self.phase, self.error = "failed", "refresh timeout"
        return False
