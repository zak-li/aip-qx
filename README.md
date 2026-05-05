<p align="center">
  <img src="assets/logo.svg" alt="RWA Platform Logo" width="400">
</p>

<br>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python Version"></a>
  <a href="https://hyperledger-fabric.readthedocs.io/"><img src="https://img.shields.io/badge/Hyperledger_Fabric-2.5-2F3134.svg" alt="Fabric Version"></a>
  <a href="https://go.dev/"><img src="https://img.shields.io/badge/Go-1.21+-00ADD8.svg" alt="Go Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License"></a>
</p>

<br>

## RWA Platform

Institutional-grade Real World Asset tokenization on a permissioned Hyperledger Fabric network. Manage the full asset lifecycle — issuance, transfer, compliance, audit — with on-chain immutability, ZK-KYC proofs, AML/KYC screening, and a RAG-powered regulatory agent.

## Features

- **Hyperledger Fabric** — permissioned two-org network (BNPParibas + AMFRegulateur), Go chaincode deployed as CCaaS
- **Asset Lifecycle** — tokenize, transfer, and redeem real-world assets with ledger-backed state
- **AML / KYC Compliance** — sanctions screening, MiCA rules engine, KYC expiry tracking, risk scoring
- **ZK-KYC** — Merkle-based zero-knowledge proofs for privacy-preserving identity verification
- **FHE Fraud Scoring** — Fully Homomorphic Encryption scorer for confidential risk evaluation
- **Regulatory Audit** — immutable audit trail, integrity checker, PDF report generation via Celery
- **RAG Agent** — Groq LLM + ChromaDB vector store for regulatory Q&A over the knowledge base
- **gRPC + REST** — dual transport: FastAPI REST API and gRPC server for inter-service communication
- **Observability** — Prometheus metrics, Grafana dashboards, Loki log aggregation, custom Celery exporter

## Quick Start

```bash
git clone https://github.com/hackerXcore/blockchain_assets.git
cd blockchain_assets

cp .env.example .env
# Fill in required variables (see Environment Variables below)

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Start the Fabric network:

```bash
cd network
./scripts/network-up.sh
./scripts/create-channel.sh
./scripts/deploy-chaincode.sh
```

Start the API:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Interactive docs at `/docs` (Swagger UI) or `/redoc`.

## API Reference

| Method | Prefix | Description |
|---|---|---|
| `*` | `/api/v1/auth` | JWT authentication, organization management |
| `*` | `/api/v1/assets` | Asset issuance, transfer, redemption |
| `*` | `/api/v1/transactions` | Ledger transaction history |
| `*` | `/api/v1/organizations` | Network organization registry |
| `*` | `/api/v1/audit` | Regulatory audit trail and PDF reports |
| `*` | `/api/v1/compliance` | AML screening, KYC verification, MiCA rules |
| `*` | `/api/v1/zkp` | ZK-KYC proof issuance and verification |
| `*` | `/api/v1/agent` | RAG agent for regulatory queries |
| `*` | `/api/v1/events` | Live Fabric event stream (SSE) |
| GET | `/metrics` | Prometheus metrics endpoint |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | JWT signing key (min 32 chars) |
| `DATABASE_URL` | Yes | PostgreSQL async connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `FABRIC_WALLET_PATH` | Yes | Path to `fabric_wallet.json` |
| `FABRIC_CONNECTION_PROFILE` | Yes | Path to `connection_profile.yaml` |
| `FABRIC_CHANNEL` | Yes | Fabric channel name |
| `FABRIC_CHAINCODE` | Yes | Chaincode name |
| `VAULT_ADDR` | Yes | HashiCorp Vault address |
| `VAULT_TOKEN` | Yes | Vault authentication token |
| `GROQ_API_KEY` | No | Groq API key for the RAG agent |

## Project Structure

```
blockchain_assets/
├── backend/
│   ├── main.py                  # FastAPI app, middleware, Prometheus metrics
│   ├── config.py                # pydantic-settings configuration
│   ├── features/
│   │   ├── assets/              # Asset lifecycle (models, service, router)
│   │   ├── transactions/        # Ledger transaction queries
│   │   ├── compliance/          # AML, KYC, MiCA rules engine
│   │   ├── audit/               # Audit trail, integrity checker, report generator
│   │   ├── zkp/                 # ZK-KYC proof issuer and Merkle logic
│   │   ├── fhe/                 # FHE fraud scorer
│   │   └── agent/               # RAG pipeline, Groq client, ChromaDB vector store
│   ├── fabric_client/           # Fabric network client, wallet, event listener, retry/circuit-breaker
│   └── grpc_server/             # gRPC servicers (assets, transactions, audit, compliance, agent)
├── chaincode/rwa-token/         # Go chaincode (CCaaS)
├── network/
│   ├── config/                  # core.yaml, connection_profile.yaml, configtx.yaml
│   ├── docker/                  # docker-compose.yaml (peers, orderer, CouchDB)
│   └── scripts/                 # network-up, channel, chaincode, enroll scripts
├── deployment/
│   ├── systemd/                 # rwa-uvicorn, rwa-celery, rwa-grpc service units
│   └── monitoring/              # Prometheus, Grafana, Loki, Celery exporter
└── database/migrations/         # Alembic migrations
```

## License

This project is licensed under the [Apache License 2.0](LICENSE).
