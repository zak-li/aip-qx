package main

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type AssetTraceContract struct {
	contractapi.Contract
}

func getTxTimestamp(ctx contractapi.TransactionContextInterface) (time.Time, error) {
	ts, err := ctx.GetStub().GetTxTimestamp()
	if err != nil {
		return time.Time{}, fmt.Errorf("getTxTimestamp: %w", err)
	}
	return ts.AsTime(), nil
}

func (c *AssetTraceContract) TokenizeAsset(ctx contractapi.TransactionContextInterface,
	assetID, isin, assetType, assetName, issuerLEI string,
	nominalValue float64, currency, issuanceDate, justification string) error {

	if err := verifyRole(ctx, "TokenizeAsset"); err != nil {
		return err
	}
	if err := ValidateISIN(isin); err != nil {
		return fmt.Errorf("TokenizeAsset: %w", err)
	}
	if err := ValidateLEI(issuerLEI); err != nil {
		return fmt.Errorf("TokenizeAsset: %w", err)
	}
	if nominalValue <= 0 {
		return fmt.Errorf("TokenizeAsset: valeur nominale doit être positive, reçu %f", nominalValue)
	}

	exists, err := c.assetExists(ctx, assetID)
	if err != nil {
		return fmt.Errorf("TokenizeAsset: vérification existence: %w", err)
	}
	if exists {
		return fmt.Errorf("l'actif %s existe déjà sur le ledger", assetID)
	}

	msp, err := getClientMSP(ctx)
	if err != nil {
		return fmt.Errorf("TokenizeAsset: %w", err)
	}
	dn, err := getClientDN(ctx)
	if err != nil {
		return fmt.Errorf("TokenizeAsset: %w", err)
	}
	txID := ctx.GetStub().GetTxID()
	ts, err := getTxTimestamp(ctx)
	if err != nil {
		return fmt.Errorf("TokenizeAsset: %w", err)
	}

	record := ProvenanceRecord{
		TxID:          txID,
		Timestamp:     ts,
		ActorMSP:      msp,
		ActorDN:       dn,
		Action:        "TOKENISE",
		ToOwner:       dn,
		Amount:        nominalValue,
		Justification: justification,
	}

	asset := FinancialAsset{
		AssetID:      assetID,
		ISIN:         isin,
		AssetType:    AssetType(assetType),
		AssetName:    assetName,
		IssuerMSP:    msp,
		IssuerLEI:    issuerLEI,
		CurrentOwner: dn,
		NominalValue: nominalValue,
		CurrentValue: nominalValue,
		Currency:     currency,
		Status:       StatusActif,
		IssuanceDate: issuanceDate,
		Provenance:   []ProvenanceRecord{record},
	}

	assetJSON, err := json.Marshal(asset)
	if err != nil {
		return fmt.Errorf("TokenizeAsset: sérialisation JSON: %w", err)
	}
	if err := ctx.GetStub().PutState(assetID, assetJSON); err != nil {
		return fmt.Errorf("TokenizeAsset: écriture ledger: %w", err)
	}
	if err := ctx.GetStub().SetEvent("AssetCreated", assetJSON); err != nil {
		return fmt.Errorf("TokenizeAsset: émission événement: %w", err)
	}
	return nil
}

