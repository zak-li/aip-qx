#!/usr/bin/env bash
# fix-firewall.sh — Apply restrictive UFW rules for the RWA platform.
#
# Usage: bash fix-firewall.sh <sudo-password>
#
# Only Docker bridge traffic and the admin LAN (10.10.10.0/24) are allowed
# to reach internal services. Keycloak HTTPS (8443) is the only publicly
# exposed service port besides SSH.

SPASS="$1"
LAN="10.10.10.0/24"

echo "==> Resetting RWA-specific UFW rules..."

# Allow Docker containers to reach PostgreSQL and Redis
echo "$SPASS" | sudo -S ufw allow from 172.16.0.0/12 to any port 5432 comment "PostgreSQL from Docker"
echo "$SPASS" | sudo -S ufw allow from 172.16.0.0/12 to any port 6379 comment "Redis from Docker"

# Keycloak HTTPS only (HTTP 8080 is disabled in Keycloak config)
echo "$SPASS" | sudo -S ufw allow 8443/tcp comment "Keycloak HTTPS"

# API — restrict to LAN only (not public)
echo "$SPASS" | sudo -S ufw allow from "$LAN" to any port 8000 comment "RWA API (LAN only)"

# Fabric peers/orderer — LAN only
echo "$SPASS" | sudo -S ufw allow from "$LAN" to any port 7050 comment "Fabric Orderer (LAN)"
echo "$SPASS" | sudo -S ufw allow from "$LAN" to any port 7051 comment "Fabric Peer BANK01 (LAN)"
echo "$SPASS" | sudo -S ufw allow from "$LAN" to any port 7091 comment "Fabric Peer REG01 (LAN)"

# Monitoring — LAN only
echo "$SPASS" | sudo -S ufw allow from "$LAN" to any port 9090 comment "Prometheus (LAN)"
echo "$SPASS" | sudo -S ufw allow from "$LAN" to any port 3000 comment "Grafana (LAN)"

# Delete overly permissive rules if they exist
echo "$SPASS" | sudo -S ufw delete allow 8080/tcp 2>/dev/null || true
echo "$SPASS" | sudo -S ufw delete allow 9999/tcp 2>/dev/null || true

echo "$SPASS" | sudo -S ufw reload
echo "==> UFW rules updated"
echo "$SPASS" | sudo -S ufw status numbered | grep -E "8443|8000|7050|7051|7091|9090|3000|5432|6379"
