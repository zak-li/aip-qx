# Documentation

This folder contains the technical and research documentation for the **Quant-ix RWA Tokenization Platform** — a regulatory-embedded, permissioned blockchain system for institutional Real-World Asset tokenization.

## Structure

```
docs/
├── technical/          # System design and operational documentation
│   ├── architecture.md     Architecture overview and component breakdown
│   ├── diagrams.md         Mermaid diagrams (system, transaction flow, REC validation)
│   └── use-cases.md        End-to-end execution flows (tokenization, transfer, freeze)
│
└── research/           # Formal mathematical proofs
    ├── game_theory_proof.tex   Game-theoretic analysis of the Compliance Tribunal
    └── zk_kyc_formal_proof.tex Formal security proofs for the Schnorr-based zk-KYC protocol
```

## Technical Documentation

| Document | Description |
|---|---|
| [architecture.md](technical/architecture.md) | High-level system architecture, component breakdown (Fabric, FastAPI, React) |
| [diagrams.md](technical/diagrams.md) | Visual diagrams: system topology, transaction sequence, REC endorsement flow |
| [use-cases.md](technical/use-cases.md) | Detailed execution flows for asset onboarding, transfer, and regulatory freeze |

## Research Papers

| Document | Description |
|---|---|
| [game_theory_proof.tex](research/game_theory_proof.tex) | Proves that truthful voting in the Compliance Tribunal is a strict Nash Equilibrium under reputational staking |
| [zk_kyc_formal_proof.tex](research/zk_kyc_formal_proof.tex) | Proves Completeness, Soundness, and Zero-Knowledge for the Schnorr-based zk-KYC protocol; formalizes MiCA Article 68 alignment |

## Key Concepts

- **Regulatory-Embedded Consensus (REC):** Endorsement policy requiring both financial operator (BNP Paribas) and regulatory body (AMF) signatures before any transaction is committed.
- **zk-KYC:** A Non-Interactive Zero-Knowledge proof protocol that satisfies MiCA KYC requirements without exposing private identity data on the ledger.
- **Compliance Tribunal:** A decentralized auditing mechanism where institutional peers vote on flagged anomalies; game-theoretically guaranteed to produce truthful outcomes via Schelling-point equilibrium.
