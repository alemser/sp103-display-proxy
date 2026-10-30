// Command sp103-vu-relay repassa o VU do groove-detector ao Pico do SP103, por UDP, e
// também o que está tocando, para as telas de informação (nowplaying.go).
//
// O groove-detector publica o VU num socket Unix (16 bytes por quadro, ~21,5 por
// segundo: float32 L, float32 R, uint64 sample_index; ver o docs/contracts.md dele) e
// diz se há música no arquivo do gate ("state": "programme" ou "idle"). O Pico está no
// Wi-Fi e não alcança nenhum dos dois. Esta ponte é só mais um leitor deles: o detector
// não muda e não sabe que o SP103 existe.
//
// Protocolo (porta UDP 7091):
//
//	Pico  → ponte  "SUB1"                       pedido só do VU; vale 6 s, o Pico repete a cada 2 s
//	Pico  → ponte  "SUB2" máscara               bit 0 = VU, bit 1 = telas (docs/api-telas.md)
//	ponte → Pico   "VU" 0x01 flags L R          12 bytes; L e R float32 little-endian (RMS 0..1)
//	               flags: bit 0 = há música, bit 1 = o gate foi lido
//	ponte → Pico   "NP" 0x01 flags campos...    as telas: ver docs/api-telas.md
//
// Sem pedido válido, a ponte não envia nada.
package main

import (
	"encoding/json"
	"flag"
	"io"
	"log"
	"net"
	"os"
	"sync"
	"sync/atomic"
	"time"
)

const (
	frameSize  = 16
	packetSize = 12
	version    = 1
	leaseTTL   = 6 * time.Second
	maxSubs    = 4

	flagProgramme = 1 << 0
	flagGateKnown = 1 << 1

	maskVU   = 1 << 0
	maskInfo = 1 << 1
)

var subscribeMsg = []byte("SUB1")

// parseSubscribe lê um pedido: "SUB1" (só o VU) ou "SUB2" + máscara. 0 = não é pedido.
func parseSubscribe(p []byte) byte {
	switch {
	case len(p) == 4 && string(p) == "SUB1":
		return maskVU
	case len(p) == 5 && string(p[:4]) == "SUB2":
		return p[4] & (maskVU | maskInfo)
	}
	return 0
}

type relay struct {
	mu   sync.Mutex
	subs map[string]subscriber

	programme atomic.Bool
	gateKnown atomic.Bool
}

type subscriber struct {
	addr  *net.UDPAddr
	mask  byte
	until time.Time
}

func newRelay() *relay {
	return &relay{subs: map[string]subscriber{}}
}

// subscribe renova o pedido de addr. Devolve false se já há maxSubs pedidos ativos.
func (r *relay) subscribe(addr *net.UDPAddr, mask byte, now time.Time) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	key := addr.String()
	if _, ok := r.subs[key]; !ok {
		r.expire(now)
		if len(r.subs) >= maxSubs {
			return false
		}
		log.Printf("subscriber %s (mask %d)", key, mask)
	}
	r.subs[key] = subscriber{addr: addr, mask: mask, until: now.Add(leaseTTL)}
	return true
}

// targets devolve os pedidos ainda válidos que querem o que a máscara diz.
func (r *relay) targets(now time.Time, mask byte) []*net.UDPAddr {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.expire(now)
	out := make([]*net.UDPAddr, 0, len(r.subs))
	for _, s := range r.subs {
		if s.mask&mask != 0 {
			out = append(out, s.addr)
		}
	}
	return out
}

func (r *relay) expire(now time.Time) {
	for key, s := range r.subs {
		if now.After(s.until) {
			log.Printf("subscriber %s expired", key)
			delete(r.subs, key)
		}
	}
}

func (r *relay) flags() byte {
	var f byte
	if r.programme.Load() {
		f |= flagProgramme
	}
	if r.gateKnown.Load() {
		f |= flagGateKnown
	}
	return f
}

