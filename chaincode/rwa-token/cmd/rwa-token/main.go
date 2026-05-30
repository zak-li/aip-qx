// Command rwa-token is the chaincode binary for the AIP Qx Fabric network.
//
// It supports two execution modes, selected at start-up by env vars:
//
//   - Peer-launched: default. The peer spawns this binary inside the chaincode
//     container after a successful lifecycle install.
//   - Chaincode-as-a-Service (CCaaS): when CHAINCODE_ID and CHAINCODE_SERVER_ADDRESS
//     are set, the binary starts a gRPC server that the peer connects to. This
//     is the mode used by the AIP Qx production deployment — see
//     fabric/scripts/deploy-chaincode.sh.
package main

import (
	"log"
	"os"

	"github.com/hyperledger/fabric-chaincode-go/shim"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"

	"github.com/zak-li/aip-qx/chaincode/rwa-token/internal/contract"
)

func main() {
	cc, err := contractapi.NewChaincode(&contract.AssetTraceContract{})
	if err != nil {
		log.Panicf("Erreur création chaincode: %v", err)
	}

	serverAddr := os.Getenv("CHAINCODE_SERVER_ADDRESS")
	ccID := os.Getenv("CHAINCODE_ID")

	if serverAddr != "" && ccID != "" {
		server := &shim.ChaincodeServer{
			CCID:    ccID,
			Address: serverAddr,
			CC:      cc,
			TLSProps: shim.TLSProperties{
				Disabled: true,
			},
		}
		log.Printf("Démarrage CCaaS sur %s avec ID %s", serverAddr, ccID)
		if err := server.Start(); err != nil {
			log.Panicf("Erreur démarrage serveur CCaaS: %v", err)
		}
		return
	}

	if err := cc.Start(); err != nil {
		log.Panicf("Erreur démarrage chaincode: %v", err)
	}
}
