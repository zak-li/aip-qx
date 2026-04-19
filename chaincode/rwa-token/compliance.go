package main

import (
	"fmt"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

func RequireActiveAsset(asset *FinancialAsset) error {
	if asset.Status != StatusActif {
		return fmt.Errorf(
			"actif %s non disponible: statut=%s (réf réglementaire: %s)",
			asset.AssetID, asset.Status, asset.RegulatoryRef,
		)
	}
	return nil
}

func RequireFrozenAsset(asset *FinancialAsset) error {
	if asset.Status != StatusGele {
		return fmt.Errorf("actif %s n'est pas gelé (statut actuel: %s)", asset.AssetID, asset.Status)
	}
	return nil
}

func ValidateISIN(isin string) error {
	if len(isin) != 12 {
		return fmt.Errorf("ISIN invalide: longueur attendue 12, reçu %d", len(isin))
	}
	for i, ch := range isin {
		if i < 2 {
			if ch < 'A' || ch > 'Z' {
				return fmt.Errorf("ISIN invalide: les 2 premiers caractères doivent être des lettres majuscules")
			}
		} else {
			if !((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9')) {
				return fmt.Errorf("ISIN invalide: caractère '%c' illégal en position %d", ch, i)
			}
		}
	}
	return nil
}

func ValidateLEI(lei string) error {
	if len(lei) != 20 {
		return fmt.Errorf("LEI invalide: longueur attendue 20, reçu %d", len(lei))
	}
	for i, ch := range lei {
		if !((ch >= 'A' && ch <= 'Z') || (ch >= '0' && ch <= '9')) {
			return fmt.Errorf("LEI invalide: caractère '%c' illégal en position %d", ch, i)
		}
	}
	return nil
}

func ValidateRegulatoryRef(ref string) error {
	if len(ref) < 8 || len(ref) > 50 {
		return fmt.Errorf("référence réglementaire invalide: longueur hors limites (%d)", len(ref))
	}
	return nil
}

func CheckMiCAThreshold(
	ctx contractapi.TransactionContextInterface,
	amount float64,
	assetID string,
) error {
	const micaThreshold = 1000.0

	if amount > micaThreshold {
		txID := ctx.GetStub().GetTxID()
		eventPayload := fmt.Sprintf(
			`{"event":"MICA_ART68_TRIGGERED","txID":"%s","assetID":"%s","amount":%f}`,
			txID, assetID, amount,
		)
		if err := ctx.GetStub().SetEvent("MiCAThresholdExceeded", []byte(eventPayload)); err != nil {
			return fmt.Errorf("CheckMiCAThreshold: émission événement: %w", err)
		}
	}
	return nil
}
