#!/bin/bash
set -e

export FABRIC_CFG_PATH=~/go/src/github.com/hyperledger/fabric-samples/config
export ORDERER_CA=~/rwa-platform/crypto-config/ordererOrganizations/finance-trust.com/orderers/orderer.finance-trust.com/tls/ca.crt

source ~/.bashrc

bnp
peer lifecycle chaincode install ~/rwa-platform/rwa-token-ccaas.tar.gz

amf
peer lifecycle chaincode install ~/rwa-platform/rwa-token-ccaas.tar.gz

sleep 5

bnp
export PKG_ID=$(peer lifecycle chaincode queryinstalled \
  | grep "rwa-token_1.0" | awk '{print $3}' | tr -d ',')
echo "PKG_ID = $PKG_ID"

bnp
peer lifecycle chaincode approveformyorg \
  -o orderer.finance-trust.com:7050 --tls --cafile $ORDERER_CA \
  --channelID rwa-channel --name rwa-token \
  --version 1.2 --package-id $PKG_ID --sequence 1

sleep 3

amf
peer lifecycle chaincode approveformyorg \
  -o orderer.finance-trust.com:7050 --tls --cafile $ORDERER_CA \
  --channelID rwa-channel --name rwa-token \
  --version 1.2 --package-id $PKG_ID --sequence 1

sleep 3

bnp
peer lifecycle chaincode checkcommitreadiness \
  --channelID rwa-channel --name rwa-token \
  --version 1.2 --sequence 1 --output json

peer lifecycle chaincode commit \
  -o orderer.finance-trust.com:7050 --tls --cafile $ORDERER_CA \
  --channelID rwa-channel --name rwa-token \
  --version 1.2 --sequence 1 \
  --peerAddresses peer0.bnpparibas.finance-trust.com:7051 \
  --tlsRootCertFiles ~/rwa-platform/crypto-config/peerOrganizations/bnpparibas.finance-trust.com/peers/peer0.bnpparibas.finance-trust.com/tls/ca.crt \
  --peerAddresses peer0.amf-regulateur.finance-trust.com:7091 \
  --tlsRootCertFiles ~/rwa-platform/crypto-config/peerOrganizations/amf-regulateur.finance-trust.com/peers/peer0.amf-regulateur.finance-trust.com/tls/ca.crt

echo "Chaincode rwa-token déployé sur rwa-channel."
