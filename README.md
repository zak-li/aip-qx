<br>

<p align="center">
  <img src="assets/vector/logo-monochrome.svg" alt="RegX" width="300">
</p>

<br>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://hyperledger-fabric.readthedocs.io/"><img src="https://img.shields.io/badge/Hyperledger_Fabric-2.5-2F3134.svg" alt="Fabric"></a>
  <a href="https://go.dev/"><img src="https://img.shields.io/badge/Go-1.21+-00ADD8.svg" alt="Go"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-BUSL%201.1-blue.svg" alt="License"></a>
</p>

<br>

## RegX

RegX is an institutional platform for tokenizing Real World Assets on a permissioned Hyperledger Fabric network. It handles the full asset lifecycle from issuance to redemption, with built-in AML/KYC compliance, ZK-KYC identity proofs, FHE-based fraud scoring, and a RAG regulatory agent for MiCA queries.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Observability](#observability)
- [License](#license)

## Features

The Fabric network runs two organizations, BANK01 and REG01, each with a dedicated peer and CouchDB state database. The Go chaincode runs as CCaaS and enforces a dual-endorsement policy on all state-changing transactions. Assets move through an `ACTIVE`, `FROZEN`, `REDEEMED` lifecycle recorded immutably on-chain, and Fabric events are streamed live via gRPC with automatic reconnection.

The platform embeds compliance directly into transaction execution and asset lifecycle management. Sanctions screening is backed by Ed25519-authenticated manifests, while the MiCA enforcement layer validates exposure boundaries, restricted asset classes, and supervisory reporting requirements. zk-KYC workflows enable cryptographic identity attestation through Merkle proofs without exposing underlying credentials. Encrypted fraud analytics powered by Fully Homomorphic Encryption evaluate AML risk in confidential datasets, with persistent monitoring of KYC validity and systemic concentration exposure.

<p align="center">
  <img src="assets/compliance-flow.svg" alt="Compliance Flow" width="800">
</p>

RegX exposes a FastAPI REST API and a gRPC server in parallel. Authentication is JWT-based with configurable TTL. Secrets are stored as `SecretStr` via pydantic-settings and never appear in logs. Private keys for Fabric identities live in HashiCorp Vault, and every response carries six security headers with rate limiting and host filtering.

Every transaction produces an on-chain audit entry. An off-chain integrity checker verifies hashes independently, PDF audit reports are generated asynchronously via Celery, and the RAG agent answers regulatory questions by querying a ChromaDB vector store with Groq LLM.

## Requirements

**API**

| Package | Version |
|---|---|
| Python | 3.12+ |
| FastAPI | 0.135+ |
| Celery | 5.6+ |
| SQLAlchemy | 2.0+ |
| grpcio | 1.78+ |
| pydantic-settings | 2.4+ |
| prometheus-client | 0.24+ |

**Technology Stack**

| Component | Role |
|---|---|
| Hyperledger Fabric 2.5 | Permissioned blockchain |
| PostgreSQL 14+ | Application database |
| Redis 7+ | Cache and Celery broker |
| HashiCorp Vault | Fabric identity key storage |
| Neo4j 5+ | Graph database for relationship analysis |
| Docker + Compose | Peers, orderer, CouchDB containers |

## Quick Start

**Step 1: Clone and configure**

```bash
git clone https://github.com/zak-li/regx.git
cd regx
cp .env.example .env
```

Open `.env` and fill in at minimum `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, and the Fabric variables.

**Step 2: Install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Step 3: Start the Fabric network**

```bash
cd network
./scripts/network-up.sh
./scripts/create-channel.sh
./scripts/deploy-chaincode.sh
./scripts/enroll-users.sh
```

**Step 4: Start the API and worker**

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
celery -A backend.core.celery_app worker --loglevel=info -Q celery,compliance,reports,fabric_events
```

The API is live at `http://localhost:8000`. Interactive docs are at `/docs` (Swagger UI) or `/redoc`.

**Step 5: Authenticate**

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'
```

Pass the returned token as `Authorization: Bearer <token>` on all subsequent requests.

## API Reference

**Authentication**

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Obtain JWT token |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| POST | `/api/v1/auth/logout` | Revoke session |
| GET | `/api/v1/auth/me` | Current user profile |

**Assets**

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/assets/tokenize` | Tokenize a new real-world asset |
| GET | `/api/v1/assets` | List assets with filtering |
| GET | `/api/v1/assets/{id}` | Get asset by ID |
| POST | `/api/v1/assets/transfer` | Transfer ownership |
| POST | `/api/v1/assets/freeze` | Freeze asset (compliance hold) |
| POST | `/api/v1/assets/unfreeze` | Unfreeze asset |
| GET | `/api/v1/assets/{id}/history` | On-chain provenance history |
| POST | `/api/v1/assets/{id}/valuate` | Submit asset valuation |

**Compliance and KYC**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/compliance/{user_id}` | Compliance status for a user |
| GET | `/api/v1/compliance/alerts/active` | Active compliance alerts |
| POST | `/api/v1/compliance/screening/run` | Run AML sanctions screening |
| POST | `/api/v1/compliance/kyc/submit` | Submit KYC documents |
| POST | `/api/v1/zkp/setup-key` | Issue ZK-KYC credential |
| POST | `/api/v1/zkp/verify` | Verify a ZK-KYC proof |

**Audit, ledger and agent**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/audit/` | List audit log entries |
| GET | `/api/v1/audit/asset/{id}` | On-chain provenance trail for an asset |
| POST | `/api/v1/audit/report/generate/{id}` | Generate PDF audit report (async) |
| GET | `/api/v1/audit/report/status/{task_id}` | Check report generation status |
| POST | `/api/v1/audit/fraud/scan` | Trigger Neo4j fraud graph scan |
| GET | `/api/v1/transactions` | Ledger transaction history |
| GET | `/api/v1/transactions/stats/summary` | Transaction statistics summary |
| GET | `/api/v1/events/stream` | Live Fabric event stream (SSE) |
| POST | `/api/v1/agent/chat` | RAG query over regulatory knowledge base |
| GET | `/metrics` | Prometheus metrics |

## Environment Variables

**Required**

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing key, minimum 32 characters |
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL (`redis://:password@host:6379/0`) |
| `FABRIC_WALLET_PATH` | Path to `fabric_wallet.json` |
| `FABRIC_CONNECTION_PROFILE` | Path to `connection_profile.yaml` |
| `FABRIC_CHANNEL` | Fabric channel name |
| `FABRIC_CHAINCODE` | Chaincode name |
| `VAULT_ADDR` | HashiCorp Vault address (e.g. `http://127.0.0.1:8200`) |
| `VAULT_TOKEN` | Vault authentication token |

**Optional**

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | `""` | Groq API key for the regulatory agent |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model ID |
| `NEO4J_URI` | | Neo4j bolt URI |
| `FABRIC_TLS_ENABLED` | `true` | TLS for Fabric gRPC |
| `FABRIC_GRPC_TIMEOUT` | `30` | gRPC timeout in seconds |
| `FABRIC_RETRY_MAX_ATTEMPTS` | `5` | Retry attempts on Fabric errors |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_ORIGINS` | | Comma-separated CORS origins |

## Project Structure

```
regx/
├── backend/
│   ├── main.py                 # FastAPI app, middleware, metrics
│   ├── config.py
│   ├── features/
│   │   ├── assets/             # Asset lifecycle
│   │   ├── compliance/         # AML, KYC, MiCA rules
│   │   ├── audit/              # Trail, integrity, PDF reports
│   │   ├── zkp/                # ZK-KYC proofs
│   │   ├── fhe/                # FHE fraud scorer
│   │   └── agent/              # RAG pipeline, ChromaDB
│   ├── fabric_client/          # Wallet, events, retry, circuit breaker
│   └── grpc_server/            # gRPC servicers
├── chaincode/rwa-token/        # Go chaincode (CCaaS)
├── network/
│   ├── config/                 # core.yaml, connection_profile.yaml
│   ├── docker/                 # docker-compose.yaml
│   └── scripts/                # Network lifecycle scripts
├── deployment/
│   ├── systemd/
│   └── monitoring/             # Prometheus, Grafana, Loki
└── database/
    ├── migrations/
    └── fixtures/
```

## Observability

RegX ships a full monitoring stack managed via systemd. Prometheus scrapes ten targets including Fabric peers, CouchDB, Redis, PostgreSQL, and the custom Celery exporter. Grafana provides dashboards for service health, API latency percentiles, infrastructure utilization, and compliance metrics. Loki aggregates structured JSON logs from the API, Celery workers, Docker containers, and systemd.

| Component | Port |
|---|---|
| Prometheus | 9090 |
| Grafana | 3000 |
| Loki | 3100 |
| Node Exporter | 9100 |
| Celery Exporter | 9808 |

Custom metrics exposed at `/metrics`:

| Metric | Description |
|---|---|
| `rwa_assets_by_status` | Asset count by lifecycle status |
| `rwa_compliance_blocks_total` | Compliance blocks by reason |
| `rwa_kyc_expiring_count` | KYC records expiring within 30 days |
| `rwa_circuit_breaker_state` | Fabric circuit breaker state |
| `rwa_celery_tasks_total` | Celery task completions by name and status |

## License

This project is licensed under the [Business Source License 1.1](LICENSE).
