# Changelog

All notable changes to AIP Qx are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.3.0] - 2026-05-28

### Added
- **AIP Qx CLI**: Complete overhaul of the Command Line Interface featuring a modernized, full-screen TUI (Text User Interface) dashboard (`AIP Qx CLI`).
- **Assets**: Added vectorized SVG logos and specialized CLI ASCII art graphics (`cli_logo.svg`).

### Changed
- **Rebranding**: Complete institutional rebranding from "AIP Qx" (and internal "Qx") to **AIP Qx** (Provenance and Exchange) across the entire codebase, documentation, GitHub assets, Keycloak themes, and TUI interfaces.
- **Repository**: Renamed GitHub remote repository to `zak-li/AIP Qx`.

---

## [1.2.0] - 2026-05-24

### Changed
- **Architecture**: Major refactoring renaming `backend/` to `core/` and `network/` to `dlt-nodes/` for institutional DLT alignment.
- **CI/CD**: Re-configured CI pipelines, Pytest, and Alembic migrations to support new module paths.
- **Cleanup**: Removed obsolete deployment scripts and output logs for a pristine repository.

---

## [1.1.0] - 2026-05-24

### Changed
- **Infrastructure**: Fully migrated from legacy systemd to pure Docker Compose for optimal network isolation.
- **Security**: Integrated Keycloak OIDC authentication. Rotated and purged all hardcoded credentials from the repository.
- **Observability**: Updated Grafana dashboards with Keycloak/Vault health tracking and Chaincode metrics.

---

## [1.0.0] - 2026-05-10

### Added
- **Core Engine**: Initial release of the AIP Qx RWA Tokenization platform (FastAPI, gRPC, Celery).
- **DLT Network**: Hyperledger Fabric 2.5 permissioned network setup with Go chaincode deployed as CCaaS.
- **Compliance Suite**: Complete MiCA validation, AML sanctions screening, FHE-based fraud scoring, and zk-KYC workflows.
- **AI Agent**: Regulatory RAG agent powered by ChromaDB and Groq LLM.
- **Security & Ops**: HashiCorp Vault integration, Neo4j graph scanning, and complete Prometheus/Grafana monitoring stack.

[1.3.0]: https://github.com/zak-li/AIP Qx/releases/tag/v1.3.0
[1.2.0]: https://github.com/zak-li/AIP Qx/releases/tag/v1.2.0
[1.1.0]: https://github.com/zak-li/AIP Qx/releases/tag/v1.1.0
[1.0.0]: https://github.com/zak-li/AIP Qx/releases/tag/v1.0.0
