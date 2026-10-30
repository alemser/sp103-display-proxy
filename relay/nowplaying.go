package main

// Telas de informação: o que está tocando, para o display do SP103 (docs/api-telas.md).
//
// Esta ponte é o adaptador do groove: lê o groove-identity (artista, música, posição,
// faixa no disco) e o groove-catalog (faixas do disco, agulha) e traduz para o contrato
// do Pico, que não sabe de onde os dados vêm. O Pico só desenha: o texto chega sem
// acentos e cortado, e os tempos valem no instante do envio (o Pico conta a partir dali).

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	npVersion     = 1
	npFlagPlaying = 1 << 0
	npFlagSideEnd = 1 << 1

	infoPoll    = time.Second
	infoEvery   = 5 * time.Second // mesmo sem mudança
	stylusEvery = 10 * time.Minute
	sideEndHold = 15 * time.Minute
	// "Acabou o lado" só se a última faixa estava a menos disto do fim, pela duração do
	// catálogo. Medido no Pi 5 em 2026-10-30: Exodus (A5) acabou 12 s antes da duração do
	// catálogo; One Love (B5), 5 s depois. Escolhido com folga sobre os dois.
	sideEndNear  = 30 // s
	maxText      = 40
	httpTimeout  = 2 * time.Second
	fieldDivider = "\x1f"
)

// info é o que vai num pacote "NP". Números < 0 = não se sabe (campo vazio).
type info struct {
	Playing, SideEnd                bool
	Artist, Title, Position, Side   string
	Elapsed, Duration               int
	SideTrack, SideTracks, SideLeft int
	StylusHours, StylusWear         int
}

func unknownInfo() info {
	return info{Elapsed: -1, Duration: -1, SideTrack: -1, SideTracks: -1, SideLeft: -1,
		StylusHours: -1, StylusWear: -1}
}

// packet monta o datagrama "NP" (docs/api-telas.md).
func (in info) packet() []byte {
	num := func(v int) string {
		if v < 0 {
			return ""
		}
		return strconv.Itoa(v)
	}
	fields := []string{fold(in.Artist), fold(in.Title), fold(in.Position), num(in.Elapsed), num(in.Duration),
		fold(in.Side), num(in.SideTrack), num(in.SideTracks), num(in.SideLeft),
		num(in.StylusHours), num(in.StylusWear)}
	var flags byte
	if in.Playing {
		flags |= npFlagPlaying
	}
	if in.SideEnd {
		flags |= npFlagSideEnd
	}
	return append([]byte{'N', 'P', npVersion, flags}, strings.Join(fields, fieldDivider)...)
}

// sameScreen diz se duas leituras mostram o mesmo: os tempos andam sozinhos no Pico.
func sameScreen(a, b info) bool {
	a.Elapsed, a.SideLeft, b.Elapsed, b.SideLeft = 0, 0, 0, 0
	return a == b
}

var foldTable = map[rune]string{
	'ß': "ss", 'æ': "ae", 'Æ': "AE", 'œ': "oe", 'Œ': "OE", 'ð': "d", 'Ð': "D", 'þ': "th", 'Þ': "Th",
	'‘': "'", '’': "'", '´': "'", '`': "'", '“': "\"", '”': "\"", '–': "-", '—': "-", '…': "...",
	'~': "-", '\\': "/", '·': "-", '×': "x", ' ': " ",
}

func init() {
	for _, group := range []string{"aàáâãäåā", "AÀÁÂÃÄÅĀ", "cçćč", "CÇĆČ", "eèéêëēę", "EÈÉÊËĒĘ", "iìíîïī", "IÌÍÎÏĪ",
		"nñń", "NÑŃ", "oòóôõöøō", "OÒÓÔÕÖØŌ", "uùúûüū", "UÙÚÛÜŪ", "yýÿ", "YÝŸ", "sšś", "SŠŚ", "zžźż", "ZŽŹŻ",
		"lł", "LŁ", "rř", "RŘ", "gğ", "GĞ"} {
		r := []rune(group)
		for _, x := range r[1:] {
			foldTable[x] = string(r[0])
		}
	}
}

// fold deixa o texto no que a ROM do display tem: ASCII de " " a "}", sem "\" (vira "¥"
// no display) e cortado em maxText caracteres. Letras sem equivalente viram "?".
func fold(s string) string {
	var b strings.Builder
	for _, r := range strings.Join(strings.Fields(s), " ") {
		switch {
		case foldTable[r] != "":
			b.WriteString(foldTable[r])
		case r >= ' ' && r <= '}':
			b.WriteRune(r)
		default:
			b.WriteByte('?')
		}
		if b.Len() >= maxText {
			break
		}
	}
	out := b.String()
	if len(out) > maxText {
		out = out[:maxText]
	}
	return strings.TrimSpace(out)
}

