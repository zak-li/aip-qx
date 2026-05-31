<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/logos/logo-dark.svg">
    <img src=".github/assets/logos/logo.svg" alt="Pxtly" width="300">
  </picture>
</p>

<br>

<p align="center">
  <a href="https://github.com/zak-li/pxtly/releases"><img src="https://img.shields.io/github/v/tag/zak-li/pxtly?label=version&color=4AAFFD" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache_2.0-4EB4FD.svg" alt="License: Apache 2.0"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12+-51B9FD.svg" alt="Python 3.12+"></a>
  <a href="https://go.dev/"><img src="https://img.shields.io/badge/Go-1.21+-55BFFD.svg" alt="Go 1.21+"></a>
  <a href="https://hyperledger-fabric.readthedocs.io/"><img src="https://img.shields.io/badge/Hyperledger_Fabric-2.5-59C4FD.svg" alt="Hyperledger Fabric 2.5"></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-14+-5DC9FD.svg" alt="PostgreSQL 14+"></a>
  <a href="https://neo4j.com/"><img src="https://img.shields.io/badge/Neo4j-5.23-61CEFD.svg" alt="Neo4j 5.23"></a>
  <a href="https://redis.io/"><img src="https://img.shields.io/badge/Redis-7+-64D4FD.svg" alt="Redis 7+"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-26.1+-68D9FC.svg" alt="Docker"></a>
  <a href="https://www.keycloak.org/"><img src="https://img.shields.io/badge/Keycloak-24-6CDEFC.svg" alt="Keycloak 24"></a>
  <a href="https://www.vaultproject.io/"><img src="https://img.shields.io/badge/HashiCorp_Vault-1.16+-70E3FC.svg" alt="HashiCorp Vault"></a>
  <a href="https://grafana.com/"><img src="https://img.shields.io/badge/Grafana-11.0+-73E9FC.svg" alt="Grafana"></a>
  <a href="https://docs.astral.sh/ruff/"><img src="https://img.shields.io/badge/code_style-ruff-77EEFC.svg" alt="Code style: ruff"></a>
  <a href="https://docs.pytest.org/"><img src="https://img.shields.io/badge/tested_with-pytest-7BF3FC.svg" alt="Tested with pytest"></a>
</p>

<br>

## Pxtly

> **Pxtly**: turning regulatory trust into executable code. Compliance isn't bolted on, it endorses every transaction.

