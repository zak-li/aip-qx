# `rwa-token` chaincode

Go smart contract that runs on the AIP Qx Hyperledger Fabric channel
(`rwa-channel`). Implements the on-chain side of the tokenisation
workflow with the **2-of-2 endorsement quorum** between `BANK01MSP`
(issuer) and `REG01MSP` (regulator).

## Layout

Standard Go project layout — `cmd/` holds the binary entry point and
`internal/` enforces that nothing outside this module can import the
contract implementation.

```
chaincode/rwa-token/
├── cmd/rwa-token/
│   └── main.go             ← bootstrap: peer-launched vs CCaaS mode
├── internal/contract/
│   ├── doc.go              ← package documentation (godoc)
│   ├── contract.go         ← AssetTraceContract + handlers
│   ├── access.go           ← MSP/DN extraction + per-function ACL
│   ├── compliance.go       ← ISIN/LEI/currency validators + MiCA Art. 68
│   ├── models.go           ← FinancialAsset, ProvenanceRecord, statuses
│   └── contract_test.go    ← unit tests
├── Dockerfile.ccaas        ← image for Chaincode-as-a-Service mode
├── go.mod                  ← module: github.com/zak-li/aip-qx/chaincode/rwa-token
├── go.sum
├── .gitignore
└── README.md
```

## Build & test

```bash
go vet ./...
go test ./...
go build -o rwa-token ./cmd/rwa-token
```

CI runs the same three commands — see [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) (`go-build` job).

## Run as CCaaS

The binary acts as a gRPC server when the two env vars below are set;
the peer connects to it instead of spawning a chaincode container.

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

State changes require **2-of-2** endorsement:

```
AND('BANK01MSP.peer','REG01MSP.peer')
```

Declared in [`fabric/config/configtx.yaml`](../../fabric/config/configtx.yaml) and enforced by the peer at
commit time. The function-level ACL in `internal/contract/access.go`
is an extra gate on the proposal side — it rejects calls from a
non-authorised MSP *before* the proposal is endorsed, saving a
round-trip.
