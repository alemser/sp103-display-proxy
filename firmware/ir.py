"""Manda comandos ao amp pela linha do IR e observa o botão do volume.

Ligação (docs/proxy-ligacao.md):

    GP15 = saída do receptor IR (perna 12 do controlador)
    GP14 = E1 do encoder do volume (perna 22 do controlador), só leitura

REGRA DE SEGURANÇA (a mesma do busy.py): o GP15 NUNCA vai a 1. O valor de saída fica em 0 e só a
direção muda, na força mínima (2 mA). A linha sobe por um resistor de cerca de 40 kΩ dentro do
receptor (medido em 2026-11-06): puxar para 0 custa cerca de 0,1 mA. O GP14 nunca é saída.

O PIO só segura a linha em 0 durante um tempo já contado. Enquanto espera o próximo tempo, ela
fica solta: se o DMA parar no meio, a linha não fica presa em 0 e o controle remoto segue ativo.
O DMA entrega os tempos sozinho, então uma pausa do Python não estraga o código enviado.

Criar DEPOIS do Sniffer e do Responder, e o mais cedo possível: até aqui, o GP15 está com o
pull-down do RP2350 ligado, e ele carregaria a linha do IR.
"""

import asyncio
import time
from array import array

import rp2
from machine import Pin, mem32

import ir_codes

IR_PIN, KNOB_PIN = 15, 14
KNOB_POLL_MS = 5
WAKE_WINDOW_MS = 1000           # duas mudanças do E1 neste tempo = alguém girou o botão
WAKE_COOLDOWN_MS = 5000         # o comando é o mesmo para ligar e desligar: nunca mandar dois seguidos
_PADS_BANK0 = 0x40038000
_DRIVE_MASK = 0x3 << 4
_PIO_BASE = (0x50200000, 0x50300000, 0x50400000)
_TXF0 = 0x010                   # fila de entrada (TX) da máquina 0; as outras seguem de 4 em 4
_DREQ_PIO_TX0 = (0, 8, 16)      # pedido de DMA "a fila TX tem espaço"


@rp2.asm_pio(set_init=rp2.PIO.IN_LOW)
def _pulses():
    # A 1 MHz: cada volta do jmp dura 1 µs. Cada par de palavras: linha em 0, linha solta.
    pull()
    mov(x, osr)
    set(pindirs, 1)             # linha em 0
    label("mark")
    jmp(x_dec, "mark")
    set(pindirs, 0)             # solta a linha antes de esperar a próxima palavra
    pull()
    mov(x, osr)
    label("space")
    jmp(x_dec, "space")


class Remote:
    def __init__(self, sm_id=5):
        # sm_id 5 = PIO1, máquina 1 (a máquina 0 é a do busy.py).
        self.line = Pin(IR_PIN, Pin.IN, pull=None)
        self.knob = Pin(KNOB_PIN, Pin.IN, pull=None)
        self.sm = rp2.StateMachine(sm_id, _pulses, freq=1_000_000, set_base=Pin(IR_PIN))
        self.sm.exec("set(pins, 0)")
        self.sm.exec("set(pindirs, 0)")
        pad = _PADS_BANK0 + 4 + 4 * IR_PIN
        mem32[pad] = mem32[pad] & ~_DRIVE_MASK & ~1     # 2 mA, borda lenta
        self.sm.active(1)
        pio, sm = divmod(sm_id, 4)
        self._fifo = _PIO_BASE[pio] + _TXF0 + 4 * sm
        self.dma = rp2.DMA()
        self._ctrl = self.dma.pack_ctrl(size=2, inc_read=True, inc_write=False,
                                        treq_sel=_DREQ_PIO_TX0[pio] + sm)
        self._words = None              # o DMA lê daqui: não pode sumir durante o envio
        self._until = time.ticks_ms()
        self.sent = 0
        self.knob_edges = 0
        self._knob_at = time.ticks_add(time.ticks_ms(), -WAKE_WINDOW_MS)
        self._woke_at = time.ticks_add(time.ticks_ms(), -WAKE_COOLDOWN_MS)
        self.wakes = 0
        self.standby = lambda: False    # o proxy.py troca: só acorda com certeza de standby

    def sending(self):
        return time.ticks_diff(self._until, time.ticks_ms()) > 0

    def _start(self, words):
        self._words = array("I", words)
        self._until = time.ticks_add(time.ticks_ms(), sum(words) // 1000 + 10)
        self.dma.config(read=self._words, write=self._fifo, count=len(words), ctrl=self._ctrl, trigger=True)
        self.sent += 1

    def send(self, command):
        self._start(ir_codes.frame(command))

    def status(self):
        return {"commands": list(ir_codes.COMMANDS), "sending": self.sending(), "sent": self.sent,
                "line": self.line.value(), "knob": self.knob.value(), "knob_edges": self.knob_edges,
                "wakes": self.wakes}

    def _knob_moved(self):
        """Com o amp em standby, girar o botão liga o amp. Em qualquer outro estado, não faz nada."""
        ms = time.ticks_ms()
        turning = time.ticks_diff(ms, self._knob_at) < WAKE_WINDOW_MS
        self._knob_at = ms
        if (turning and self.standby() and not self.sending()
                and time.ticks_diff(ms, self._woke_at) >= WAKE_COOLDOWN_MS):
            self._woke_at = ms
            self.wakes += 1
            self.send("power_toggle")

    async def watch_knob(self):
        """Acompanha o E1. Um giro dura dezenas de ms, então olhar de tempos em tempos basta."""
        last = self.knob.value()
        while True:
            now = self.knob.value()
            if now != last:
                last = now
                self.knob_edges += 1
                self._knob_moved()
            await asyncio.sleep_ms(KNOB_POLL_MS)

    async def handle(self, req, writer):
        """Rotas /ir (ver web.Publisher e docs/api-estado.md)."""
        from web import reply, reply_json
        if req.path == "/ir" and req.method == "GET":
            return await reply_json(writer, self.status())
        if req.method != "POST" or req.path != "/ir/send":
            return await reply(writer, "404 Not Found", "text/plain", b"not found\n")
        command = req.query.get("cmd")
        if self.sending():
            return await reply_json(writer, {"error": "busy"}, "400 Bad Request")
        if command not in ir_codes.COMMANDS:
            return await reply_json(writer, {"error": "unknown command"}, "400 Bad Request")
        self.send(command)
        await reply_json(writer, self.status())