Pxtly is an institutional platform for tokenising Real World Assets on a permissioned Hyperledger Fabric network. It handles the full asset lifecycle from issuance to redemption, with built-in AML/KYC compliance, ZK-KYC identity proofs, FHE-based fraud scoring, and a RAG regulatory agent for MiCA queries.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [CLI](#cli)
- [API Reference](#api-reference)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Observability](#observability)
- [License](#license)

## Features

The Fabric network runs two organisations, **BANK01** (issuer) and **REG01** (regulator), each with a dedicated peer and CouchDB state database. The Go chaincode runs as Chaincode-as-a-Service and enforces a **2-of-2 endorsement policy** on every state-changing transaction. Assets move through an `ACTIF`, `GELE`, `EN_EMISSION`, `REMBOURSE` lifecycle recorded immutably on-chain, and Fabric events stream live via gRPC with automatic reconnection.

The platform embeds compliance directly into transaction execution and asset lifecycle management. Sanctions screening is backed by Ed25519-signed manifests with fuzzy PEP/UN/EU matching, while the MiCA enforcement layer validates exposure boundaries (Art. 68 thresholds), restricted asset classes, and supervisory reporting requirements. zk-KYC workflows enable cryptographic identity attestation through Merkle proofs without exposing underlying credentials. Encrypted fraud analytics powered by Fully Homomorphic Encryption (HElib CKKS) evaluate AML risk on confidential datasets, with persistent monitoring of KYC validity and systemic concentration exposure.

Pxtly exposes a FastAPI REST API and a gRPC server in parallel. Authentication is OIDC-based via Keycloak with PKCE (authorization_code flow). Private keys for Fabric identities are stored in HashiCorp Vault (KV v2, AppRole in production), and every response carries six security headers with rate limiting and trusted-proxy host filtering.

Every transaction produces an on-chain audit entry. An off-chain integrity checker verifies hashes independently, PDF audit reports are generated asynchronously via Celery + LaTeX, and the RAG agent answers regulatory questions by querying a ChromaDB vector store with a Groq-hosted LLM.

## Requirements

**API**

| Package | Version |
|---|---|
| Python | 3.12+ |
| FastAPI | 0.135+ |
| Celery | 5.6+ |
| SQLAlchemy | 2.0+ |
| grpcio | 1.78+ |
| pydantic-settings | 2.13+ |
| prometheus-client | 0.24+ |

**Technology Stack**

| Component | Role |
|---|---|
| Hyperledger Fabric 2.5 | Permissioned blockchain |
| PostgreSQL 14+ | Application database (Supabase in production, local PG for tests) |
| Redis 7+ | Cache and Celery broker |
| HashiCorp Vault | Fabric identity key storage (KV v2) |
| Keycloak 24 | OIDC SSO / PKCE authentication |
| Neo4j 5+ | Graph database for AML relationship analysis (Aura in production) |
| Docker + Compose | Peers, orderer, CouchDB, Keycloak, API, Celery containers |

## Quick Start

**Step 1: Clone and configure**

```bash
git clone https://github.com/zak-li/pxtly.git
cd pxtly
cp .env.example .env
```

Open `.env` and fill in at minimum `DATABASE_URL`, `REDIS_URL`, the `FABRIC_*` variables, and all `KEYCLOAK_*` variables.

**Step 2: Install dependencies**

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
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
cp .env.keycloak.example .env.keycloak    # fill in admin/DB credentials
bash deploy.sh
```

The `setup-realm.py` script prints a `KEYCLOAK_CLIENT_SECRET`. Copy it into your `.env`.

**Step 5: Start the API and worker**

```bash
docker compose up -d    # API + Celery worker
# Or without Docker:
uvicorn core.main:app --host 0.0.0.0 --port 8000 --workers 1
celery -A core.core.celery_app worker --loglevel=info -Q celery,compliance,reports,fabric_events
```

The API is live at `http://localhost:8000`. Swagger UI at `/docs`.

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

## CLI

Pxtly ships a Python CLI under [`cli/`](cli/) that mirrors every REST endpoint. It uses OAuth 2.0 Authorization Code + PKCE by default, stores tokens in the OS keyring, and writes a redacted audit line to `~/.pxtly/audit.log` for every command.

```bash
pip install -r cli/requirements.txt
python -m cli.main --help                      # 12 sub-apps
python -m cli.main auth login                  # PKCE flow (browser)
python -m cli.main assets list --status ACTIF
python -m cli.main events stream               # live SSE tail
python -m cli.main dashboard                   # full-screen Textual TUI
```

Configuration precedence: `PXTLY_*` env vars, then `~/.pxtly/config.json`, then defaults. Sub-apps: `auth`, `assets`, `tx`, `audit`, `compliance`, `zkp`, `tribunal`, `orgs`, `agent`, `events`, `system`, `dashboard`.

## API Reference

REST root: `/api/v1`. Every endpoint requires a valid OIDC access token unless marked *public*.

**Authentication (OIDC / PKCE)**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/auth/login` | Redirect to Keycloak login (PKCE). *public* |
| GET | `/auth/callback` | OIDC callback, exchanges code for tokens. *public* |
| POST | `/auth/refresh` | Refresh access token via cookie |
| POST | `/auth/logout` | Revoke session (clear cookies + Keycloak) |
| GET | `/auth/me` | Current user profile |
| GET | `/auth/me/export` | GDPR Art. 15 personal data export |
| DELETE | `/auth/me` | GDPR Art. 17 right to erasure |

**Assets**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/assets` | List assets with filtering |
| GET | `/assets/{id}` | Get one asset |
| GET | `/assets/{id}/history` | On-chain provenance history |
| GET | `/assets/{id}/valuations` | Valuation history |
| POST | `/assets/tokenize` | Tokenise a new real-world asset (BANK01MSP) |
| POST | `/assets/transfer` | Transfer ownership (BANK01MSP) |
| POST | `/assets/freeze` | Freeze (REG01MSP) |
| POST | `/assets/unfreeze` | Unfreeze (REG01MSP) |
| POST | `/assets/{id}/valuate` | Record a valuation point |

**Compliance, KYC, ZKP**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/compliance` | Compliance dashboard summary |
| GET | `/compliance/alerts/active` | Active AML / sanctions alerts |
| GET | `/compliance/{user_id}` | Per-user compliance status |
| POST | `/compliance/kyc/submit` | Submit KYC document hashes |
| POST | `/compliance/kyc/approve` | Approve / reject KYC submission |
| POST | `/compliance/screening/run` | Run AML sanctions screening |
| POST | `/zkp/setup-key` | Issue ZK-KYC credential |
| POST | `/zkp/verify` | Verify a Schnorr proof |
| GET | `/zkp/status` | ZKP subsystem health |
| POST | `/zkp/revoke/{credential_id}` | Revoke a credential |

**Audit, Transactions, Events, Tribunal**

| Method | Endpoint | Description |
|---|---|---|
| GET | `/audit` | Paginated audit log |
| GET | `/audit/asset/{id}` | On-chain provenance trail for an asset |
| POST | `/audit/report/generate/{id}` | Generate PDF audit report (async) |
| GET | `/audit/report/status/{task_id}` | Check report generation status |
| POST | `/audit/fraud/scan` | Trigger Neo4j fraud graph scan |
| GET | `/transactions` | List transactions |
| GET | `/transactions/{tx_ref}` | Lookup a transaction by reference |
| GET | `/transactions/stats/summary` | Transaction statistics summary |
| GET | `/events/stream` | Live Fabric event stream (SSE) |
| POST | `/tribunal/vote/commit` | Commit a hashed regulator vote |
| POST | `/tribunal/vote/reveal` | Reveal vote + nonce |
| POST | `/tribunal/session/{id}/tally` | Tally a closed session |

**Agent and Organisations**

| Method | Endpoint | Description |
|---|---|---|
| POST | `/agent/chat` | RAG query over the regulatory knowledge base |
| GET | `/agent/search` | Top-K semantic search over the corpus |
| GET | `/agent/status` | RAG subsystem health |
| POST | `/agent/index` | Re-index the corpus (admin only) |
| GET | `/organizations` | List organisations |
| GET | `/organizations/users` | List users (filter by role / country) |
| GET | `/organizations/{org_id}/portfolio` | Per-org portfolio aggregate |
| GET | `/metrics` | Prometheus metrics. *public* |

## Environment Variables

**Required**

| Variable | Description |
|---|---|
| `ENVIRONMENT` | `production`, `staging`, or `development` |
| `DATABASE_URL` | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis URL (`redis://:password@host:6379/0`) |
| `KEYCLOAK_URL` | Keycloak base URL (`https://host:8443`) |
| `KEYCLOAK_CLIENT_SECRET` | OIDC client secret (printed by `setup-realm.py`) |
| `KEYCLOAK_CALLBACK_URL` | Where Keycloak redirects after login. Must match the API's public URL |
| `FABRIC_WALLET_PATH` | Path to `fabric_wallet.json` |
| `FABRIC_CONNECTION_PROFILE` | Path to `connection_profile.yaml` |
| `FABRIC_CHANNEL` | Fabric channel name (`rwa-channel`) |
| `FABRIC_CHAINCODE` | Chaincode name (`rwa-token`) |
| `VAULT_ADDR` | HashiCorp Vault address (`http://host:8200`) |
| `VAULT_TOKEN` | Vault authentication token (for wallet KV access; metrics scrape uses `unauthenticated_metrics_access = true` in `vault.hcl`) |
| `NEO4J_URI` | Neo4j bolt URI (`neo4j+s://<id>.databases.neo4j.io` for Aura) |
| `NEO4J_USER` / `NEO4J_PASS` | Neo4j credentials |

**Optional**

| Variable | Default | Description |
|---|---|---|
| `KEYCLOAK_REALM` | `pxtly` | Keycloak realm name |
| `KEYCLOAK_CLIENT_ID` | `pxtly-api` | OIDC client identifier |
| `KEYCLOAK_VERIFY_TLS` | `false` | Verify Keycloak TLS certificate |
| `KEYCLOAK_CA_CERT_PATH` | | Path to pinned CA for Keycloak TLS (self-signed cert deployments) |
| `NEO4J_DATABASE` | `neo4j` | Neo4j database name (set to the Aura instance ID when using Aura) |
| `GROQ_API_KEY` | `""` | Groq API key for the regulatory agent |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model ID |
| `FABRIC_TLS_ENABLED` | `true` | TLS for Fabric gRPC |
| `FABRIC_GRPC_TIMEOUT` | `30` | gRPC timeout in seconds |
| `FABRIC_RETRY_MAX_ATTEMPTS` | `5` | Retry attempts on Fabric errors |
| `PLATFORM_ZKP_SECRET` | | Strong secret for ZK credential signing (rejected in production if dev default) |
| `SANCTIONS_MANIFEST_PUBKEY_HEX` | | Ed25519 pubkey (64 hex chars) verifying the sanctions manifest signature |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ALLOWED_ORIGINS` | | Comma-separated CORS origins |

The full list lives in [`.env.example`](.env.example).

## Project Structure

The repository is organised by responsibility: application code, the Fabric consortium, side services, persistence, and tooling each live under their own top-level directory.

### Application code

```
core/                         # FastAPI + Celery, application backend
├── main.py                   # ASGI entry, middleware, metrics
├── config.py                 # pydantic-settings root
├── features/
│   ├── assets/               # Asset lifecycle (issue, transfer, freeze)
│   ├── compliance/           # AML / KYC / MiCA rules
│   ├── audit/                # On-chain trail, integrity, PDF reports
│   ├── auth/                 # Keycloak OIDC + PKCE + GDPR
│   ├── zkp/                  # ZK-KYC Schnorr proofs
│   ├── fhe/                  # HElib CKKS fraud scorer
│   └── agent/                # RAG pipeline + ChromaDB
├── fabric_client/            # Wallet, events, retry, circuit breaker
├── grpc_server/              # gRPC servicers
└── grpc_generated/           # protoc-generated stubs

chaincode/                    # Go smart contract (rwa-token, CCaaS)

cli/                          # Pxtly CLI (Typer + Rich + Textual)
├── api/                      # One client per REST resource
├── commands/                 # One Typer sub-app per domain
├── http/                     # Transport + auto-refresh on 401
├── security/                 # Keyring tokens, PKCE, audit log
└── ui/                       # Rich console, REPL, dashboard
```

### Consortium and side services

```
fabric/                       # Hyperledger Fabric 2.5 network
├── config/                   # configtx, connection profile, MSP material
├── docker/                   # Peers, orderer, CouchDB compose
└── scripts/                  # deploy-chaincode.sh

stack/                        # Side services (run alongside the API)
├── keycloak/                 # Compose, TLS, identity-first flow
├── monitoring/               # Prometheus, Grafana, Loki, Promtail
└── vault/                    # Policy + hcl config
```

### Persistence and tooling

```
db/                           # Schema, seeds, Alembic migrations
├── migrations/               # alembic env + versions/
├── sql/                      # 01_schema to 08_zkp_tables
└── fixtures/                 # csv/, json/ (sanctions manifest)

proto/                        # gRPC service definitions (.proto)

scripts/                      # Operational scripts (Python + bash)
├── benchmarks/               # fhe.py, zkp.py
├── simulations/              # dashboard.py, full.py, jitter.py, game_theory.py
├── seed_db.py                # Apply SQL seeds + compliance fixtures
├── health_check.py           # Liveness probe for CI / oncall
├── generate_report.py        # Build a sample audit PDF locally
├── generate_protos.sh        # Regenerate Python gRPC stubs
└── install_latex.sh          # Install LaTeX deps (TeX Live)

tests/                        # pytest suite + fixtures
```

### Repository root

`.github/` (assets + CI), `.env.example`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `pyproject.toml`, `alembic.ini`, plus the metadata files (`README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`).

## Observability

Pxtly ships a full monitoring stack deployed via Docker Compose. **Prometheus** scrapes twelve targets: the API itself, Fabric peers (BANK01 + REG01), CouchDB for each peer, Keycloak, Vault, Redis, PostgreSQL, node-exporter, the Celery exporter, and Prometheus itself. **Grafana** renders one curated dashboard covering service health, API throughput / latency percentiles, infrastructure utilisation, datastores, blockchain activity, and compliance metrics. **Loki** aggregates structured JSON logs from the API container, Celery worker, Fabric peers, and the host's systemd journal.

The dashboard is auto-provisioned from [`stack/monitoring/grafana_dashboard.json`](stack/monitoring/grafana_dashboard.json) via the file provider in [`stack/monitoring/grafana-provisioning/`](stack/monitoring/grafana-provisioning/). Datasource UIDs are pinned (`ffgx1hbr25a0wc` for Prometheus, `loki` for Loki) so the dashboard JSON is portable across deployments.

| Component | Port |
|---|---|
| Prometheus | 9090 |
| Grafana | 3000 |
| Loki | 3100 |
| Node Exporter | 9100 |
| Redis Exporter | 9121 |
| Postgres Exporter | 9187 |
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

This project is licensed under the [Apache License 2.0](LICENSE). Vulnerability reports: see [SECURITY.md](SECURITY.md). Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md).
