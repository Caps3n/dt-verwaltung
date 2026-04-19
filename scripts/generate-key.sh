#!/bin/bash
# Zufälligen 256-bit DB-Schlüssel für SQLCipher generieren
echo "[KEY] Neuer DB_KEY (in .env eintragen):"
echo ""
echo "DB_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
echo ""
echo "Danach: docker compose up -d --build"
