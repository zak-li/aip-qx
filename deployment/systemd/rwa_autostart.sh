#!/bin/bash
set -euo pipefail

LOG_TAG="RWA-PLATFORM"
COMPOSE_FILE="/home/zakaria/rwa-platform/docker/docker-compose.yaml"
ENV_FILE="/home/zakaria/rwa-platform/.env"

log()  { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] [${LOG_TAG}] $*" | tee -a /var/log/rwa/autostart.log; }
fail() { log "ERREUR: $*"; exit 1; }

wait_port() {
    local host="$1" port="$2" label="$3" max="${4:-45}"
    local n=0
    until nc -z "$host" "$port" 2>/dev/null; do
        sleep 1
        n=$((n + 1))
        [ "$n" -ge "$max" ] && fail "${label} (port ${port}) indisponible apres ${max}s"
    done
    log "${label}: UP en ${n}s"
}

mkdir -p /var/log/rwa
log "=== DEMARRAGE INFRASTRUCTURE RWA ==="

systemctl start postgresql 2>/dev/null || true
wait_port localhost 5432 "PostgreSQL" 30

systemctl start redis-server 2>/dev/null || true
wait_port localhost 6379 "Redis" 15

systemctl start vault 2>/dev/null || true
sleep 5
wait_port localhost 8200 "Vault" 30
systemctl start vault-unseal 2>/dev/null || true
sleep 3
log "Vault: PRET (unsealed)"

systemctl start docker 2>/dev/null || true
sleep 3

if [ -f "$COMPOSE_FILE" ]; then
    cd "$(dirname "$COMPOSE_FILE")"
    set -a
    source "$ENV_FILE"
    set +a
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
    sleep 8
    wait_port localhost 7050 "Fabric Orderer"  60
    wait_port localhost 7051 "Peer BNP"        45
    wait_port localhost 7091 "Peer AMF"        45
    wait_port localhost 9999 "Chaincode CCaaS" 30
    log "Hyperledger Fabric: PRET"
else
    fail "docker-compose introuvable: ${COMPOSE_FILE}"
fi

wait_port localhost 7687 "Neo4j"  60

for svc in prometheus grafana-server node_exporter; do
    systemctl start "$svc" 2>/dev/null && log "${svc}: demarre" || log "${svc}: ignore"
done

log "=== INFRASTRUCTURE PRETE ==="
