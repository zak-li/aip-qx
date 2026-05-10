# Changelog

All notable changes to RegX are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).  
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.0.0] - 2026-05-10

### Added

- Hyperledger Fabric 2.5 permissioned network with two organizations (BANK01, REG01), dedicated peers, and CouchDB state databases
- Go chaincode deployed as CCaaS with dual-endorsement policy enforcing ACTIVE / FROZEN / REDEEMED asset lifecycle
- FastAPI REST API and gRPC server running in parallel, JWT authentication with configurable TTL
- Asset tokenization, transfer, freeze/unfreeze, valuation, and on-chain provenance history
- AML sanctions screening backed by Ed25519-authenticated manifests
- MiCA compliance layer validating exposure limits, restricted asset classes, and supervisory reporting
- zk-KYC workflow with Merkle proof-based identity attestation
- FHE-based fraud scoring operating on encrypted datasets via Celery workers
- RAG regulatory agent querying a ChromaDB vector store with Groq LLM for MiCA questions
- On-chain audit trail with off-chain hash integrity verification and async PDF report generation
- Neo4j fraud graph scanning
- HashiCorp Vault integration for Fabric identity key storage
- Prometheus metrics endpoint, Grafana dashboards, and Loki log aggregation
- Alembic migrations and database fixtures
- Docker Compose deployment for Fabric peers, orderer, and CouchDB
- Systemd service units for API, Celery workers, and monitoring stack
- GitHub Actions CI pipeline covering linting, unit tests, and integration tests against live PostgreSQL and Redis

[1.0.0]: https://github.com/zak-li/regx/releases/tag/v1.0.0
