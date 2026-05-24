#!/usr/bin/env bash
# test-pg-conn.sh — Smoke-test the Keycloak container's connectivity to Postgres.
#
# Usage:  KEYCLOAK_DB_PASSWORD=... bash test-pg-conn.sh [sudo_password]
#
# Reads credentials from env so nothing sensitive lands in git.

set -euo pipefail

DB_USER="${KEYCLOAK_DB_USER:-keycloak_user}"
DB_NAME="${KEYCLOAK_DB:-keycloak_db}"
DB_HOST="${KEYCLOAK_DB_HOST:-10.10.10.150}"
DB_PASS="${KEYCLOAK_DB_PASSWORD:?Set KEYCLOAK_DB_PASSWORD before running}"

echo "=== TCP connectivity to ${DB_HOST}:5432 from Keycloak container ==="
docker exec rwa-keycloak bash -c \
    "timeout 5 bash -c 'cat /dev/null > /dev/tcp/${DB_HOST}/5432' && echo 'TCP OK' || echo 'TCP FAILED'"

echo "=== JDBC from container (psql if present) ==="
docker exec rwa-keycloak bash -c \
    "which psql 2>/dev/null && PGPASSWORD='${DB_PASS}' psql -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} -c 'SELECT 1' 2>&1 || echo 'psql not in container'"

echo "=== ufw status ==="
if [ "${1:-}" ]; then
    echo "$1" | sudo -S ufw status 2>/dev/null || echo "ufw not active"
else
    echo "(skip — pass sudo password as arg 1 to check ufw)"
fi
