#!/bin/sh
if [ -z "$BASH_VERSION" ]; then exec bash "$0" "$@"; fi
# ══════════════════════════════════════════════════
#  DT-Verwaltung – Update (Daten bleiben erhalten)
# ══════════════════════════════════════════════════
set -e
BOLD='\033[1m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
p() { printf "${1}${NC}\n"; }

p "\n${BOLD}DT-Verwaltung – Update\nDatenbank und Konfiguration bleiben erhalten.\n"

if [ ! -f .env ]; then
  p "${RED}✗ Keine .env – bitte zuerst install.sh ausführen."; exit 1
fi

if docker compose version &>/dev/null 2>&1; then DC="docker compose"
elif docker-compose version &>/dev/null 2>&1; then DC="docker-compose"
else p "${RED}✗ docker compose nicht gefunden."; exit 1; fi

p "${BOLD}[1/2] Baue neues Image ..."
$DC build --no-cache
p "${BOLD}[2/2] Starte Container neu ..."
$DC up -d

PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d= -f2-); PORT=${PORT:-8123}
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
p "\n${GREEN}✓ Update abgeschlossen!"
p "  🌐 http://${SERVER_IP}:${PORT}\n"