func (c *AssetTraceContract) TransferAsset(ctx contractapi.TransactionContextInterface,
	assetID, toOwner, justification string, price float64) error {

	if err := verifyRole(ctx, "TransferAsset"); err != nil {
		return err
	}
	if price <= 0 {
		return fmt.Errorf("TransferAsset: prix doit être positif, reçu %f", price)
	}

	asset, err := c.getAsset(ctx, assetID)
	if err != nil {
		return fmt.Errorf("TransferAsset: %w", err)
	}
	if err := RequireActiveAsset(asset); err != nil {
		return fmt.Errorf("TransferAsset: %w", err)
	}
	if err := CheckMiCAThreshold(ctx, price, assetID); err != nil {
		return fmt.Errorf("TransferAsset: %w", err)
	}

	msp, err := getClientMSP(ctx)
	if err != nil {
		return fmt.Errorf("TransferAsset: %w", err)
	}
	dn, err := getClientDN(ctx)
	if err != nil {
		return fmt.Errorf("TransferAsset: %w", err)
	}
	ts, err := getTxTimestamp(ctx)
	if err != nil {
		return fmt.Errorf("TransferAsset: %w", err)
	}

	record := ProvenanceRecord{
		TxID:          ctx.GetStub().GetTxID(),
		Timestamp:     ts,
		ActorMSP:      msp,
		ActorDN:       dn,
		Action:        "TRANSFERE",
		FromOwner:     asset.CurrentOwner,
		ToOwner:       toOwner,
		Amount:        price,
		Justification: justification,
	}

	asset.Provenance = append(asset.Provenance, record)
	asset.CurrentOwner = toOwner
	asset.CurrentValue = price
	asset.TotalTransfers++

	assetJSON, err := json.Marshal(asset)
	if err != nil {
		return fmt.Errorf("TransferAsset: sérialisation JSON: %w", err)
	}
	if err := ctx.GetStub().PutState(assetID, assetJSON); err != nil {
		return fmt.Errorf("TransferAsset: écriture ledger: %w", err)
	}
	if err := ctx.GetStub().SetEvent("AssetTransferred", assetJSON); err != nil {
		return fmt.Errorf("TransferAsset: émission événement: %w", err)
	}
	return nil
}

func (c *AssetTraceContract) FreezeAsset(ctx contractapi.TransactionContextInterface,
	assetID, reason, regulatoryRef string) error {

	if err := verifyRole(ctx, "FreezeAsset"); err != nil {
		return err
	}
	if err := ValidateRegulatoryRef(regulatoryRef); err != nil {
		return fmt.Errorf("FreezeAsset: %w", err)
	}

	asset, err := c.getAsset(ctx, assetID)
	if err != nil {
		return fmt.Errorf("FreezeAsset: %w", err)
	}
	if asset.Status == StatusGele {
		return fmt.Errorf("actif %s déjà gelé", assetID)
	}

	msp, err := getClientMSP(ctx)
	if err != nil {
		return fmt.Errorf("FreezeAsset: %w", err)
	}
	dn, err := getClientDN(ctx)
	if err != nil {
		return fmt.Errorf("FreezeAsset: %w", err)
	}
	ts, err := getTxTimestamp(ctx)
	if err != nil {
		return fmt.Errorf("FreezeAsset: %w", err)
	}

	record := ProvenanceRecord{
		TxID:          ctx.GetStub().GetTxID(),
		Timestamp:     ts,
		ActorMSP:      msp,
		ActorDN:       dn,
		Action:        "GELE",
		Justification: reason,
	}

	asset.Status = StatusGele
	asset.FrozenBy = dn
	asset.FrozenAt = ts.Format(time.RFC3339)
	asset.FrozenReason = reason
	asset.RegulatoryRef = regulatoryRef
	asset.Provenance = append(asset.Provenance, record)

	assetJSON, err := json.Marshal(asset)
	if err != nil {
		return fmt.Errorf("FreezeAsset: sérialisation JSON: %w", err)
	}
	if err := ctx.GetStub().PutState(assetID, assetJSON); err != nil {
		return fmt.Errorf("FreezeAsset: écriture ledger: %w", err)
	}
	if err := ctx.GetStub().SetEvent("AssetFrozen", assetJSON); err != nil {
		return fmt.Errorf("FreezeAsset: émission événement: %w", err)
	}
	return nil
}

