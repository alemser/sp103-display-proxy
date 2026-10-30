package main

import (
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestParseSubscribe(t *testing.T) {
	cases := []struct {
		in   string
		want byte
	}{
		{"SUB1", maskVU},
		{"SUB2\x01", maskVU},
		{"SUB2\x02", maskInfo},
		{"SUB2\x03", maskVU | maskInfo},
		{"SUB2\xff", maskVU | maskInfo},
		{"SUB2", 0},
		{"SUB3\x01", 0},
		{"hello", 0},
	}
	for _, c := range cases {
		if got := parseSubscribe([]byte(c.in)); got != c.want {
			t.Errorf("%q: got %d, want %d", c.in, got, c.want)
		}
	}
}

func TestTargetsByMask(t *testing.T) {
	r := newRelay()
	now := time.Unix(1000, 0)
	vuOnly := &net.UDPAddr{IP: net.IPv4(192, 168, 1, 10), Port: 5000}
	both := &net.UDPAddr{IP: net.IPv4(192, 168, 1, 11), Port: 5000}
	r.subscribe(vuOnly, maskVU, now)
	r.subscribe(both, maskVU|maskInfo, now)
	if n := len(r.targets(now, maskVU)); n != 2 {
		t.Errorf("VU targets = %d", n)
	}
	if got := r.targets(now, maskInfo); len(got) != 1 || got[0] != both {
		t.Errorf("info targets = %v", got)
	}
	r.subscribe(both, maskInfo, now) // o Pico desligou o VU
	if n := len(r.targets(now, maskVU)); n != 1 {
		t.Errorf("VU targets after mask change = %d", n)
	}
}

func TestFold(t *testing.T) {
	cases := map[string]string{
		"Construção":                "Construcao",
		"  Björk   Guðmundsdóttir ": "Bjork Gudmundsdottir",
		"Don’t Stop – Live":         "Don't Stop - Live",
		"AC\\DC ~ remix":            "AC/DC - remix",
		"東京":                        "??",
		strings.Repeat("x", 50):     strings.Repeat("x", maxText),
	}
	for in, want := range cases {
		if got := fold(in); got != want {
			t.Errorf("fold(%q) = %q, want %q", in, got, want)
		}
	}
	for _, r := range fold("ÀÉÎÕÜçñ{|}") {
		if r < ' ' || r > '}' || r == '\\' {
			t.Errorf("character %q outside the display ROM", r)
		}
	}
}

func TestInfoPacket(t *testing.T) {
	in := unknownInfo()
	in.Playing = true
	in.Artist, in.Title, in.Position = "Pink Floyd", "Time", "A4"
	in.Elapsed, in.Duration = 161, 421
	in.Side, in.SideTrack, in.SideTracks, in.SideLeft = "A", 4, 5, 544
	p := in.packet()
	if string(p[:2]) != "NP" || p[2] != npVersion || p[3] != npFlagPlaying {
		t.Fatalf("header %v", p[:4])
	}
	want := "Pink Floyd\x1fTime\x1fA4\x1f161\x1f421\x1fA\x1f4\x1f5\x1f544\x1f\x1f"
	if string(p[4:]) != want {
		t.Fatalf("fields %q", p[4:])
	}
	if f := strings.Split(string(p[4:]), fieldDivider); len(f) != 11 {
		t.Fatalf("%d fields", len(f))
	}
}

func TestSameScreenIgnoresClocks(t *testing.T) {
	a := unknownInfo()
	a.Playing, a.Title, a.Elapsed, a.SideLeft = true, "Time", 10, 500
	b := a
	b.Elapsed, b.SideLeft = 11, 499
	if !sameScreen(a, b) {
		t.Error("only the clocks moved")
	}
	b.Title = "Breathe"
	if sameScreen(a, b) {
		t.Error("the track changed")
	}
}

var darkSide = []track{
	{"A1", 67000}, {"A2", 163000}, {"A3", 216000}, {"A4", 421000}, {"A5", 284000},
	{"B1", 382000}, {"B2", 469000},
}

func TestSideOf(t *testing.T) {
	side, idx, total, left := sideOf(darkSide, "A4", 260)
	if side != "A" || idx != 4 || total != 5 || left != 260+284 {
		t.Errorf("A4: %s %d/%d %d", side, idx, total, left)
	}
	if _, idx, total, left = sideOf(darkSide, "B2", 10); idx != 2 || total != 2 || left != 10 {
		t.Errorf("B2 (last): %d/%d %d", idx, total, left)
	}
	if side, _, _, _ = sideOf(darkSide, "4", 10); side != "" {
		t.Errorf("a CD position has no side: %q", side)
	}
	if _, idx, _, _ = sideOf(darkSide, "C1", 10); idx != -1 {
		t.Error("a track not in the list")
	}
	gap := []track{{"A1", 1000}, {"A2", 0}}
	if _, _, _, left = sideOf(gap, "A1", 5); left != -1 {
		t.Error("an unknown duration makes the side time unknown")
	}
}

// fakeGroove simula o identity e o catálogo do Pi 5.
type fakeGroove struct {
	status      string
	stylusCalls int
	trackCalls  int
}

func (f *fakeGroove) server() *httptest.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/status", func(w http.ResponseWriter, _ *http.Request) { fmt.Fprint(w, f.status) })
	mux.HandleFunc("/catalog/stylus", func(w http.ResponseWriter, _ *http.Request) {
		f.stylusCalls++
		fmt.Fprint(w, `{"active":true,"metrics":{"stylus_hours_total":119.35,"wear_percent":11.94}}`)
	})
	mux.HandleFunc("/catalog/library/releases/user/dsotm/tracks", func(w http.ResponseWriter, _ *http.Request) {
		f.trackCalls++
		fmt.Fprint(w, `{"items":[{"track_position":"A1","duration_ms":67000},{"track_position":"A2","duration_ms":163000},
			{"track_position":"A3","duration_ms":216000},{"track_position":"A4","duration_ms":421000},
			{"track_position":"A5","duration_ms":284000},{"track_position":"B1","duration_ms":382000}]}`)
	})
	return httptest.NewServer(mux)
}

