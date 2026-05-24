#!/usr/bin/env bash
# setup-db.sh — Create the Keycloak Postgres role + database.
#
# Usage:  KEYCLOAK_DB_PASSWORD=... bash setup-db.sh <sudo_password>
#
# Idempotent: skips role/db creation when already present, refreshes the
# password on every run so .env is the single source of truth.

set -euo pipefail

SPASS="${1:?sudo password required as arg 1}"
DB_USER="${KEYCLOAK_DB_USER:-keycloak_user}"
DB_NAME="${KEYCLOAK_DB:-keycloak_db}"
DB_PASS="${KEYCLOAK_DB_PASSWORD:?Set KEYCLOAK_DB_PASSWORD before running this script}"

psql_su() { echo "$SPASS" | sudo -S -u postgres psql "$@"; }

echo "==> Setting up $DB_NAME..."
if [ "$(psql_su -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null)" != "1" ]; then
    psql_su -c "CREATE DATABASE $DB_NAME"
    echo "  $DB_NAME created"
else
    echo "  $DB_NAME already exists"
fi

if [ "$(psql_su -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null)" != "1" ]; then
    psql_su -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS'"
    echo "  $DB_USER created"
else
    psql_su -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS'"
    echo "  $DB_USER password refreshed"
fi

psql_su -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER"
psql_su -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER"
echo "==> DB setup complete"
