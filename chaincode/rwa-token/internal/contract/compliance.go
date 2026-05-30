package contract

import (
	"fmt"
	"regexp"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// AssetID convention: RWA-<COUNTRY 2-12>-<TYPE 2-6>-<YEAR 4 digits>-<SERIAL 3 digits>
var assetIDPattern = regexp.MustCompile(`^RWA-[A-Z]{2,12}-[A-Z]{2,6}-[0-9]{4}-[0-9]{3}$`)

// RegulatoryRef convention: <AUTHORITY 2-6 letters>-<CATEGORY>-<YEAR>-<SERIAL>.
// Examples: REG01-INV-2026-001, ESMA-MICA-2026-042. Letters/digits/dashes only.
var regulatoryRefPattern = regexp.MustCompile(`^[A-Z]{2,6}-[A-Z0-9]{2,8}-[0-9]{4}-[A-Z0-9]{3,8}$`)

// ISO 4217 currencies accepted by the platform. Restricting to a small,
// reviewed set is safer than accepting any 3-letter string.
var supportedCurrencies = map[string]struct{}{
	"EUR": {}, "USD": {}, "GBP": {}, "CHF": {}, "JPY": {}, "MAD": {},
	"AED": {}, "SGD": {},
}

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

func ValidateAssetID(assetID string) error {
	if !assetIDPattern.MatchString(assetID) {
		return fmt.Errorf("assetID invalide: doit suivre le format RWA-XX-XXX-YYYY-NNN, reçu %q", assetID)
	}
	return nil
}

func ValidateCurrency(currency string) error {
	if _, ok := supportedCurrencies[currency]; !ok {
		return fmt.Errorf("devise non supportée: %q (ISO 4217 attendu)", currency)
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
	if !regulatoryRefPattern.MatchString(ref) {
		return fmt.Errorf(
			"référence réglementaire invalide: format attendu AUTHORITY-CATEGORY-YYYY-NNN, reçu %q",
			ref,
		)
	}
	return nil
}

func CheckMiCAThreshold(
	ctx contractapi.TransactionContextInterface,
	amount float64,
	assetID string,
) error {
	// MiCA Article 68: high-value crypto-asset transfers above 1,000,000 EUR
	// trigger an enhanced reporting obligation. The previous 1,000 EUR threshold
	// was a debug value and would saturate the regulator with every retail
	// transaction.
	const micaThresholdEUR = 1_000_000.0

	if amount > micaThresholdEUR {
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