func playing(pos string, posMs, durMs int) string {
	return playingEpochs(pos, posMs, durMs, 984, 984)
}

// playingEpochs é o /status com a captura da faixa mostrada (playback) e a de agora
// (recognition): o fim da música abre uma captura nova antes de o identity largar a faixa.
func playingEpochs(pos string, posMs, durMs int, playbackEpoch, captureEpoch uint64) string {
	return fmt.Sprintf(`{"playback":{"active":true,"epoch":%d,"artist":"Pink Floyd","title":"Some Track",
		"track_position":%q,"position_ms":%d,"duration_ms":%d},"recognition":{"phase":"identifying","epoch":%d},
		"album_programme":{"active":true,"release_source":"user","release_id":"dsotm"}}`,
		playbackEpoch, pos, posMs, durMs, captureEpoch)
}

func TestNowPlayingRead(t *testing.T) {
	g := &fakeGroove{status: playing("A4", 161000, 421000)}
	srv := g.server()
	defer srv.Close()
	np := newNowPlaying(srv.URL, srv.URL+"/")
	now := time.Unix(1000, 0)

	in := np.read(now)
	if !in.Playing || in.Title != "Some Track" || in.Position != "A4" || in.Elapsed != 161 || in.Duration != 421 {
		t.Fatalf("track: %+v", in)
	}
	if in.Side != "A" || in.SideTrack != 4 || in.SideTracks != 5 || in.SideLeft != 260+284 {
		t.Fatalf("side: %+v", in)
	}
	if in.StylusHours != 119 || in.StylusWear != 12 {
		t.Fatalf("stylus: %+v", in)
	}
	np.read(now.Add(time.Second))
	if g.stylusCalls != 1 || g.trackCalls != 1 {
		t.Errorf("stylus read %d times, tracks %d times; want once each", g.stylusCalls, g.trackCalls)
	}
	np.read(now.Add(stylusEvery))
	if g.stylusCalls != 2 {
		t.Errorf("stylus not refreshed after %v", stylusEvery)
	}

	// A última faixa do lado chega ao fim e o reconhecimento para: "Flip the record".
	g.status = playing("A5", 270000, 284000)
	np.read(now.Add(2 * time.Second))
	g.status = `{"playback":{"active":false}}`
	in = np.read(now.Add(20 * time.Second))
	if in.Playing || !in.SideEnd || in.Side != "A" || in.SideLeft != 0 {
		t.Fatalf("side end: %+v", in)
	}
	if in = np.read(now.Add(20*time.Second + sideEndHold/2)); !in.SideEnd {
		t.Error("side end should hold for a while")
	}
	if in = np.read(now.Add(21*time.Second + sideEndHold)); in.SideEnd {
		t.Error("side end should expire")
	}

	// A música da última faixa acaba antes da duração do catálogo (Exodus, 2026-10-30): o
	// identity abre a captura do sulco final e ainda mostra a faixa. O lado acabou ali.
	g.status = playingEpochs("A5", 260000, 284000, 984, 984)
	np.read(now.Add(30 * time.Minute))
	g.status = playingEpochs("A5", 272000, 284000, 984, 993)
	if in = np.read(now.Add(30*time.Minute + 12*time.Second)); in.Playing || !in.SideEnd || in.Side != "A" {
		t.Fatalf("new capture on the last track: %+v", in)
	}
	g.status = playingEpochs("A5", 299000, 284000, 984, 993)
	if in = np.read(now.Add(30*time.Minute + 39*time.Second)); in.Playing || !in.SideEnd {
		t.Errorf("the old track must not come back while its capture is stale: %+v", in)
	}
	g.status = playingEpochs("B1", 3000, 382000, 995, 995)
	if in = np.read(now.Add(40 * time.Minute)); !in.Playing || in.SideEnd || in.Position != "B1" {
		t.Errorf("next side: %+v", in)
	}

	// Uma captura nova no meio do lado (troca de faixa) não é fim de lado.
	g.status = playingEpochs("A2", 150000, 163000, 1000, 1001)
	if in = np.read(now.Add(50 * time.Minute)); !in.Playing || in.SideEnd {
		t.Errorf("track change mid-side: %+v", in)
	}

	// Parou no meio do lado: só "não tocando".
	g.status = playing("A2", 10000, 163000)
	np.read(now.Add(time.Hour))
	g.status = `{"playback":{"active":false}}`
	if in = np.read(now.Add(time.Hour + time.Second)); in.SideEnd || in.Playing || in.Title != "" {
		t.Errorf("stopped mid-side: %+v", in)
	}
}

