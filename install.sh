#!/bin/sh
# Auto-switch to bash if called via sh
if [ -z "$BASH_VERSION" ]; then
  exec bash "$0" "$@"
fi
# ═══════════════════════════════════════════════════════════════
#  DT-Verwaltung – Installer
#  Usage:  bash install.sh  OR  sh install.sh
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

# ── 1. Check Docker ─────────────────────────────────────────────
DOCKER_BIN=$(command -v docker 2>/dev/null || ls /usr/bin/docker /usr/local/bin/docker 2>/dev/null | head -1 || true)
if [ -z "$DOCKER_BIN" ]; then
  p "${RED}✗ Docker not found. Please install Docker first."
  p "  https://docs.docker.com/get-docker/"
  exit 1
fi
p "${GREEN}✓ Docker found"

if docker compose version &>/dev/null 2>&1; then DC="docker compose"
elif docker-compose version &>/dev/null 2>&1; then DC="docker-compose"
else
  p "${RED}✗ 'docker compose' not found."
  p "  sudo apt-get install docker-compose-plugin"
  exit 1
fi
p "${GREEN}✓ $DC"

# ── 2. Stop old containers ──────────────────────────────────────
ph "[1/4] Cleaning up old containers ..."
for name in dtv-verwaltung dtv-app dtv-nginx; do
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${name}$"; then
    docker rm -f "$name" &>/dev/null && p "  → $name stopped"
  fi
done
p "${GREEN}✓ Done"

# ── 3. Create .env ──────────────────────────────────────────────
ph "[2/4] Configuration (.env) ..."
if [ ! -f .env ]; then
  cp .env.example .env
  p "  → .env created from .env.example"
fi

# Check / set admin password
CURRENT_PW=$(grep "^ADMIN_PASSWORD=" .env | cut -d= -f2-)
if [ -z "$CURRENT_PW" ] || [ "$CURRENT_PW" = "ChangeMe!" ]; then
  p ""
  p "${YELLOW}⚠ Please enter a secure admin password:"
  printf "  Admin password: "
  read -rs ADMIN_PW; printf "\n"
  if [ -z "$ADMIN_PW" ]; then
    ADMIN_PW="Admin$(shuf -i 1000-9999 -n1 2>/dev/null || echo $RANDOM)"
    p "  ${YELLOW}No password entered – temporary password: ${BOLD}$ADMIN_PW"
    p "  ${YELLOW}Please change it in the Admin panel immediately after login!"
  fi
  sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PW}|" .env
fi

# Generate DB key if empty (and DB_KEY line exists in .env)
CURRENT_KEY=$(grep "^DB_KEY=" .env 2>/dev/null | cut -d= -f2- || true)
if [ -n "$(grep "^#.*DB_KEY\|^DB_KEY=" .env 2>/dev/null)" ] && [ -z "$CURRENT_KEY" ]; then
  DB_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null \
           || openssl rand -hex 32)
  if grep -q "^DB_KEY=" .env; then
    sed -i "s|^DB_KEY=.*|DB_KEY=${DB_KEY}|" .env
  fi
  p ""
  p "${YELLOW}  ╔══════════════════════════════════════════════════════════╗"
  p "${YELLOW}  ║  IMPORTANT: Save this DB_KEY in a safe place!           ║"
  p "${YELLOW}  ║  Without it your data cannot be recovered.              ║"
  p "${YELLOW}  ║  (e.g. store it in your password manager)               ║"
  p "${YELLOW}  ╚══════════════════════════════════════════════════════════╝"
  p ""
  p "  DB_KEY=${DB_KEY}"
  p ""
fi
p "${GREEN}✓ Configuration OK"

# ── 4. Build & start Docker image ──────────────────────────────
ph "[3/4] Building Docker image (first time may take ~3–5 minutes) ..."
$DC up -d --build
p "${GREEN}✓ Container started"

# ── 5. Wait for app ready ───────────────────────────────────────
ph "[4/4] Waiting for app to be ready ..."
for i in $(seq 1 30); do
  if docker exec dtv-verwaltung python3 -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health')" \
    &>/dev/null 2>&1; then
    break
  fi
  printf "."; sleep 2
done
printf "\n"

# ── Done ────────────────────────────────────────────────────────
PORT=$(grep "^PORT=" .env 2>/dev/null | cut -d= -f2-)
PORT=${PORT:-8123}
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

p ""
p "${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗"
p "${GREEN}${BOLD}║  ✓ DT-Verwaltung installed successfully!             ║"
p "${GREEN}${BOLD}╚══════════════════════════════════════════════════════╝"
p ""
p "  🌐 Network: ${BOLD}http://${SERVER_IP}:${PORT}"
p "  🌐 Local:   ${BOLD}http://localhost:${PORT}"
p ""
p "  📋 Logs: ${BOLD}docker logs dtv-verwaltung -f"
p "  🛑 Stop: ${BOLD}$DC down"
p ""
