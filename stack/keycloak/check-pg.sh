#!/usr/bin/env bash
SPASS="$1"

echo "=== PostgreSQL listen address ==="
echo "$SPASS" | sudo -S -u postgres psql -c "SHOW listen_addresses" 2>/dev/null

echo "=== pg_hba.conf ==="
PG_CONF=$(echo "$SPASS" | sudo -S find /etc/postgresql /var/lib/postgresql /var/lib/pgsql \
  -name pg_hba.conf 2>/dev/null | head -1)
echo "pg_hba.conf at: $PG_CONF"
echo "$SPASS" | sudo -S cat "$PG_CONF" 2>/dev/null | grep -v "^#" | grep -v "^$"

echo "=== Docker bridge gateway ==="
docker network inspect bridge --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'

echo "=== Keycloak container IP ==="
docker inspect qx-keycloak --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
