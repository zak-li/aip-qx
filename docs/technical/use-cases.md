# End-to-End Use Cases

This document maps out the specific execution flows of the RWA Tokenization platform, demonstrating the interplay between the off-chain middleware and the on-chain smart contract.

## Use Case 1: Institutional Asset Onboarding and Tokenization

**Goal:** A commercial bank (Financial Operator) wants to tokenize a corporate bond.

**Flow:**
1. **KYC & Entity Verification (Off-Chain):**
   - The issuer submits their details to the FastAPI backend.
   - The backend validates the entity's Legal Entity Identifier (LEI) and runs AML checks using the **Neo4j Fraud Graph**.
   - Identity documents are securely stored in **PostgreSQL**.
2. **Blockchain Submission (On-Chain):**
   - The FastAPI backend prepares the transaction, cryptographically signing it via the Fabric Gateway using keys retrieved from **HashiCorp Vault**.
   - The `TokenizeAsset` chaincode function is invoked with arguments: `assetID`, `ISIN`, `AssetType`, `IssuerLEI`, `NominalValue`, `Currency`, etc.
3. **Smart Contract Validation:**
   - The Go chaincode validates the ISIN (must be 12 characters, specific format), LEI (20 alphanumeric characters), and checks that the currency is in the supported ISO 4217 list.
   - The asset is persisted to the ledger state with a `StatusActif` flag, and an `AssetCreated` event is emitted.

## Use Case 2: High-Value Asset Transfer and MiCA Reporting

**Goal:** An investor transfers a significant portion of their tokenized asset, triggering regulatory thresholds.

**Flow:**
1. **Pre-Trade Compliance (Off-Chain):**
   - The backend receives the transfer request. It queries the Neo4j graph to ensure the destination wallet is not linked to suspicious topologies (e.g., sanction evasion rings).
2. **Transfer Execution (On-Chain):**
   - The backend invokes the `TransferAsset` chaincode function.
   - The chaincode verifies the caller's role, checks that the asset is active (not frozen), and updates the ownership.
3. **MiCA Threshold Detection:**
   - During execution, the chaincode's `CheckMiCAThreshold` evaluates the transfer amount.
   - If the amount exceeds **1,000,000 EUR** (as per MiCA Art. 68), the chaincode emits a specific `MiCAThresholdExceeded` event natively.
4. **Regulatory Notification (Off-Chain):**
   - The AMF's backend event listener (`FabricEventListener`) catches the `MiCAThresholdExceeded` event and routes it to the compliance module, triggering an automated Suspicious Activity Report (SAR) task via **Celery**.

## Use Case 3: Regulatory Asset Freeze

**Goal:** The regulatory body (AMF) detects illicit activity and freezes a specific tokenized asset.

**Flow:**
1. **Anomaly Detection:**
   - Either through the Neo4j fraud graph alerts or an external mandate, the AMF determines that an asset must be locked.
2. **Execution (On-Chain):**
   - The regulator invokes the `FreezeAsset` chaincode function, providing a regulatory reference (e.g., `AMF-INV-2026-001`) and a justification.
   - The chaincode verifies that the invoking identity possesses the Regulatory Body role via the MSP configuration.
3. **State Mutation:**
   - The asset's status is changed to `StatusGele`.
   - Any subsequent attempts to call `TransferAsset` for this asset ID will be rejected at the chaincode endorsement stage.
   - The chaincode emits an `AssetFrozen` event, ensuring all participants on the network are synchronized regarding the asset's suspended state.
