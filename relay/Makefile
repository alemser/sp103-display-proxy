# Ponte do VU (sp103-vu-relay). Compila no computador e instala pelo ssh em qualquer placa
# Linux com o groove-detector. A arquitetura vem da própria placa.
#
#   make test
#   make deploy HOST=usuario@ip      # instala ou atualiza
#   make check HOST=usuario@ip       # a ponte responde?
#   make status HOST=usuario@ip      # serviço e log

BINARY := sp103-vu-relay
GOARCH ?= arm64
BIN = bin/$(BINARY)-linux-$(GOARCH)
ADDR = $(lastword $(subst @, ,$(HOST)))

.PHONY: build test deploy check status need-host

need-host:
	@test -n "$(HOST)" || { echo "Falta a placa: make $(MAKECMDGOALS) HOST=usuario@ip"; exit 1; }

build:
	@mkdir -p bin
	GOOS=linux GOARCH=$(GOARCH) GOARM=6 CGO_ENABLED=0 go build -o $(BIN) .

test:
	go vet ./... && go test ./...

# O -t deixa o sudo pedir a senha nas placas que pedem.
deploy: need-host test
	@ssh $(HOST) "getent group groove >/dev/null" || { echo "$(HOST) não tem o grupo groove: falta o groove-detector?"; exit 1; }
	@arch=$$(ssh $(HOST) "dpkg --print-architecture"); \
	case "$$arch" in armhf) arch=arm;; arm64|amd64) ;; *) echo "Arquitetura desconhecida: $$arch"; exit 1;; esac; \
	$(MAKE) --no-print-directory build GOARCH=$$arch && \
	scp bin/$(BINARY)-linux-$$arch $(HOST):/tmp/$(BINARY).new
	scp $(BINARY).service $(HOST):/tmp/$(BINARY).service
	ssh -t $(HOST) "sudo install -m 0755 /tmp/$(BINARY).new /usr/local/bin/$(BINARY) && \
		sudo install -m 0644 /tmp/$(BINARY).service /etc/systemd/system/$(BINARY).service && \
		rm /tmp/$(BINARY).new /tmp/$(BINARY).service && \
		sudo systemctl daemon-reload && sudo systemctl enable --now $(BINARY) && \
		sudo systemctl restart $(BINARY) && sleep 1 && systemctl --no-pager status $(BINARY) | head -12"

check: need-host
	-@ssh $(HOST) "for s in groove-detector $(BINARY); do printf '%s: ' \$$s; systemctl is-active \$$s; done"
	@python3 ../tools/vu_check.py $(ADDR)

status: need-host
	ssh $(HOST) "systemctl --no-pager status $(BINARY) | head -12; journalctl -u $(BINARY) -n 20 --no-pager"
