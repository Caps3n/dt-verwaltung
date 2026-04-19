#!/bin/sh
# Auto-switch to bash if called via sh
if [ -z "$BASH_VERSION" ]; then
  exec bash "$0" "$@"
fi
# ═══════════════════════════════════════════════════════════════
#  DT-Verwaltung – Installer / Updater
#  Verwendung: bash install.sh  ODER  sh install.sh
# ═══════════════════════════════════════════════════════════════
set -e
BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
p()  { printf "${1}${NC}\n"; }
ph() { printf "\n${BOLD}${1}${NC}\n"; }

p ""
p "${BOLD}╔══════════════════════════════════════════╗"
p "${BOLD}║     DT-Verwaltung – Installation         ║"
p "${BOLD}╚══════════════════════════════════════════╝"
p ""

# ── 1. Docker prüfen ────────────────────────────────────────────
DOCKER_BIN=$(command -v docker 2>/dev/null || ls /usr/bin/docker /usr/local/bin/docker 2>/dev/null | head -1 || true)
if [ -z "$DOCKER_BIN" ]; then
  p "${RED}✗ Docker nicht gefunden. Bitte zuerst Docker installieren."
  p "  https://docs.docker.com/get-docker/"
  exit 1
fi
p "${GREEN}✓ Docker gefunden"

if docker compose version &>/dev/null 2>&1; then DC="docker compose"
elif docker-compose version &>/dev/null 2>&1; then DC="docker-compose"
else
  p "${RED}✗ 'docker compose' nicht gefunden."
  p "  sudo apt-get install docker-compose-plugin"
  exit 1
fi
p "${GREEN}✓ $DC"

# ── 2. Alte Container stoppen ───────────────────────────────────
ph "[1/4] Alte Container aufräumen ..."
for name in dtv-verwaltung dtv-app dtv-nginx; do
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${name}$"; then
    docker rm -f "$name" &>/dev/null && p "  → $name gestoppt"
  fi
done
p "${GREEN}✓ Fertig"

# ── 3. .env anlegen ─────────────────────────────────────────────
ph "[2/4] Konfiguration (.env) ..."
if [ ! -f .env ]; then
  cp .env.example .env
  p "  → .env aus .env.example erstellt"
fi

# Admin-Passwort prüfen / setzen
CURRENT_PW=$(grep "^ADMIN_PASSWORD=" .env | cut -d= -f2-)
if [ -z "$CURRENT_PW" ] || [ "$CURRENT_PW" = "BitteSichersErsetzt!" ]; then
  p ""
  p "${YELLOW}⚠ Bitte ein sicheres Admin-Passwort eingeben:"
  printf "  Admin-Passwort: "
  read -rs ADMIN_PW; printf "\n"
  if [ -z "$ADMIN_PW" ]; then
    ADMIN_PW="Admin$(shuf -i 1000-9999 -n1 2>/dev/null || echo $RANDOM)"
    p "  ${YELLOW}Kein Passwort eingegeben – temporär: ${BOLD}$ADMIN_PW"
    p "  ${YELLOW}Bitte nach dem Login sofort unter Admin ändern!"
  fi
  sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PW}|" .env
fi

# DB-Schlüssel generieren falls leer
CURRENT_KEY=$(grep "^DB_KEY=" .env 2>/dev/null | cut -d= -f2-)
if [ -z "$CURRENT_KEY" ]; then
  DB_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null \
           || openssl rand -hex 32)
  if grep -q "^DB_KEY=" .env; then
    sed -i "s|^DB_KEY=.*|DB_KEY=${DB_KEY}|" .env
  else
    printf "DB_KEY=%s\n" "$DB_KEY" >> .env
  fi
  p ""
  p "${YELLOW}  ╔══════════════════════════════════════════════════════════╗"
  p "${YELLOW}  ║  WICHTIG: DB_KEY jetzt sicher aufbewahren!              ║"
  p "${YELLOW}  ║  Ohne diesen Schlüssel sind die Daten nicht              ║"
  p "${YELLOW}  ║  wiederherstellbar (z.B. in Passwortmanager speichern).  ║"
  p "${YELLOW}  ╚══════════════════════════════════════════════════════════╝"
  p ""
  p "  DB_KEY=${DB_KEY}"
  p ""
fi
p "${GREEN}✓ Konfiguration OK"

# ── 4. Docker Image bauen & starten ────────────────────────────
ph "[3/4] Docker Image bauen (beim ersten Mal ~3–5 Minuten) ..."
$DC up -d --build
p "${GREEN}✓ Container gestartet"

# ── 5. Warten bis App bereit ────────────────────────────────────
ph "[4/4] Warte auf App-Start ..."
for i in $(seq 1 30); do
  if docker exec dtv-verwaltung python3 -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" \
    &>/dev/null 2>&1; then
    break
  fi
  printf "."; sleep 2
done
printf "\n"

# ── Fertig ──────────────────────────────────────────────────────
PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d= -f2-)
PORT=${PORT:-8123}
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

p ""
p "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗"
p "${GREEN}${BOLD}║  ✓ DT-Verwaltung erfolgreich installiert!            ║"
p "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝"
p ""
p "  🌐 Browser: ${BOLD}http://${SERVER_IP}:${PORT}"
p "  🌐 Lokal:   ${BOLD}http://localhost:${PORT}"
p ""
p "  📋 Logs: ${BOLD}docker logs dtv-verwaltung -f"
p "  🛑 Stop: ${BOLD}$DC down"
p ""
