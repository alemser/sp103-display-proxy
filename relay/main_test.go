package main

import (
	"encoding/binary"
	"math"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func frame(l, r float32, sample uint64) []byte {
	f := make([]byte, frameSize)
	binary.LittleEndian.PutUint32(f[0:], math.Float32bits(l))
	binary.LittleEndian.PutUint32(f[4:], math.Float32bits(r))
	binary.LittleEndian.PutUint64(f[8:], sample)
	return f
}

func TestPacket(t *testing.T) {
	p := packet(frame(0.25, 0.5, 2048), flagProgramme|flagGateKnown)
	if len(p) != packetSize || string(p[:2]) != "VU" || p[2] != version || p[3] != 3 {
		t.Fatalf("header %v", p[:4])
	}
	if l, r := rms(p); l != 0.25 || r != 0.5 {
		t.Fatalf("got L=%v R=%v", l, r)
	}
}

func TestSubscribeLeaseAndLimit(t *testing.T) {
	r := newRelay()
	now := time.Unix(1000, 0)
	for i := 0; i < maxSubs; i++ {
		if !r.subscribe(&net.UDPAddr{IP: net.IPv4(192, 168, 1, byte(10+i)), Port: 5000}, maskVU, now) {
			t.Fatalf("subscriber %d refused", i)
		}
	}
	extra := &net.UDPAddr{IP: net.IPv4(192, 168, 1, 99), Port: 5000}
	if r.subscribe(extra, maskVU, now) {
		t.Fatal("accepted more than maxSubs")
	}
	if n := len(r.targets(now.Add(leaseTTL-time.Second), maskVU)); n != maxSubs {
		t.Fatalf("targets before expiry = %d", n)
	}
	if n := len(r.targets(now.Add(leaseTTL+time.Second), maskVU)); n != 0 {
		t.Fatalf("targets after expiry = %d", n)
	}
	if !r.subscribe(extra, maskVU, now.Add(leaseTTL+time.Second)) {
		t.Fatal("refused after the others expired")
	}
}

func TestRenewKeepsSubscriber(t *testing.T) {
	r := newRelay()
	a := &net.UDPAddr{IP: net.IPv4(192, 168, 1, 108), Port: 5000}
	now := time.Unix(1000, 0)
	r.subscribe(a, maskVU, now)
	r.subscribe(a, maskVU, now.Add(4*time.Second))
	if n := len(r.targets(now.Add(8*time.Second), maskVU)); n != 1 {
		t.Fatalf("renewed subscriber expired: %d", n)
	}
}

func TestReadGate(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "gate.json")
	cases := []struct {
		body          string
		programme, ok bool
	}{
		{`{"state":"programme","rms_threshold":0.01}`, true, true},
		{`{"state":"idle"}`, false, true},
		{`{"state":"weird"}`, false, false},
		{`not json`, false, false},
	}
	for _, c := range cases {
		os.WriteFile(path, []byte(c.body), 0o644)
		p, ok := readGate(path)
		if p != c.programme || ok != c.ok {
			t.Errorf("%s: got %v %v", c.body, p, ok)
		}
	}
	if _, ok := readGate(filepath.Join(dir, "missing.json")); ok {
		t.Error("missing file read as ok")
	}
}

func TestEndToEnd(t *testing.T) {
	dir := t.TempDir()
	sock := filepath.Join(dir, "vu.sock")
	ln, err := net.Listen("unix", sock)
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()

	conn, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	r := newRelay()
	r.programme.Store(true)
	r.gateKnown.Store(true)
	go r.serveSubscriptions(conn)
	go r.pumpVU(sock, conn)

	pico, err := net.DialUDP("udp", nil, conn.LocalAddr().(*net.UDPAddr))
	if err != nil {
		t.Fatal(err)
	}
	defer pico.Close()
	pico.Write(subscribeMsg)

	detector, err := ln.Accept()
	if err != nil {
		t.Fatal(err)
	}
	defer detector.Close()
	deadline := time.Now().Add(2 * time.Second)
	for len(r.targets(time.Now(), maskVU)) == 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	detector.Write(frame(0.1, 0.2, 0))

	pico.SetReadDeadline(time.Now().Add(2 * time.Second))
	buf := make([]byte, 32)
	n, err := pico.Read(buf)
	if err != nil {
		t.Fatal(err)
	}
	if n != packetSize || buf[3] != flagProgramme|flagGateKnown {
		t.Fatalf("packet %v", buf[:n])
	}
	if l, rr := rms(buf[:n]); l != 0.1 || rr != 0.2 {
		t.Fatalf("L=%v R=%v", l, rr)
	}
}

// rms devolve L e R de um pacote .
func rms(p []byte) (float32, float32) {
	return math.Float32frombits(binary.LittleEndian.Uint32(p[4:8])),
		math.Float32frombits(binary.LittleEndian.Uint32(p[8:12]))
}
