package main

import (
	"fmt"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

var authorisedMSPs = map[string][]string{
	"TokenizeAsset":  {"BANK01MSP"},
	"TransferAsset":  {"BANK01MSP"},
	"FreezeAsset":    {"REG01MSP"},
	"UnfreezeAsset":  {"REG01MSP"},
	"QueryAssets":    {"BANK01MSP", "REG01MSP"},
	"GetAsset":       {"BANK01MSP", "REG01MSP"},
	"GetAssetHistory": {"BANK01MSP", "REG01MSP"},
	"GetProvenanceTrail": {"BANK01MSP", "REG01MSP"},
}

func getClientMSP(ctx contractapi.TransactionContextInterface) (string, error) {
	id, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return "", fmt.Errorf("getClientMSP: impossible de lire le MSP: %w", err)
	}
	if id == "" {
		return "", fmt.Errorf("getClientMSP: MSP ID vide")
	}
	return id, nil
}

func getClientDN(ctx contractapi.TransactionContextInterface) (string, error) {
	cert, err := ctx.GetClientIdentity().GetX509Certificate()
	if err != nil {
		return "", fmt.Errorf("getClientDN: impossible de lire le certificat X.509: %w", err)
	}
	dn := cert.Subject.String()
	if dn == "" {
		return "", fmt.Errorf("getClientDN: DN vide dans le certificat")
	}
	return dn, nil
}

func verifyRole(ctx contractapi.TransactionContextInterface, functionName string) error {
	msp, err := getClientMSP(ctx)
	if err != nil {
		return fmt.Errorf("verifyRole: %w", err)
	}

	allowed, ok := authorisedMSPs[functionName]
	if !ok {
		return fmt.Errorf("verifyRole: fonction '%s' non reconnue dans la politique d'accès", functionName)
	}

	for _, a := range allowed {
		if strings.EqualFold(msp, a) {
			return nil
		}
	}

	return fmt.Errorf("accès refusé: MSP '%s' non autorisé pour '%s' (autorisés: %s)",
		msp, functionName, strings.Join(allowed, ", "))
}

