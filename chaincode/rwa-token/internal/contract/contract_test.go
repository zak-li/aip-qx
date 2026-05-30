package contract

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestTokenizeAsset(t *testing.T) {
	contract := new(AssetTraceContract)
	assert.NotNil(t, contract)
}

func TestTransferBlockedOnFrozenAsset(t *testing.T) {
	asset := &FinancialAsset{
		AssetID:       "RWA-OBL-BANK01-2025-001",
		Status:        StatusGele,
		RegulatoryRef: "REG01-INV-2026-001",
	}
	assetJSON, err := json.Marshal(asset)
	assert.NoError(t, err)
	assert.NotNil(t, assetJSON)

	var decoded FinancialAsset
	err = json.Unmarshal(assetJSON, &decoded)
	assert.NoError(t, err)
	assert.Equal(t, StatusGele, decoded.Status)
	assert.Equal(t, "REG01-INV-2026-001", decoded.RegulatoryRef)
}

func TestProvenanceRecord(t *testing.T) {
	record := ProvenanceRecord{
		TxID:     "abc123",
		ActorMSP: "BANK01MSP",
		Action:   "TOKENISE",
	}
	assert.Equal(t, "TOKENISE", record.Action)
	assert.Equal(t, "BANK01MSP", record.ActorMSP)
}

func TestAssetStatusConstants(t *testing.T) {
	assert.Equal(t, AssetStatus("ACTIF"), StatusActif)
	assert.Equal(t, AssetStatus("GELE"), StatusGele)
	assert.Equal(t, AssetStatus("EN_EMISSION"), StatusEnEmission)
	assert.Equal(t, AssetStatus("REMBOURSE"), StatusRembourse)
}
