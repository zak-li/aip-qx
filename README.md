<br>

<p align="center">
  <img src=".github/assets/logos/logo_qx.svg" alt="AIP Qx" width="350">
</p>

<br>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python"></a>
  <a href="https://hyperledger-fabric.readthedocs.io/"><img src="https://img.shields.io/badge/Hyperledger_Fabric-2.5-2F3134.svg" alt="Fabric"></a>
  <a href="https://go.dev/"><img src="https://img.shields.io/badge/Go-1.21+-00ADD8.svg" alt="Go"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-BUSL%201.1-blue.svg" alt="License"></a>
</p>

<br>

## AIP Qx

> **AIP Qx**, **A**sset **I**ssuance **P**latform · **Q**uorum e**X**change.
> The name captures the two pillars of the system: a regulated **issuance platform** for Real-World Assets on Hyperledger Fabric, and a **quorum-based exchange** layer where every state-changing transaction is multi-endorsed by the permissioned consortium (issuer + regulator) before it lands on-chain.

AIP Qx is an institutional platform for tokenizing Real World Assets on a permissioned Hyperledger Fabric network. It handles the full asset lifecycle from issuance to redemption, with built-in AML/KYC compliance, ZK-KYC identity proofs, FHE-based fraud scoring, and a RAG regulatory agent for MiCA queries.

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
  <img src=".github/assets/diagrams/compliance-flow-v3.svg" alt="Compliance Flow" width="800">
</p>

AIP Qx exposes a FastAPI REST API and a gRPC server in parallel. Authentication is OIDC-based via Keycloak with PKCE (authorization_code flow). Private keys for Fabric identities are stored in HashiCorp Vault (KV v2), and every response carries six security headers with rate limiting and host filtering.

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
| PostgreSQL 14+ | Application database (Supabase in production, local PG for tests) |
| Redis 7+ | Cache and Celery broker |
| HashiCorp Vault | Fabric identity key storage (KV v2) |
| Keycloak 24 | OIDC SSO / PKCE authentication |
| Neo4j 5+ | Graph database for relationship analysis (Aura in production) |
| Docker + Compose | Peers, orderer, CouchDB, Keycloak, API, Celery containers |

## Quick Start

**Step 1: Clone and configure**

```bash
git clone https://github.com/zak-li/aip-qx.git
cd aip-qx
cp .env.example .env
```

Open `.env` and fill in at minimum `DATABASE_URL`, `REDIS_URL`, the Fabric variables, and all `KEYCLOAK_*` variables.

**Step 2: Install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate                # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Step 3: Start the Fabric network**

```bash
cd fabric
# generate crypto material + genesis block, then bring containers up
docker run --rm -v "$PWD:/work" -w /work -e FABRIC_CFG_PATH=/work/config \
    hyperledger/fabric-tools:2.5.4 \
    cryptogen generate --config=config/crypto_config.yaml --output=crypto-config
docker run --rm -v "$PWD:/work" -w /work -e FABRIC_CFG_PATH=/work/config \
    hyperledger/fabric-tools:2.5.4 \
    configtxgen -profile RWAGenesis -outputBlock config/rwa-channel.pb -channelID rwa-channel
docker compose -f docker/docker-compose.yaml up -d
./scripts/deploy-chaincode.sh
```

**Step 4: Deploy Keycloak**

```bash
cd stack/keycloak
cp .env.keycloak.example .env.keycloak   # fill in admin/DB credentials
bash deploy.sh
```

The `setup-realm.py` script prints a `KEYCLOAK_CLIENT_SECRET` — copy it into your `.env`.

**Step 5: Start the API and worker**

```bash
docker compose up -d                     # API + Celery worker
# Or without Docker:
uvicorn core.main:app --host 0.0.0.0 --port 8000 --workers 1
celery -A core.core.celery_app worker --loglevel=info -Q celery,compliance,reports,fabric_events
```

The API is live at `http://localhost:8000`.

**Step 6: Authenticate**

Authentication uses Keycloak OIDC with PKCE. Open in a browser:

```
http://localhost:8000/api/v1/auth/login
```

This redirects to Keycloak's login page. After authentication, the callback sets httpOnly session cookies and returns an access token.

```bash
# Use the access token for API calls:
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/assets
```

## API Reference

