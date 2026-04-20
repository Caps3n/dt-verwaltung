#!/bin/sh
if [ -z "$BASH_VERSION" ]; then exec bash "$0" "$@"; fi
# ══════════════════════════════════════════════════
#  DT-Verwaltung – Update (data and config preserved)
# ══════════════════════════════════════════════════
set -e
BOLD='\033[1m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
p() { printf "${1}${NC}\n"; }

p "\n${BOLD}DT-Verwaltung – Update\nDatabase and configuration are preserved.\n"

if [ ! -f .env ]; then
  p "${RED}✗ No .env found – please run install.sh first."; exit 1
fi

if docker compose version &>/dev/null 2>&1; then DC="docker compose"
elif docker-compose version &>/dev/null 2>&1; then DC="docker-compose"
else p "${RED}✗ docker compose not found."; exit 1; fi

p "${BOLD}[1/2] Building new image ..."
$DC build --no-cache
p "${BOLD}[2/2] Restarting container ..."
$DC up -d

PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d= -f2-); PORT=${PORT:-8123}
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
p "\n${GREEN}✓ Update complete!"
p "  🌐 http://${SERVER_IP}:${PORT}\n"