func (c *AssetTraceContract) UnfreezeAsset(ctx contractapi.TransactionContextInterface,
	assetID, justification string) error {

	if err := verifyRole(ctx, "UnfreezeAsset"); err != nil {
		return err
	}

	asset, err := c.getAsset(ctx, assetID)
	if err != nil {
		return fmt.Errorf("UnfreezeAsset: %w", err)
	}
	if err := RequireFrozenAsset(asset); err != nil {
		return fmt.Errorf("UnfreezeAsset: %w", err)
	}

	msp, err := getClientMSP(ctx)
	if err != nil {
		return fmt.Errorf("UnfreezeAsset: %w", err)
	}
	dn, err := getClientDN(ctx)
	if err != nil {
		return fmt.Errorf("UnfreezeAsset: %w", err)
	}
	ts, err := getTxTimestamp(ctx)
	if err != nil {
		return fmt.Errorf("UnfreezeAsset: %w", err)
	}

	record := ProvenanceRecord{
		TxID:          ctx.GetStub().GetTxID(),
		Timestamp:     ts,
		ActorMSP:      msp,
		ActorDN:       dn,
		Action:        "DEGELE",
		Justification: justification,
	}

	asset.Status = StatusActif
	asset.FrozenBy = ""
	asset.FrozenAt = ""
	asset.FrozenReason = ""
	asset.Provenance = append(asset.Provenance, record)

	assetJSON, err := json.Marshal(asset)
	if err != nil {
		return fmt.Errorf("UnfreezeAsset: sérialisation JSON: %w", err)
	}
	if err := ctx.GetStub().SetEvent("AssetUnfrozen", assetJSON); err != nil {
		return fmt.Errorf("UnfreezeAsset: émission événement: %w", err)
	}
	return ctx.GetStub().PutState(assetID, assetJSON)
}

func (c *AssetTraceContract) GetAsset(ctx contractapi.TransactionContextInterface,
	assetID string) (*FinancialAsset, error) {
	return c.getAsset(ctx, assetID)
}

func (c *AssetTraceContract) GetAssetHistory(ctx contractapi.TransactionContextInterface,
	assetID string) ([]map[string]interface{}, error) {

	iterator, err := ctx.GetStub().GetHistoryForKey(assetID)
	if err != nil {
		return nil, fmt.Errorf("GetAssetHistory: accès historique: %w", err)
	}
	defer iterator.Close()

	var history []map[string]interface{}
	for iterator.HasNext() {
		entry, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("GetAssetHistory: itération: %w", err)
		}
		record := map[string]interface{}{
			"txId":     entry.TxId,
			"isDelete": entry.IsDelete,
			"value":    string(entry.Value),
		}
		history = append(history, record)
	}
	return history, nil
}

func (c *AssetTraceContract) GetProvenanceTrail(ctx contractapi.TransactionContextInterface,
	assetID string) ([]ProvenanceRecord, error) {
	asset, err := c.getAsset(ctx, assetID)
	if err != nil {
		return nil, fmt.Errorf("GetProvenanceTrail: %w", err)
	}
	return asset.Provenance, nil
}

func (c *AssetTraceContract) QueryAssets(ctx contractapi.TransactionContextInterface,
	queryString string) ([]*FinancialAsset, error) {

	iterator, err := ctx.GetStub().GetQueryResult(queryString)
	if err != nil {
		return nil, fmt.Errorf("QueryAssets: exécution requête: %w", err)
	}
	defer iterator.Close()

	var assets []*FinancialAsset
	for iterator.HasNext() {
		result, err := iterator.Next()
		if err != nil {
			return nil, fmt.Errorf("QueryAssets: itération: %w", err)
		}
		var asset FinancialAsset
		if err := json.Unmarshal(result.Value, &asset); err != nil {
			return nil, fmt.Errorf("QueryAssets: désérialisation: %w", err)
		}
		assets = append(assets, &asset)
	}
	return assets, nil
}

func (c *AssetTraceContract) getAsset(ctx contractapi.TransactionContextInterface,
	assetID string) (*FinancialAsset, error) {
	assetJSON, err := ctx.GetStub().GetState(assetID)
	if err != nil {
		return nil, fmt.Errorf("getAsset: lecture ledger: %w", err)
	}
	if assetJSON == nil {
		return nil, fmt.Errorf("actif %s introuvable sur le ledger", assetID)
	}
	var asset FinancialAsset
	if err := json.Unmarshal(assetJSON, &asset); err != nil {
		return nil, fmt.Errorf("getAsset: désérialisation: %w", err)
	}
	return &asset, nil
}

func (c *AssetTraceContract) assetExists(ctx contractapi.TransactionContextInterface,
	assetID string) (bool, error) {
	assetJSON, err := ctx.GetStub().GetState(assetID)
	if err != nil {
		return false, fmt.Errorf("assetExists: lecture ledger: %w", err)
	}
	return assetJSON != nil, nil
}
