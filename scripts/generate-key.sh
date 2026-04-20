#!/bin/bash
# Generate a random 256-bit DB key for SQLCipher encryption
echo "[KEY] New DB_KEY (add to your .env file):"
echo ""
echo "DB_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
echo ""
echo "Then restart: docker compose up -d --build"
