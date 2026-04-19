#!/bin/bash
set -e

cd "$(dirname "$0")/.."

export FABRIC_CFG_PATH=~/go/src/github.com/hyperledger/fabric-samples/config
export ORDERER_CA=~/rwa-platform/crypto-config/ordererOrganizations/finance-trust.com/orderers/orderer.finance-trust.com/tls/ca.crt

docker compose -f docker/docker-compose.yaml up -d
sleep 15

source ~/.bashrc

bnp
peer channel join -b ~/rwa-platform/channel-artifacts/genesis.block \
  -o orderer.finance-trust.com:7050 --tls --cafile $ORDERER_CA

amf
peer channel join -b ~/rwa-platform/channel-artifacts/genesis.block \
  -o orderer.finance-trust.com:7050 --tls --cafile $ORDERER_CA

osnadmin channel join \
  --channelID rwa-channel \
  --config-block ~/rwa-platform/channel-artifacts/genesis.block \
  -o orderer.finance-trust.com:7053

sleep 10
echo "Réseau rwa-channel actif."
docker ps --format "table {{.Names}}\t{{.Status}}"