func TestNowPlayingServicesDown(t *testing.T) {
	np := newNowPlaying("http://127.0.0.1:1", "http://127.0.0.1:1")
	in := np.read(time.Unix(1000, 0))
	if in.Playing || in.Title != "" || in.StylusHours != -1 {
		t.Errorf("services down: %+v", in)
	}
	if p := in.packet(); string(p[4:]) != strings.Repeat(fieldDivider, 10) {
		t.Errorf("empty packet %q", p[4:])
	}
}

func TestPumpInfoEndToEnd(t *testing.T) {
	g := &fakeGroove{status: playing("A4", 161000, 421000)}
	srv := g.server()
	defer srv.Close()

	conn, err := net.ListenUDP("udp", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	r := newRelay()
	go r.serveSubscriptions(conn)
	go r.pumpInfo(newNowPlaying(srv.URL, srv.URL), conn)

	pico, err := net.DialUDP("udp", nil, conn.LocalAddr().(*net.UDPAddr))
	if err != nil {
		t.Fatal(err)
	}
	defer pico.Close()
	pico.Write([]byte("SUB2\x02"))

	pico.SetReadDeadline(time.Now().Add(3 * time.Second))
	buf := make([]byte, 256)
	n, err := pico.Read(buf)
	if err != nil {
		t.Fatal(err)
	}
	if string(buf[:2]) != "NP" || !strings.HasPrefix(string(buf[4:n]), "Pink Floyd\x1fSome Track\x1fA4\x1f") {
		t.Fatalf("packet %q", buf[:n])
	}
}
