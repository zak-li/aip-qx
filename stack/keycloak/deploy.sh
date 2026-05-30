#!/usr/bin/env bash
# deploy.sh — Bootstrap Keycloak on the RWA platform server (10.10.10.150).
# Run once from a machine that can SSH to the server.
#
#   Usage:  bash deploy.sh

set -euo pipefail

REMOTE_USER="zakaria"
REMOTE_HOST="10.10.10.150"
REMOTE_DIR="/opt/rwa/keycloak"
COMPOSE_FILE="docker-compose.keycloak.yml"

echo "==> Copying deployment files to ${REMOTE_HOST}:${REMOTE_DIR}"
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}/tls"
scp "${COMPOSE_FILE}" ".env.keycloak"          "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"
scp tls/tls.crt tls/tls.key                    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/tls/"
scp setup-realm.py requirements-setup.txt       "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo "==> Creating keycloak_db on the PostgreSQL server"
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash << 'ENDSSH'
  set -euo pipefail
  source /opt/rwa/keycloak/.env.keycloak

  # Database credentials are read from the main project .env to avoid duplication.
  # Ensure DATABASE_URL is set in /home/zakaria/rwa-platform/.env
  DB_CONN=$(grep "^DATABASE_URL=" /home/zakaria/rwa-platform/.env | sed 's|postgresql+asyncpg://||' | sed 's|/[^/]*$||')
  DB_USER=$(echo "$DB_CONN" | cut -d: -f1)
  DB_PASS=$(echo "$DB_CONN" | cut -d: -f2 | cut -d@ -f1)
  DB_HOST=$(echo "$DB_CONN" | cut -d@ -f2 | cut -d: -f1)
  DB_PORT=$(echo "$DB_CONN" | cut -d: -f3)

  PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d rwadb \
    -c "SELECT 1 FROM pg_database WHERE datname='keycloak_db'" | grep -q 1 \
  || PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d rwadb \
       -c "CREATE DATABASE keycloak_db;"

  PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d rwadb \
    -c "SELECT 1 FROM pg_roles WHERE rolname='${KEYCLOAK_DB_USER}'" | grep -q 1 \
  || PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d rwadb \
       -c "CREATE USER ${KEYCLOAK_DB_USER} WITH PASSWORD '${KEYCLOAK_DB_PASSWORD}';
           GRANT ALL PRIVILEGES ON DATABASE keycloak_db TO ${KEYCLOAK_DB_USER};"
ENDSSH

echo "==> Starting Keycloak container"
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash << 'ENDSSH'
  set -euo pipefail
  cd /opt/rwa/keycloak
  docker compose --env-file .env.keycloak -f docker-compose.keycloak.yml up -d --wait
  echo "Keycloak started. Waiting for health check..."
  for i in $(seq 1 20); do
    # Keycloak runs HTTPS-only (port 8443); HTTP 8080 is disabled.
    if curl -fso /dev/null --insecure https://localhost:8443/health/ready; then
      echo "Keycloak is healthy!"
      break
    fi
    echo "  ... attempt $i/20"
    sleep 5
  done
ENDSSH

echo "==> Configuring realm, client, and roles via Admin API"
ssh "${REMOTE_USER}@${REMOTE_HOST}" bash << 'ENDSSH'
  set -euo pipefail
  cd /opt/rwa/keycloak
  source .env.keycloak
  pip3 install -q -r requirements-setup.txt
  python3 setup-realm.py \
    --keycloak-url "https://localhost:8443" \
    --admin-user  "${KEYCLOAK_ADMIN_USER}" \
    --admin-pass  "${KEYCLOAK_ADMIN_PASSWORD}"
ENDSSH

echo ""
echo "==> Keycloak deployed and configured successfully!"
echo "    Admin UI: https://10.10.10.150:8443/admin"
echo "    HTTPS:    https://10.10.10.150:8443"