// track é uma faixa do disco no catálogo.
type track struct {
	Position string `json:"track_position"`
	Duration int64  `json:"duration_ms"`
}

// splitPosition separa "A4" em lado "A" e número 4. Sem letra (um CD: "4") = sem lado.
func splitPosition(pos string) (side string, n int, ok bool) {
	pos = strings.TrimSpace(pos)
	i := 0
	for i < len(pos) && (pos[i] >= 'A' && pos[i] <= 'Z' || pos[i] >= 'a' && pos[i] <= 'z') {
		i++
	}
	n, err := strconv.Atoi(pos[i:])
	if i == 0 || err != nil {
		return "", 0, false
	}
	return strings.ToUpper(pos[:i]), n, true
}

// sideOf calcula lado, faixa no lado, faixas no lado e o tempo até o fim do lado (s).
// left = o que falta da faixa de agora. Sem a duração de alguma faixa seguinte, o tempo
// do lado fica -1.
func sideOf(tracks []track, pos string, left int) (side string, idx, total, sideLeft int) {
	side, n, ok := splitPosition(pos)
	if !ok {
		return "", -1, -1, -1
	}
	type entry struct {
		n   int
		dur int64
	}
	var same []entry
	for _, t := range tracks {
		if s, tn, ok := splitPosition(t.Position); ok && s == side {
			same = append(same, entry{tn, t.Duration})
		}
	}
	sort.Slice(same, func(a, b int) bool { return same[a].n < same[b].n })
	idx, sideLeft = -1, -1
	if left >= 0 {
		sideLeft = left
	}
	for i, e := range same {
		if e.n == n {
			idx = i + 1
		} else if idx > 0 && sideLeft >= 0 {
			if e.dur <= 0 {
				sideLeft = -1
			} else {
				sideLeft += int(e.dur / 1000)
			}
		}
	}
	if idx < 0 {
		return side, -1, -1, -1
	}
	return side, idx, len(same), sideLeft
}

// identityStatus é o pedaço do GET /status do groove-identity que interessa aqui.
type identityStatus struct {
	Playback struct {
		Active        bool   `json:"active"`
		Epoch         uint64 `json:"epoch"`
		Artist        string `json:"artist"`
		Title         string `json:"title"`
		TrackPosition string `json:"track_position"`
		PositionMs    int64  `json:"position_ms"`
		DurationMs    int64  `json:"duration_ms"`
	} `json:"playback"`
	Recognition struct {
		Epoch uint64 `json:"epoch"`
	} `json:"recognition"`
	AlbumProgramme *struct {
		ReleaseSource string `json:"release_source"`
		ReleaseID     string `json:"release_id"`
	} `json:"album_programme"`
}

type stylusState struct {
	Active  bool `json:"active"`
	Metrics struct {
		Hours float64 `json:"stylus_hours_total"`
		Wear  float64 `json:"wear_percent"`
	} `json:"metrics"`
}

// nowPlaying lê os serviços do groove e guarda o que precisa entre uma leitura e outra.
type nowPlaying struct {
	identity, catalog string
	client            *http.Client

	release    string // source/id do disco cujas faixas estão em tracks
	tracks     []track
	stylus     info // só os campos da agulha
	stylusAt   time.Time
	last       info // a leitura anterior
	sideEndAt  time.Time
	lastWasEnd bool   // a leitura anterior era a última faixa do lado, perto do fim
	endedEpoch uint64 // a captura da última faixa de um lado que já acabou
}

func newNowPlaying(identity, catalog string) *nowPlaying {
	return &nowPlaying{identity: strings.TrimRight(identity, "/"), catalog: strings.TrimRight(catalog, "/"),
		client: &http.Client{Timeout: httpTimeout}, stylus: unknownInfo(), last: unknownInfo()}
}

func (np *nowPlaying) getJSON(u string, v any) error {
	resp, err := np.client.Get(u)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("%s: %s", u, resp.Status)
	}
	return json.NewDecoder(resp.Body).Decode(v)
}

