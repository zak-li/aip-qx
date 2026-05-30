# Changelog

All notable changes to AIP Qx are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Changed
- **Project layout**: top-level directories renamed for clarity —
  `dlt-nodes/` → `fabric/`, `database/` → `db/`, `deployment/` → `stack/`.
- **JWT claim**: `pex_role` renamed to `qx_role` across the API, gRPC
  interceptors, Keycloak protocol mappers and user-attribute migration.
- **Assets**: removed every unused logo / icon — only
  `.github/assets/logos/logo_qx.svg` remains alongside the compliance
  flow diagram.

---

## [1.0.0] - 2026-05-10

### Added
- **Core Engine**: Initial release of the AIP Qx tokenization platform
  (FastAPI + gRPC + Celery).
- **DLT Network**: Hyperledger Fabric 2.5 permissioned network with a
  Go chaincode deployed as Chaincode-as-a-Service.
- **Compliance Suite**: MiCA validation, AML sanctions screening,
  FHE-based fraud scoring, and zk-KYC workflows.
- **AI Agent**: Regulatory RAG agent powered by ChromaDB and Groq.
- **Security & Ops**: HashiCorp Vault integration, Neo4j graph scanning,
  and a complete Prometheus / Grafana monitoring stack.

[Unreleased]: https://github.com/zak-li/aip-qx/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/zak-li/aip-qx/releases/tag/v1.0.0
