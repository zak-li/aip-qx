"""
AIP Qx -- Full-stack Grafana Dashboard Simulation
================================================
Exercises every endpoint surface so that ALL Grafana panels populate with
realistic data: HTTP throughput, latency histograms, Celery queues, custom
rwa_* metrics, error rates, ZK-KYC flows, RAG agent, SSE streams, fraud
scans and audit report generation.

Phases run sequentially. Each phase targets a specific dashboard area:

    1. setup        -> auth + ZKP setup-key + agent readiness
    2. kyc-wave     -> KYC submissions (compliance writes)
    3. tokenize     -> diverse asset mints (rwa_assets_by_status, http)
    4. screening    -> AML screening burst (rwa_aml_score_avg, blocks)
    5. trading      -> transfers + valuations + history reads
    6. async-heavy  -> audit report + fraud scan (Celery queues)
    7. agent        -> RAG chat (Groq circuit breaker, latency)
    8. sse          -> concurrent /events/stream subscribers
    9. freeze       -> compliance freeze/unfreeze cycle
   10. zkp-verify   -> bogus proofs to populate 400 metrics
   11. errors       -> deliberate 404/422/403 traffic
   12. cooldown     -> mixed reads + health + /metrics scrape

Usage:
    python scripts/simulate_full.py                  # full run, ~5 min
    python scripts/simulate_full.py --quick          # ~90s
    python scripts/simulate_full.py --concurrency 16 # higher load
    python scripts/simulate_full.py --skip sse,agent

Environment:
    API_URL              default http://localhost:8000
    SIM_USER_EMAIL       login email (admin/compliance officer recommended)
    SIM_USER_PASSWORD    login password
    SIM_USER_ID          UUID of the simulated user for compliance reads
    SIM_COUNTERPARTY_ID  UUID used in screening flows
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import secrets
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date

try:
    import httpx
except ImportError:
    import subprocess
    # Self-bootstrap install — args are hard-coded, no user input.
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])  # noqa: S603
    import httpx

try:
    from cryptography.hazmat.primitives.asymmetric import ec
except ImportError:
    ec = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
SIM_EMAIL = os.environ.get("SIM_USER_EMAIL", "thomas.martin@bank01.com")
SIM_PASSWORD = os.environ.get("SIM_USER_PASSWORD", "")
SIM_USER_ID = os.environ.get("SIM_USER_ID", "a0000001-0001-0001-0001-000000000001")
SIM_COUNTERPARTY_ID = os.environ.get(
    "SIM_COUNTERPARTY_ID", "a0000002-0002-0002-0002-000000000002"
)

ASSET_TYPES = [
    "OBLIGATION", "OPCVM", "IMMOBILIER", "DERIVE", "MATIERE_PREMIERE", "PRIVATE_EQUITY",
]
ASSET_PREFIX = {
    "OBLIGATION": "OBL", "OPCVM": "OPC", "IMMOBILIER": "IMM",
    "DERIVE": "DER", "MATIERE_PREMIERE": "MPR", "PRIVATE_EQUITY": "PE",
}
ASSET_NAMES = {
    "OBLIGATION":       ["OAT 3.75% 2030", "BTP 4.0% 2028", "BUND 2.5% 2031", "Gilt 4.25% 2032"],
    "OPCVM":            ["MSCI World Tracker", "CAC 40 ETF", "Euro Corporate Bond Fund"],
    "IMMOBILIER":       ["Tour Montparnasse SCPI", "La Defense Plaza", "Logistique Portfolio"],
    "DERIVE":           ["OAT Future Dec 2026", "EUR/USD 3M Forward", "CDS BANK01 5Y"],
    "MATIERE_PREMIERE": ["Gold Bullion Token", "Crude Oil WTI Q4", "Wheat Index Fund"],
    "PRIVATE_EQUITY":   ["LBO Tech Fund III", "Growth Capital SCPI", "Infra Debt 2027"],
}

AGENT_QUESTIONS = [
    "Quelles sont les obligations MiCA pour un émetteur d'EMT ?",
    "Comment fonctionne le seuil de reporting REG01 pour un transfert > 10M EUR ?",
    "Quel est le délai légal pour signaler une suspicion de blanchiment ?",
    "Quelles sont les exigences de couverture en capital pour un CASP ?",
    "Différence entre token utilitaire et security token sous MiCA ?",
    "Quel KYC niveau 3 selon les normes GAFI ?",
]

DOC_TYPES = ["PASSPORT", "ID_CARD", "PROOF_OF_ADDRESS", "BANK_STATEMENT", "TAX_FORM"]
ISSUING_COUNTRIES = ["FR", "DE", "IT", "ES", "BE", "LU", "NL", "PT"]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

COLORS = {
    "g": "\033[92m", "y": "\033[93m", "r": "\033[91m", "b": "\033[94m",
    "c": "\033[96m", "m": "\033[95m", "bold": "\033[1m", "dim": "\033[2m",
    "reset": "\033[0m",
}


def col(name: str, text: str) -> str:
    return f"{COLORS[name]}{text}{COLORS['reset']}"


def banner(title: str) -> None:
    width = 74
    line = "=" * width
    print()
    print(col("bold", line))
    print(col("bold", f"  {title}"))
    print(col("bold", line))


def section(title: str) -> None:
    print()
    print(col("m", f"-- {title} ").ljust(74, "-"))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class PhaseStats:
    name: str
    requests: int = 0
    ok: int = 0
    errors: int = 0
    elapsed: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class GlobalStats:
    start: float = 0.0
    phases: list[PhaseStats] = field(default_factory=list)
    assets_minted: list[str] = field(default_factory=list)
    tasks_dispatched: list[str] = field(default_factory=list)

    def add(self, phase: PhaseStats) -> None:
        self.phases.append(phase)

    @property
    def total_requests(self) -> int:
        return sum(p.requests for p in self.phases)

    @property
    def total_ok(self) -> int:
        return sum(p.ok for p in self.phases)

    @property
    def total_errors(self) -> int:
        return sum(p.errors for p in self.phases)


STATS = GlobalStats()


# ---------------------------------------------------------------------------
# Generic HTTP wrapper that increments phase stats
# ---------------------------------------------------------------------------

async def hit(
    client: httpx.AsyncClient,
    phase: PhaseStats,
    method: str,
    path: str,
    *,
    headers: dict | None = None,
    json_body: dict | None = None,
    timeout: float = 15.0,  # noqa: ASYNC109 - per-call HTTP deadline, forwarded to httpx
    accept_codes: tuple[int, ...] = (200, 201, 202, 204),
) -> httpx.Response | None:
    url = f"{BASE_URL}{path}"
    phase.requests += 1
    try:
        resp = await client.request(
            method, url, headers=headers, json=json_body, timeout=timeout,
        )
        if resp.status_code in accept_codes:
            phase.ok += 1
        else:
            phase.errors += 1
        return resp
    except Exception:
        phase.errors += 1
        return None


# ---------------------------------------------------------------------------
# Crypto helper (secp256r1 fallback — server only validates hex shape for sim)
# ---------------------------------------------------------------------------

def fresh_pubkey() -> tuple[str, str]:
    """Generate a fresh secp256k1-style public key (x, y) in hex.

    Server accepts any 64-hex coordinates; we use real EC keygen when available
    for realism, otherwise random bytes.
    """
    if ec is not None:
        try:
            sk = ec.generate_private_key(ec.SECP256K1())
            nums = sk.public_key().public_numbers()
            return f"{nums.x:064x}", f"{nums.y:064x}"
        except Exception:  # noqa: S110 - fall back to random hex when EC unavailable
            pass
    return secrets.token_hex(32), secrets.token_hex(32)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

async def login(client: httpx.AsyncClient) -> str | None:
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": SIM_EMAIL, "password": SIM_PASSWORD},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("access_token") or data.get("token")
        print(col("r", f"  login failed: {resp.status_code} -- {resp.text[:200]}"))
    except Exception as exc:
        print(col("r", f"  login error: {exc}"))
    return None


# ---------------------------------------------------------------------------
# Phase 1 -- ZKP setup-key + agent readiness
# ---------------------------------------------------------------------------

async def phase_setup(client: httpx.AsyncClient, headers: dict) -> PhaseStats:
    p = PhaseStats("setup")
    section("Phase 1 -- ZKP setup-key + agent readiness")
    start = time.time()

    px, py = fresh_pubkey()
    resp = await hit(
        client, p, "POST", "/api/v1/zkp/setup-key",
        headers=headers, json_body={"public_key_x": px, "public_key_y": py},
    )
    issued = bool(resp and resp.status_code in (200, 201))
    p.extra["credential_issued"] = issued

    await hit(client, p, "GET", "/api/v1/zkp/status", headers=headers, accept_codes=(200,))
    await hit(client, p, "GET", "/api/v1/agent/status", headers=headers, accept_codes=(200,))
    await hit(client, p, "GET", "/health", accept_codes=(200,))
    await hit(client, p, "GET", "/metrics", accept_codes=(200,))

    p.elapsed = time.time() - start
    print(f"  credential issued : {col('g', 'yes') if issued else col('y', 'no (replay or perms)')}")
    print(f"  ok/err            : {col('g', str(p.ok))} / {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 2 -- KYC submission wave
# ---------------------------------------------------------------------------

async def phase_kyc(client: httpx.AsyncClient, headers: dict, count: int) -> PhaseStats:
    p = PhaseStats("kyc-wave")
    section(f"Phase 2 -- KYC submission wave ({count} docs)")
    start = time.time()

    tasks = []
    for _ in range(count):
        tasks.append(hit(
            client, p, "POST", "/api/v1/compliance/kyc/submit",
            headers=headers,
            json_body={
                "user_id": SIM_USER_ID,
                "document_type": random.choice(DOC_TYPES),
                "file_hash": secrets.token_hex(32),
                "document_number": f"DOC-{secrets.token_hex(4).upper()}",
                "issuing_country": random.choice(ISSUING_COUNTRIES),
            },
            accept_codes=(200, 201, 409),
        ))
    await asyncio.gather(*tasks, return_exceptions=True)

    await hit(client, p, "GET", "/api/v1/compliance/alerts/active",
              headers=headers, accept_codes=(200,))
    await hit(client, p, "GET", "/api/v1/compliance", headers=headers, accept_codes=(200,))

    p.elapsed = time.time() - start
    print(f"  submissions : {col('c', str(count))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 3 -- Tokenization burst
# ---------------------------------------------------------------------------

def make_asset_payload(seq: int) -> dict:
    atype = random.choice(ASSET_TYPES)
    prefix = ASSET_PREFIX[atype]
    year = random.randint(2024, 2026)
    asset_id = f"RWA-{prefix}-SIM-{year}-{(seq % 1000):03d}"
    issuance = date(year, random.randint(1, 12), random.randint(1, 28))
    nominal = random.choice([5_000_000, 10_000_000, 25_000_000, 50_000_000, 100_000_000])
    return {
        "asset_id": asset_id,
        "isin": f"FR{uuid.uuid4().hex[:10].upper()}"[:12],
        "asset_type": atype,
        "asset_name": f"{random.choice(ASSET_NAMES[atype])} #{seq}",
        "issuer_lei": f"969500{uuid.uuid4().hex[:14].upper()}",
        "nominal_value": float(nominal),
        "currency": random.choice(["EUR", "EUR", "EUR", "USD", "GBP"]),
        "issuance_date": issuance.isoformat(),
        "justification": "Full-sim tokenization batch",
    }


async def phase_tokenize(
    client: httpx.AsyncClient, headers: dict, count: int, concurrency: int,
) -> PhaseStats:
    p = PhaseStats("tokenize")
    section(f"Phase 3 -- Tokenization burst ({count} assets, concurrency={concurrency})")
    start = time.time()

    sem = asyncio.Semaphore(concurrency)

    async def mint(seq: int) -> None:
        payload = make_asset_payload(seq)
        async with sem:
            resp = await hit(
                client, p, "POST", "/api/v1/assets/tokenize",
                headers=headers, json_body=payload,
                accept_codes=(200, 201),
            )
            if resp and resp.status_code in (200, 201):
                STATS.assets_minted.append(payload["asset_id"])

    await asyncio.gather(*[mint(i) for i in range(1, count + 1)], return_exceptions=True)

    # Diverse reads for /assets panel
    for _ in range(min(count, 20)):
        await hit(client, p, "GET", "/api/v1/assets", headers=headers, accept_codes=(200,))

    p.elapsed = time.time() - start
    p.extra["assets_created"] = len(STATS.assets_minted)
    print(f"  minted : {col('y', str(len(STATS.assets_minted)))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 4 -- AML screening burst
# ---------------------------------------------------------------------------

async def phase_screening(client: httpx.AsyncClient, headers: dict, count: int) -> PhaseStats:
    p = PhaseStats("screening")
    section(f"Phase 4 -- AML screening burst ({count} runs)")
    start = time.time()

    tasks = []
    for _ in range(count):
        tasks.append(hit(
            client, p, "POST", "/api/v1/compliance/screening/run",
            headers=headers,
            json_body={
                "user_id": SIM_USER_ID,
                "amount": float(random.choice([5_000, 50_000, 250_000, 1_000_000, 12_000_000])),
                "counterparty_id": SIM_COUNTERPARTY_ID,
            },
            timeout=20,
            accept_codes=(200, 201, 202),
        ))
        tasks.append(hit(
            client, p, "GET", f"/api/v1/compliance/{SIM_USER_ID}",
            headers=headers, accept_codes=(200, 404),
        ))
    await asyncio.gather(*tasks, return_exceptions=True)

    p.elapsed = time.time() - start
    print(f"  screenings : {col('c', str(count))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 5 -- Trading: transfers + valuations + history
# ---------------------------------------------------------------------------

async def phase_trading(
    client: httpx.AsyncClient, headers: dict, transfers: int, concurrency: int,
) -> PhaseStats:
    p = PhaseStats("trading")
    section(f"Phase 5 -- Trading wave ({transfers} transfers)")
    start = time.time()

    if not STATS.assets_minted:
        print(col("y", "  no assets available, skipping"))
        p.elapsed = time.time() - start
        return p

    sem = asyncio.Semaphore(concurrency)

    async def trade(_: int) -> None:
        asset_id = random.choice(STATS.assets_minted)
        async with sem:
            await hit(
                client, p, "POST", "/api/v1/assets/transfer",
                headers=headers,
                json_body={
                    "asset_id": asset_id,
                    "to_owner": f"AMF_REG_{secrets.token_hex(4).upper()}",
                    "price": float(random.randint(1_000_000, 80_000_000)),
                    "justification": "Full-sim secondary market transfer",
                },
                accept_codes=(200, 201, 409),
            )
            await hit(
                client, p, "POST", f"/api/v1/assets/{asset_id}/valuate",
                headers=headers,
                json_body={
                    "valuation": float(random.randint(900_000, 120_000_000)),
                    "currency": "EUR",
                    "method": random.choice(["DCF", "MARK_TO_MARKET", "COMPARABLES"]),
                    "justification": "quarterly mark",
                },
                accept_codes=(200, 201, 202, 422),
            )
            await hit(
                client, p, "GET", f"/api/v1/assets/{asset_id}/history",
                headers=headers, accept_codes=(200, 404),
            )

    await asyncio.gather(*[trade(i) for i in range(transfers)], return_exceptions=True)
    await hit(client, p, "GET", "/api/v1/transactions",
              headers=headers, accept_codes=(200,))
    await hit(client, p, "GET", "/api/v1/transactions/stats/summary",
              headers=headers, accept_codes=(200,))

    p.elapsed = time.time() - start
    print(f"  transfers : {col('c', str(transfers))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 6 -- Async-heavy: Celery report + fraud scan
# ---------------------------------------------------------------------------

async def phase_async_heavy(
    client: httpx.AsyncClient, headers: dict, reports: int, scans: int,
) -> PhaseStats:
    p = PhaseStats("async-heavy")
    section(f"Phase 6 -- Async workload ({reports} reports, {scans} fraud scans)")
    start = time.time()

    task_ids: list[str] = []

    # Generate audit reports -> Celery reports queue
    sample_assets = STATS.assets_minted[: max(1, reports)] or [f"RWA-OBL-SIM-2026-{i:03d}" for i in range(1, reports + 1)]
    for asset_id in sample_assets[:reports]:
        resp = await hit(
            client, p, "POST", f"/api/v1/audit/report/generate/{asset_id}",
            headers=headers, accept_codes=(200, 202),
        )
        if resp is not None and resp.status_code in (200, 202):
            try:
                tid = resp.json().get("task_id")
                if tid:
                    task_ids.append(tid)
                    STATS.tasks_dispatched.append(tid)
            except Exception:  # noqa: S110 - malformed body shouldn't abort the run
                pass

    # Fraud graph scan -> Celery compliance queue
    for _ in range(scans):
        await hit(client, p, "POST", "/api/v1/audit/fraud/scan",
                  headers=headers, accept_codes=(200, 202))

    # Poll a subset of task statuses (drives /audit/report/status traffic)
    for tid in task_ids[:8]:
        await hit(client, p, "GET", f"/api/v1/audit/report/status/{tid}",
                  headers=headers, accept_codes=(200, 404))

    await hit(client, p, "GET", "/api/v1/audit", headers=headers, accept_codes=(200,))

    p.elapsed = time.time() - start
    p.extra["tasks"] = len(task_ids)
    print(f"  tasks queued : {col('y', str(len(task_ids)))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 7 -- RAG agent chat burst
# ---------------------------------------------------------------------------

async def phase_agent(
    client: httpx.AsyncClient, headers: dict, queries: int,
) -> PhaseStats:
    p = PhaseStats("agent")
    section(f"Phase 7 -- RAG agent chat ({queries} queries)")
    start = time.time()

    tasks = []
    for _ in range(queries):
        question = random.choice(AGENT_QUESTIONS)
        tasks.append(hit(
            client, p, "POST", "/api/v1/agent/chat",
            headers=headers,
            json_body={
                "message": question,
                "stream": False,
                "use_rag": True,
                "n_results": 4,
                "max_tokens": 512,
                "temperature": 0.3,
            },
            timeout=45.0,
            accept_codes=(200, 500, 503),  # 5xx accepted -> still exercises circuit breaker
        ))
        tasks.append(hit(
            client, p, "GET", "/api/v1/agent/search",
            headers={**headers},
            accept_codes=(200, 422),
        ))
    # search needs query param; do them separately
    for _ in range(queries):
        await hit(
            client, p, "GET", f"/api/v1/agent/search?query={random.choice(AGENT_QUESTIONS).split()[0]}&n=3",
            headers=headers, accept_codes=(200, 422),
        )
    await asyncio.gather(*tasks, return_exceptions=True)

    p.elapsed = time.time() - start
    print(f"  queries : {col('c', str(queries))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 8 -- SSE concurrent subscribers
# ---------------------------------------------------------------------------

async def phase_sse(
    client: httpx.AsyncClient, headers: dict, subscribers: int, hold_seconds: float,
) -> PhaseStats:
    p = PhaseStats("sse")
    section(f"Phase 8 -- SSE subscribers ({subscribers} streams, {hold_seconds:.0f}s hold)")
    start = time.time()

    async def subscribe(idx: int) -> None:
        p.requests += 1
        try:
            async with client.stream(
                "GET", f"{BASE_URL}/api/v1/events/stream",
                headers=headers, timeout=hold_seconds + 5,
            ) as resp:
                if resp.status_code != 200:
                    p.errors += 1
                    return
                received = 0
                deadline = time.time() + hold_seconds
                async for _ in resp.aiter_lines():
                    received += 1
                    if time.time() >= deadline:
                        break
                p.ok += 1
                p.extra[f"sub_{idx}_events"] = received
        except Exception:
            p.errors += 1

    await asyncio.gather(*[subscribe(i) for i in range(subscribers)], return_exceptions=True)

    p.elapsed = time.time() - start
    print(f"  streams : {col('c', str(subscribers))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 9 -- Freeze / unfreeze cycle
# ---------------------------------------------------------------------------

async def phase_freeze(
    client: httpx.AsyncClient, headers: dict, count: int,
) -> PhaseStats:
    p = PhaseStats("freeze")
    section(f"Phase 9 -- Freeze cycle ({count} ops)")
    start = time.time()

    if not STATS.assets_minted:
        print(col("y", "  no assets available, skipping"))
        p.elapsed = time.time() - start
        return p

    sample = random.sample(
        STATS.assets_minted, k=min(count, len(STATS.assets_minted))
    )
    for asset_id in sample:
        await hit(
            client, p, "POST", "/api/v1/assets/freeze",
            headers=headers,
            json_body={
                "asset_id": asset_id,
                "reason": "Full-sim regulatory freeze (AML threshold)",
                "regulatory_ref": f"REG01-AML-{date.today().year}-{random.randint(100, 999)}",
            },
            accept_codes=(200, 201, 409),
        )

    # Unfreeze a portion to keep the asset population diverse
    for asset_id in sample[: max(1, count // 3)]:
        await hit(
            client, p, "POST", "/api/v1/assets/unfreeze",
            headers=headers,
            json_body={
                "asset_id": asset_id,
                "reason": "Full-sim screening cleared",
                "regulatory_ref": f"REG01-CLR-{date.today().year}-{random.randint(100, 999)}",
            },
            accept_codes=(200, 201, 409),
        )

    p.elapsed = time.time() - start
    print(f"  ops : {col('c', str(count))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 10 -- ZKP verify with bogus proofs (drives 400 metrics intentionally)
# ---------------------------------------------------------------------------

async def phase_zkp_verify(
    client: httpx.AsyncClient, headers: dict, attempts: int,
) -> PhaseStats:
    p = PhaseStats("zkp-verify")
    section(f"Phase 10 -- ZKP verify load ({attempts} attempts, expected 400s)")
    start = time.time()

    for _ in range(attempts):
        px, py = fresh_pubkey()
        rx, ry = fresh_pubkey()
        await hit(
            client, p, "POST", "/api/v1/zkp/verify",
            headers=headers,
            json_body={
                "public_key_x": px, "public_key_y": py,
                "proof_Rx": rx, "proof_Ry": ry,
                "proof_s": secrets.token_hex(32),
                "purpose": random.choice(["asset_transfer", "kyc_proof", "age_check"]),
                "context": f"sim-{secrets.token_hex(8)}",
                "nullifier": secrets.token_hex(32),
                "credential_claim": {"kyc_level": 2, "age_ok": True},
                "credential_sig": secrets.token_hex(64),
            },
            accept_codes=(400,),  # bogus proofs SHOULD be rejected
        )
        await hit(client, p, "GET", "/api/v1/zkp/status",
                  headers=headers, accept_codes=(200,))

    p.elapsed = time.time() - start
    print(f"  attempts : {col('c', str(attempts))}  rejected (expected): {col('g', str(p.ok))}  unexpected: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 11 -- Deliberate error traffic (4xx population)
# ---------------------------------------------------------------------------

async def phase_errors(
    client: httpx.AsyncClient, headers: dict, count: int,
) -> PhaseStats:
    p = PhaseStats("errors")
    section(f"Phase 11 -- Error traffic ({count} hits)")
    start = time.time()

    for _ in range(count):
        choice = random.random()
        if choice < 0.4:
            await hit(client, p, "GET",
                      f"/api/v1/assets/NONEXISTENT-{secrets.token_hex(4)}",
                      headers=headers, accept_codes=(404, 422))
        elif choice < 0.7:
            await hit(client, p, "POST", "/api/v1/assets/transfer",
                      headers=headers, json_body={"bad": "payload"},
                      accept_codes=(400, 422))
        elif choice < 0.85:
            await hit(client, p, "GET",
                      f"/api/v1/compliance/{uuid.uuid4()}",
                      headers=headers, accept_codes=(404, 403))
        else:
            await hit(client, p, "GET",
                      "/api/v1/audit/asset/NOT-A-REAL-ID",
                      headers=headers, accept_codes=(404, 403, 422))

    p.elapsed = time.time() - start
    print(f"  errors generated : {col('y', str(p.ok))}  unexpected: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Phase 12 -- Cooldown reads
# ---------------------------------------------------------------------------

async def phase_cooldown(
    client: httpx.AsyncClient, headers: dict, duration: float,
) -> PhaseStats:
    p = PhaseStats("cooldown")
    section(f"Phase 12 -- Cooldown reads ({duration:.0f}s)")
    start = time.time()
    deadline = start + duration

    while time.time() < deadline:
        batch = [
            hit(client, p, "GET", "/api/v1/assets",
                headers=headers, accept_codes=(200,)),
            hit(client, p, "GET", "/api/v1/transactions",
                headers=headers, accept_codes=(200,)),
            hit(client, p, "GET", "/api/v1/compliance",
                headers=headers, accept_codes=(200,)),
            hit(client, p, "GET", "/api/v1/audit",
                headers=headers, accept_codes=(200,)),
            hit(client, p, "GET", "/health", accept_codes=(200,)),
            hit(client, p, "GET", "/metrics", accept_codes=(200,)),
        ]
        await asyncio.gather(*batch, return_exceptions=True)
        await asyncio.sleep(0.5)

    p.elapsed = time.time() - start
    print(f"  rolling reads : {col('c', str(p.requests))}  ok: {col('g', str(p.ok))}  err: {col('r', str(p.errors))}")
    return p


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

PHASE_REGISTRY = {
    "setup":       "Phase 1  -- ZKP setup + readiness",
    "kyc-wave":    "Phase 2  -- KYC submissions",
    "tokenize":    "Phase 3  -- Tokenization burst",
    "screening":   "Phase 4  -- AML screening burst",
    "trading":     "Phase 5  -- Trading wave",
    "async-heavy": "Phase 6  -- Audit reports + fraud scans",
    "agent":       "Phase 7  -- RAG agent queries",
    "sse":         "Phase 8  -- SSE subscribers",
    "freeze":      "Phase 9  -- Freeze cycle",
    "zkp-verify":  "Phase 10 -- ZKP verify load",
    "errors":      "Phase 11 -- Error traffic",
    "cooldown":    "Phase 12 -- Cooldown reads",
}


async def run(args: argparse.Namespace) -> None:
    quick = args.quick
    skip = set(s.strip() for s in (args.skip or "").split(",") if s.strip())

    profile = {
        "kyc_count":          5 if quick else 12,
        "tokenize_count":     10 if quick else 30,
        "screening_count":    6 if quick else 16,
        "trading_count":      8 if quick else 24,
        "report_count":       3 if quick else 8,
        "scan_count":         2 if quick else 4,
        "agent_count":        3 if quick else 8,
        "sse_subscribers":    2 if quick else 4,
        "sse_hold":           6.0 if quick else 18.0,
        "freeze_count":       4 if quick else 10,
        "zkp_attempts":       4 if quick else 12,
        "error_count":        8 if quick else 20,
        "cooldown_seconds":   10.0 if quick else 25.0,
    }

    banner("AIP Qx -- Full-stack Grafana Dashboard Simulation")
    print(f"  target       : {col('c', BASE_URL)}")
    print(f"  user         : {col('dim', SIM_EMAIL)}")
    print(f"  profile      : {col('y', 'quick' if quick else 'standard')}")
    print(f"  concurrency  : {col('y', str(args.concurrency))}")
    if skip:
        print(f"  skipping     : {col('r', ', '.join(sorted(skip)))}")

    STATS.start = time.time()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        print(f"\n  {col('dim', 'authenticating...')} ", end="")
        token = await login(client)
        if not token:
            print(col("r", "FAILED -- cannot continue"))
            return
        print(col("g", f"OK (token {token[:18]}...)"))

        headers = {"Authorization": f"Bearer {token}"}

        runners = {
            "setup":       lambda: phase_setup(client, headers),
            "kyc-wave":    lambda: phase_kyc(client, headers, profile["kyc_count"]),
            "tokenize":    lambda: phase_tokenize(client, headers, profile["tokenize_count"], args.concurrency),
            "screening":   lambda: phase_screening(client, headers, profile["screening_count"]),
            "trading":     lambda: phase_trading(client, headers, profile["trading_count"], args.concurrency),
            "async-heavy": lambda: phase_async_heavy(client, headers, profile["report_count"], profile["scan_count"]),
            "agent":       lambda: phase_agent(client, headers, profile["agent_count"]),
            "sse":         lambda: phase_sse(client, headers, profile["sse_subscribers"], profile["sse_hold"]),
            "freeze":      lambda: phase_freeze(client, headers, profile["freeze_count"]),
            "zkp-verify":  lambda: phase_zkp_verify(client, headers, profile["zkp_attempts"]),
            "errors":      lambda: phase_errors(client, headers, profile["error_count"]),
            "cooldown":    lambda: phase_cooldown(client, headers, profile["cooldown_seconds"]),
        }

        for key, _label in PHASE_REGISTRY.items():
            if key in skip:
                continue
            phase = await runners[key]()
            STATS.add(phase)

    # ─── Summary ────────────────────────────────────────────────────────
    elapsed = time.time() - STATS.start
    banner("Simulation Complete")
    print(f"  duration       : {elapsed:.1f}s")
    print(f"  total requests : {col('b', str(STATS.total_requests))}")
    print(f"  successes      : {col('g', str(STATS.total_ok))}")
    print(f"  errors         : {col('r', str(STATS.total_errors))}")
    print(f"  assets minted  : {col('y', str(len(STATS.assets_minted)))}")
    print(f"  celery tasks   : {col('y', str(len(STATS.tasks_dispatched)))}")
    print()
    print(col("bold", "  per-phase breakdown"))
    print("  " + "-" * 70)
    for ph in STATS.phases:
        bar_ok = "#" * min(40, ph.ok // 2)
        print(
            f"  {ph.name:<14} {ph.elapsed:5.1f}s  "
            f"req {ph.requests:4d}  ok {col('g', f'{ph.ok:4d}')}  err {col('r', f'{ph.errors:3d}')}  {bar_ok}"
        )
    print("  " + "-" * 70)
    print(f"\n  dashboard : {col('c', 'http://10.10.10.150:3000/d/rwa-ops-hub')}")
    print(f"  prometheus: {col('dim', 'http://10.10.10.150:9090/graph')}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AIP Qx full-stack Grafana simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Phases: " + ", ".join(PHASE_REGISTRY.keys()) +
            "\n\nUse --skip phase1,phase2 to omit phases."
        ),
    )
    parser.add_argument("--quick", action="store_true",
                        help="lighter profile, ~90s instead of ~5min")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="max in-flight tokenize/transfer requests (default 8)")
    parser.add_argument("--skip", type=str, default="",
                        help="comma-separated phase keys to skip")
    args = parser.parse_args()

    if not SIM_PASSWORD:
        print(col("y", "warning: SIM_USER_PASSWORD is empty -- export it before running."))

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print(col("y", "\n  interrupted by user"))


if __name__ == "__main__":
    main()
