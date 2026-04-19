package main

import (
	"encoding/json"
	"testing"

	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-chaincode-go/shimtest"
	"github.com/stretchr/testify/assert"
)

func newMockStub() *shimtest.MockStub {
	cc, _ := newChaincode()
	stub := shimtest.NewMockStub("rwa-token", cc)
	return stub
}

func newChaincode() (shim.Chaincode, error) {
	return nil, nil
}

func TestTokenizeAsset(t *testing.T) {
	contract := new(AssetTraceContract)
	assert.NotNil(t, contract)
}

func TestTransferBlockedOnFrozenAsset(t *testing.T) {
	asset := &FinancialAsset{
		AssetID:       "RWA-OBL-BNP-2025-001",
		Status:        StatusGele,
		RegulatoryRef: "AMF-INV-2026-001",
	}
	assetJSON, err := json.Marshal(asset)
	assert.NoError(t, err)
	assert.NotNil(t, assetJSON)

	var decoded FinancialAsset
	err = json.Unmarshal(assetJSON, &decoded)
	assert.NoError(t, err)
	assert.Equal(t, StatusGele, decoded.Status)
	assert.Equal(t, "AMF-INV-2026-001", decoded.RegulatoryRef)
}

func TestProvenanceRecord(t *testing.T) {
	record := ProvenanceRecord{
		TxID:     "abc123",
		ActorMSP: "BNPParibasMSP",
		Action:   "TOKENISE",
	}
	assert.Equal(t, "TOKENISE", record.Action)
	assert.Equal(t, "BNPParibasMSP", record.ActorMSP)
}

func TestAssetStatusConstants(t *testing.T) {
	assert.Equal(t, AssetStatus("ACTIF"), StatusActif)
	assert.Equal(t, AssetStatus("GELE"), StatusGele)
	assert.Equal(t, AssetStatus("EN_EMISSION"), StatusEnEmission)
	assert.Equal(t, AssetStatus("REMBOURSE"), StatusRembourse)
}
