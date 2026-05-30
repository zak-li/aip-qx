// Package contract implements the AIP Qx rwa-token Fabric chaincode.
//
// AssetTraceContract is the entry type registered with the contract API. Its
// methods fall into three groups, each with its own MSP authorisation:
//
//   - Issuer (BANK01MSP):  TokenizeAsset, TransferAsset
//   - Regulator (REG01MSP): FreezeAsset, UnfreezeAsset
//   - Read-only (both):     GetAsset, GetAssetHistory, GetProvenanceTrail,
//                           QueryAssets
//
// State changes additionally require the 2-of-2 endorsement policy declared
// in fabric/config/configtx.yaml — the function-level ACL in access.go is an
// early gate that rejects forbidden calls *before* endorsement is solicited.
//
// The package is internal/ by design: only the rwa-token cmd binary should
// import it, and the Go toolchain enforces that boundary.
package contract
