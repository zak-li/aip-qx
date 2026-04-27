# Architecture & Flow Diagrams (Mermaid)

These diagrams visualize the Regulatory-Embedded Consensus (REC) architecture and execution flows.

## A. System Architecture Diagram

This diagram maps the high-level components from the user frontend down to the distributed ledger components.

```mermaid
graph TD
    User([Institutional Investor])
    
    subgraph Client Layer
        SPA[React SPA]
    end
    
    subgraph Middleware Layer
        API[FastAPI Backend]
        Neo4j[(Neo4j Fraud Graph)]
        DB[(PostgreSQL KYC Data)]
        Vault[HashiCorp Vault]
    end
    
    subgraph Regulatory-Embedded Ledger
        Gateway[Fabric Gateway]
        
        subgraph Endorsement Network
            PeerF[Financial Operator Peer]
            PeerR[Regulatory Body Peer]
        end
        
        Orderer[EtcdRaft Ordering Service]
        CC[Go Chaincode / CCaaS]
    end

    User --> SPA
    SPA -->|HTTPS| API
    API <--> Neo4j
    API <--> DB
    API <--> Vault
    
    API -->|gRPC| Gateway
    Gateway --> PeerF
    Gateway --> PeerR
    PeerF <--> CC
    PeerR <--> CC
    PeerF --> Orderer
    PeerR --> Orderer
```

---

## B. Transaction Flow Diagram

This flow shows the end-to-end journey of a transaction, highlighting the off-chain AML gatekeeping and the on-chain endorsement.

```mermaid
sequenceDiagram
    participant User
    participant API as FastAPI Backend
    participant Neo4j as Neo4j Graph
    participant PeerF as Financial Peer (F)
    participant PeerR as Regulatory Peer (R)
    participant Orderer as EtcdRaft Orderer

    User->>API: Initiate Transfer(AssetA, 1.5M EUR)
    activate API
    API->>Neo4j: Query AML Graph(Sender, Receiver)
    Neo4j-->>API: Risk Score OK
    
    API->>PeerF: Propose Transaction(TransferAsset)
    API->>PeerR: Propose Transaction(TransferAsset)
    
    PeerF->>PeerF: Execute Chaincode (Validate state)
    PeerR->>PeerR: Execute Chaincode (Validate compliance)
    
    PeerF-->>API: Return Signed Proposal (F)
    PeerR-->>API: Return Signed Proposal (R)
    
    API->>Orderer: Submit Endorsed Transaction (F + R signatures)
    Orderer->>Orderer: Sequence block (EtcdRaft consensus)
    Orderer-->>PeerF: Broadcast Block
    Orderer-->>PeerR: Broadcast Block
    
    PeerF->>PeerF: Commit to Ledger
    PeerR->>PeerR: Commit to Ledger
    
    API-->>User: Transfer Successful
    deactivate API
```

---

## C. REC Validation Flow

This diagram illustrates the internal logic of the Regulatory-Embedded Consensus Model, specifically how the endorsement policy $\mathbb{E}(\mathcal{T})$ is satisfied before committing.

```mermaid
flowchart TD
    Start([Transaction Proposal]) --> Split{Send to Endorsers}
    
    Split --> Bank[Financial Operator]
    Split --> Reg[Regulatory Body]
    
    subgraph Endorsement Policy: Sign(F) AND Sign(R)
        Bank -->|V_state| B_Valid{State Valid?}
        B_Valid -->|Yes| B_Sign[Sign Transaction]
        B_Valid -->|No| Reject1([Reject])
        
        Reg -->|V_comp| R_Valid{Compliant?}
        R_Valid -->|Yes| R_Sign[Sign Transaction]
        R_Valid -->|No| Reject2([Reject])
    end
    
    B_Sign --> Assemble
    R_Sign --> Assemble
    
    Assemble{Both Signatures Present?}
    Assemble -->|Yes| Orderer[Send to EtcdRaft Orderer]
    Assemble -->|No| Reject3([Transaction Fails])
    
    Orderer --> Commit([Commit to Immutable Ledger])
```