**Authentication (OIDC/PKCE)**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/auth/login` | Redirect to Keycloak login (PKCE) |
| GET | `/api/v1/auth/callback` | OIDC callback (exchanges code for tokens) |
| POST | `/api/v1/auth/refresh` | Refresh access token via cookie |
| POST | `/api/v1/auth/logout` | Revoke session (clear cookies + Keycloak) |
| GET | `/api/v1/auth/me` | Current user profile |
| GET | `/api/v1/auth/me/export` | GDPR Art. 15 personal data export |
| DELETE | `/api/v1/auth/me` | GDPR Art. 17 right to erasure |

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
| GET | `/api/v1/audit/asset/{id}` | On-chain provenance trail for an asset |
| POST | `/api/v1/audit/report/generate/{id}` | Generate PDF audit report (async) |
| GET | `/api/v1/audit/report/status/{task_id}` | Check report generation status |
| POST | `/api/v1/audit/fraud/scan` | Trigger Neo4j fraud graph scan |
| GET | `/api/v1/transactions/{tx_ref}` | Lookup a transaction by reference |
| GET | `/api/v1/transactions/stats/summary` | Transaction statistics summary |
| GET | `/api/v1/events/stream` | Live Fabric event stream (SSE) |
| POST | `/api/v1/agent/chat` | RAG query over regulatory knowledge base |
| GET | `/metrics` | Prometheus metrics |

## Environment Variables

**Required**

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL (`redis://:password@host:6379/0`) |
| `KEYCLOAK_URL` | Keycloak base URL (`https://host:8443`) |
| `KEYCLOAK_CLIENT_SECRET` | OIDC client secret (from `setup-realm.py`) |
| `FABRIC_WALLET_PATH` | Path to `fabric_wallet.json` |
| `FABRIC_CONNECTION_PROFILE` | Path to `connection_profile.yaml` |
| `FABRIC_CHANNEL` | Fabric channel name |
| `FABRIC_CHAINCODE` | Chaincode name |
| `VAULT_ADDR` | HashiCorp Vault address (`http://host:8200`) |
| `VAULT_TOKEN` | Vault authentication token (for wallet KV access; metrics scrape uses `unauthenticated_metrics_access = true` in `vault.hcl`) |
| `NEO4J_URI` | Neo4j bolt URI (`neo4j+s://<id>.databases.neo4j.io` for Aura) |
| `NEO4J_USER` / `NEO4J_PASS` | Neo4j credentials |

**Optional**

| Variable | Default | Description |
|---|---|---|
| `KEYCLOAK_REALM` | `qx` | Keycloak realm name |
| `KEYCLOAK_CLIENT_ID` | `qx-api` | OIDC client identifier |
| `KEYCLOAK_VERIFY_TLS` | `false` | Verify Keycloak TLS certificate |
| `KEYCLOAK_CA_CERT_PATH` | | Path to pinned CA for Keycloak TLS (self-signed cert deployments) |
| `NEO4J_DATABASE` | `neo4j` | Neo4j database name (set to the Aura instance ID when using Aura free tier) |
| `GROQ_API_KEY` | `""` | Groq API key for the regulatory agent |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model ID |
| `FABRIC_TLS_ENABLED` | `true` | TLS for Fabric gRPC |
| `FABRIC_GRPC_TIMEOUT` | `30` | gRPC timeout in seconds |
| `FABRIC_RETRY_MAX_ATTEMPTS` | `5` | Retry attempts on Fabric errors |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_ORIGINS` | | Comma-separated CORS origins |

## Project Structure

```
aip-qx/
├── core/
│   ├── main.py                 # FastAPI app, middleware, metrics
│   ├── config.py
│   ├── features/
│   │   ├── assets/             # Asset lifecycle
│   │   ├── compliance/         # AML, KYC, MiCA rules
│   │   ├── audit/              # Trail, integrity, PDF reports
│   │   ├── auth/               # Keycloak OIDC/PKCE, GDPR
│   │   ├── zkp/                # ZK-KYC proofs
│   │   ├── fhe/                # FHE fraud scorer (HElib CKKS)
│   │   └── agent/              # RAG pipeline, ChromaDB
│   ├── fabric_client/          # Wallet, events, retry, circuit breaker
│   └── grpc_server/            # gRPC servicers
├── chaincode/rwa-token/        # Go chaincode (CCaaS)
├── fabric/
│   ├── config/                 # core.yaml, connection_profile.yaml
│   ├── docker/                 # docker-compose.yaml
│   └── scripts/                # Network lifecycle scripts
├── stack/
│   ├── keycloak/               # Compose, TLS, realm setup
│   ├── vault/                  # Vault config, policy, unseal service
│   └── monitoring/             # Prometheus, Grafana, Loki
└── database/
    ├── migrations/
    └── fixtures/
```

## Observability

AIP Qx ships a full monitoring stack managed via systemd. Prometheus scrapes **twelve** targets — the API itself, Fabric peers (BANK01 + REG01), CouchDB for each peer, Keycloak, Vault, Redis, PostgreSQL, node-exporter, the Celery exporter, and Prometheus itself. Grafana renders one curated `AIP Qx` dashboard (uid `qx`, served at the root of `/dashboards`) covering service health, API throughput / latency percentiles, infrastructure utilization, datastores, blockchain activity, and compliance metrics. Loki aggregates structured JSON logs from the API container, Celery worker, Fabric peers, and the host's systemd journal.

The dashboard is auto-provisioned from `stack/monitoring/grafana_dashboard.json` via the file provider in `stack/monitoring/grafana-provisioning/`. Datasource UIDs are pinned (`ffgx1hbr25a0wc` for Prometheus, `loki` for Loki) so the dashboard JSON is portable.

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