// read faz uma leitura completa. Um serviço fora do ar só esvazia os campos dele.
func (np *nowPlaying) read(now time.Time) info {
	in := unknownInfo()
	if np.stylusAt.IsZero() || now.Sub(np.stylusAt) >= stylusEvery {
		np.stylusAt = now
		np.stylus = unknownInfo()
		var st stylusState
		if err := np.getJSON(np.catalog+"/catalog/stylus", &st); err != nil {
			log.Printf("stylus: %v", err)
		} else if st.Active {
			np.stylus.StylusHours = int(st.Metrics.Hours + 0.5)
			np.stylus.StylusWear = int(st.Metrics.Wear + 0.5)
		}
	}
	in.StylusHours, in.StylusWear = np.stylus.StylusHours, np.stylus.StylusWear

	var st identityStatus
	if err := np.getJSON(np.identity+"/status", &st); err != nil {
		log.Printf("identity: %v", err)
		return in
	}
	pb := st.Playback
	// Quando a música acaba, o groove-listener vê o fim da faixa e o identity abre uma
	// captura nova (o sulco final) antes de largar a faixa que mostrava (27 s antes às 16:03). Na última
	// faixa do lado, perto do fim, essa captura nova já é o fim do lado; a faixa que o
	// identity continua mostrando, com a captura velha, não volta a contar como tocando.
	// Medido no Pi 5 em 2026-10-30: 15:36:51 e 16:03:12, os dois fins de lado do dia.
	if np.lastWasEnd && pb.Epoch != 0 && st.Recognition.Epoch > pb.Epoch {
		np.endedEpoch = pb.Epoch
	}
	if pb.Active && pb.Title != "" && pb.Epoch != np.endedEpoch {
		in.Playing = true
		in.Artist, in.Title, in.Position = pb.Artist, pb.Title, pb.TrackPosition
		left := -1
		if pb.DurationMs > 0 {
			in.Duration = int(pb.DurationMs / 1000)
			in.Elapsed = int(pb.PositionMs / 1000)
			if in.Elapsed > in.Duration {
				in.Elapsed = in.Duration
			}
			left = in.Duration - in.Elapsed
		}
		if p := st.AlbumProgramme; p != nil && p.ReleaseSource != "" && p.ReleaseID != "" {
			np.loadTracks(p.ReleaseSource, p.ReleaseID)
			in.Side, in.SideTrack, in.SideTracks, in.SideLeft = sideOf(np.tracks, pb.TrackPosition, left)
		}
		np.lastWasEnd = in.SideTrack > 0 && in.SideTrack == in.SideTracks && left >= 0 && left <= sideEndNear
		np.sideEndAt, np.endedEpoch = time.Time{}, 0
	} else if np.lastWasEnd || (!np.sideEndAt.IsZero() && now.Sub(np.sideEndAt) < sideEndHold) {
		// A última faixa do lado acabou (captura nova ou reconhecimento parado): "Flip the record".
		if np.sideEndAt.IsZero() {
			np.sideEndAt = now
			log.Printf("side %s ended", np.last.Side)
		}
		np.lastWasEnd = false
		in.SideEnd = true
		in.Artist, in.Side, in.SideLeft = np.last.Artist, np.last.Side, 0
		in.SideTracks = np.last.SideTracks
		in.SideTrack = np.last.SideTracks
	}
	if in.Playing {
		np.last = in
	}
	return in
}

// loadTracks busca as faixas do disco uma vez por disco.
func (np *nowPlaying) loadTracks(source, id string) {
	key := source + "/" + id
	if key == np.release {
		return
	}
	var resp struct {
		Items []track `json:"items"`
	}
	u := np.catalog + "/catalog/library/releases/" + url.PathEscape(source) + "/" + url.PathEscape(id) + "/tracks"
	if err := np.getJSON(u, &resp); err != nil {
		log.Printf("tracks %s: %v", key, err)
		np.tracks = nil // tenta de novo na próxima leitura
		return
	}
	np.release, np.tracks = key, resp.Items
	log.Printf("release %s: %d tracks", key, len(resp.Items))
}

// pumpInfo lê os serviços a cada segundo, só enquanto alguém pede as telas, e manda o
// pacote quando o que aparece muda ou a cada infoEvery.
func (r *relay) pumpInfo(np *nowPlaying, conn *net.UDPConn) {
	var sent info
	var sentAt time.Time
	for {
		now := time.Now()
		targets := r.targets(now, maskInfo)
		if len(targets) == 0 {
			sentAt = time.Time{}
			time.Sleep(infoPoll)
			continue
		}
		in := np.read(now)
		if sentAt.IsZero() || !sameScreen(in, sent) || now.Sub(sentAt) >= infoEvery {
			p := in.packet()
			for _, addr := range targets {
				conn.WriteToUDP(p, addr)
			}
			sent, sentAt = in, now
		}
		time.Sleep(infoPoll)
	}
}
