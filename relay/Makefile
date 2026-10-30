# Ponte do VU (sp103-vu-relay). Compila no Mac e instala na placa pelo ssh, como os groove-*.
#
#   make test
#   make deploy-pi                               # oceano-0000 (Pi 5), onde fica o SP103
#   make deploy HOST=orange@192.168.178.105      # outra placa (oceano-0001, Orange Pi)

BINARY := sp103-vu-relay
BIN := bin/$(BINARY)-linux-arm64
HOST ?= alemser@192.168.178.99

.PHONY: build test deploy deploy-pi status

build:
	@mkdir -p bin
	GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -o $(BIN) .

test:
	go vet ./... && go test ./...

deploy: test build
	scp $(BIN) $(HOST):/tmp/$(BINARY).new
	scp $(BINARY).service $(HOST):/tmp/$(BINARY).service
	ssh $(HOST) "sudo install -m 0755 /tmp/$(BINARY).new /usr/local/bin/$(BINARY) && \
		sudo install -m 0644 /tmp/$(BINARY).service /etc/systemd/system/$(BINARY).service && \
		rm /tmp/$(BINARY).new /tmp/$(BINARY).service && \
		sudo systemctl daemon-reload && sudo systemctl enable --now $(BINARY) && \
		sudo systemctl restart $(BINARY) && sleep 1 && systemctl --no-pager status $(BINARY) | head -12"

# O mesmo nome dos groove-*: instala no Pi 5.
deploy-pi: deploy

status:
	ssh $(HOST) "systemctl --no-pager status $(BINARY) | head -12; journalctl -u $(BINARY) -n 20 --no-pager"
