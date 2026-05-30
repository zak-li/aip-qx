# `rwa-token` chaincode

Go smart contract that runs on the AIP Qx Hyperledger Fabric channel
(`rwa-channel`). It implements the on-chain side of the tokenization
workflow: asset lifecycle, transfer, freeze, and the dual-endorsement
quorum between `BANK01MSP` (issuer) and `REG01MSP` (regulator).

## Files

| File                  | Role                                                           |
|-----------------------|----------------------------------------------------------------|
| `main.go`             | Entry point. Starts the chaincode in CCaaS or peer-launched mode. |
| `chaincode.go`        | `AssetTraceContract` — tokenize, transfer, freeze, query.      |
| `access_control.go`   | Role check helpers (`verifyRole`) and MSP-to-role mapping.     |
| `compliance.go`       | ID/format validation (ISIN, LEI, decimals).                    |
| `models.go`           | On-chain types (`Asset`, `AssetStatus`, transfer record).      |
| `chaincode_test.go`   | Unit tests using `MockTransactionContext`.                     |
| `Dockerfile.ccaas`    | Image for Chaincode-as-a-Service mode.                         |
| `go.mod` / `go.sum`   | Go module declaration and locked dependencies.                 |

## Build

Run from this directory:

```bash
go vet ./...
go test ./...
go build -o rwa-token .
```

## Run as CCaaS

The chaincode binary acts as a gRPC server when the environment variables
below are set; the peer connects to it instead of spawning a container.

```bash
export CHAINCODE_ID="<package-id-from-peer-lifecycle>"
export CHAINCODE_SERVER_ADDRESS="0.0.0.0:9999"
./rwa-token
```

Build the image with:

```bash
docker build -f Dockerfile.ccaas -t rwa-token:ccaas .
```

## Endorsement policy

State changes require the **2-of-2** policy
`AND('BANK01MSP.peer','REG01MSP.peer')` — see `fabric/config/configtx.yaml`.
Without an endorsement from both organisations the peer rejects the
proposal at commit time.
