#!/bin/bash
set -e

cd "$(dirname "$0")/.."

docker compose -f docker/docker-compose.yaml down -v
docker volume prune -f
echo "Réseau arrêté et volumes supprimés."
