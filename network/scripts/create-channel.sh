#!/bin/bash
set -e

export FABRIC_CFG_PATH=~/rwa-platform/config
export ORDERER_CA=~/rwa-platform/crypto-config/ordererOrganizations/finance-trust.com/orderers/orderer.finance-trust.com/tls/ca.crt

cd ~/rwa-platform

cryptogen generate --config=./config/crypto-config.yaml --output=./crypto-config

configtxgen -profile RWAGenesis -channelID rwa-channel \
  -outputBlock ./channel-artifacts/genesis.block

export FABRIC_CFG_PATH=~/go/src/github.com/hyperledger/fabric-samples/config

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

echo "Channel rwa-channel créé et joints par les deux peers."