// packet monta o datagrama para o Pico a partir de um quadro do detector.
func packet(frame []byte, flags byte) []byte {
	p := make([]byte, packetSize)
	p[0], p[1], p[2], p[3] = 'V', 'U', version, flags
	copy(p[4:12], frame[0:8]) // L e R já vêm em float32 little-endian
	return p
}

// readGate lê o "state" do arquivo do gate do detector.
func readGate(path string) (programme, ok bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return false, false
	}
	var g struct {
		State string `json:"state"`
	}
	if json.Unmarshal(data, &g) != nil || (g.State != "programme" && g.State != "idle") {
		return false, false
	}
	return g.State == "programme", true
}

func (r *relay) watchGate(path string, every time.Duration) {
	var last time.Time
	for {
		info, err := os.Stat(path)
		switch {
		case err != nil:
			if r.gateKnown.Swap(false) {
				log.Printf("gate %s: %v", path, err)
			}
			r.programme.Store(false)
			last = time.Time{}
		case !info.ModTime().Equal(last):
			last = info.ModTime()
			programme, ok := readGate(path)
			if ok && programme != r.programme.Load() {
				log.Printf("gate: programme=%v", programme)
			}
			r.programme.Store(programme)
			r.gateKnown.Store(ok)
		}
		time.Sleep(every)
	}
}

func (r *relay) serveSubscriptions(conn *net.UDPConn) {
	buf := make([]byte, 64)
	for {
		n, addr, err := conn.ReadFromUDP(buf)
		if err != nil {
			log.Printf("udp read: %v", err)
			time.Sleep(time.Second)
			continue
		}
		if mask := parseSubscribe(buf[:n]); mask != 0 {
			if !r.subscribe(addr, mask, time.Now()) {
				log.Printf("subscriber %s refused: %d already", addr, maxSubs)
			}
		}
	}
}

func (r *relay) pumpVU(sockPath string, conn *net.UDPConn) {
	frame := make([]byte, frameSize)
	for {
		c, err := net.Dial("unix", sockPath)
		if err != nil {
			log.Printf("vu socket: %v (retrying)", err)
			time.Sleep(2 * time.Second)
			continue
		}
		log.Printf("vu socket %s connected", sockPath)
		for {
			if _, err = io.ReadFull(c, frame); err != nil {
				break
			}
			targets := r.targets(time.Now(), maskVU)
			if len(targets) == 0 {
				continue
			}
			p := packet(frame, r.flags())
			for _, addr := range targets {
				conn.WriteToUDP(p, addr) // UDP: um quadro perdido não importa
			}
		}
		c.Close()
		log.Printf("vu socket closed: %v (reconnecting)", err)
		time.Sleep(time.Second)
	}
}

func main() {
	listen := flag.String("listen", ":7091", "endereço UDP para os pedidos do Pico")
	vuSock := flag.String("vu", "/tmp/groove-vu.sock", "socket do VU do groove-detector")
	gate := flag.String("gate", "/tmp/groove-gate.json", "arquivo do gate do groove-detector")
	identity := flag.String("identity", "http://127.0.0.1:7071", "groove-identity (o que está tocando)")
	catalog := flag.String("catalog", "http://127.0.0.1:7073", "groove-catalog (faixas do disco e agulha)")
	flag.Parse()

	addr, err := net.ResolveUDPAddr("udp", *listen)
	if err != nil {
		log.Fatal(err)
	}
	conn, err := net.ListenUDP("udp", addr)
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("sp103-vu-relay on udp %s, vu %s, gate %s, identity %s, catalog %s",
		*listen, *vuSock, *gate, *identity, *catalog)

	r := newRelay()
	go r.watchGate(*gate, 500*time.Millisecond)
	go r.serveSubscriptions(conn)
	go r.pumpInfo(newNowPlaying(*identity, *catalog), conn)
	r.pumpVU(*vuSock, conn)
}
