"""
RWA Platform — Dashboard Load Simulation
Generates realistic API traffic so Prometheus metrics populate the Grafana dashboard.

Usage:
    python scripts/simulate_dashboard.py [--duration 120] [--rps 8]
"""

import asyncio
import os
import random
import sys
import time
import uuid
import argparse
from datetime import date, timedelta
from decimal import Decimal

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
THOMAS_EMAIL = os.environ.get("SIM_USER_EMAIL", "thomas.martin@bank01.com")
THOMAS_PASSWORD = os.environ.get("SIM_USER_PASSWORD", "")
THOMAS_USER_ID = os.environ.get("SIM_USER_ID", "a0000001-0001-0001-0001-000000000001")
BNP_ORG_ID = os.environ.get("SIM_ORG_ID", "a1b2c3d4-0001-0001-0001-000000000001")

ASSET_TYPES = ["OBLIGATION", "OPCVM", "IMMOBILIER", "DERIVE", "MATIERE_PREMIERE", "PRIVATE_EQUITY"]
ASSET_PREFIXES = {
    "OBLIGATION": "OBL",
    "OPCVM": "OPC",
    "IMMOBILIER": "IMM",
    "DERIVE": "DER",
    "MATIERE_PREMIERE": "MPR",
    "PRIVATE_EQUITY": "PE",
}
ASSET_NAMES = {
    "OBLIGATION": ["OAT 3.75% 2030", "BTP 4.0% 2028", "BUND 2.5% 2031", "Gilt 4.25% 2032"],
    "OPCVM": ["MSCI World Tracker", "CAC 40 ETF", "Euro Corporate Bond Fund"],
    "IMMOBILIER": ["Tour Montparnasse SCPI", "Immeuble La Defense", "Portfolio Logistique"],
    "DERIVE": ["OAT Future Dec 2025", "EUR/USD 3M Forward", "CDS BNP 5Y"],
    "MATIERE_PREMIERE": ["Gold Bullion Token", "Crude Oil WTI Q4", "Wheat Index Fund"],
    "PRIVATE_EQUITY": ["LBO Tech Fund III", "Growth Capital SCPI", "Infra Debt 2026"],
}

STATS = {"requests": 0, "ok": 0, "errors": 0, "assets_created": [], "start": 0.0}

COLORS = {
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "red":    "\033[91m",
    "blue":   "\033[94m",
    "cyan":   "\033[96m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
    "dim":    "\033[2m",
}

def c(color: str, text: str) -> str:
    return f"{COLORS[color]}{text}{COLORS['reset']}"


def progress_bar(current: float, total: float, width: int = 40) -> str:
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    pct = current / total * 100
    return f"[{bar}] {pct:5.1f}%"


def status_line(token: bool, elapsed: float, duration: float) -> None:
    ok = STATS["ok"]
    err = STATS["errors"]
    total_req = STATS["requests"]
    rps = total_req / max(elapsed, 1)
    assets = len(STATS["assets_created"])
    bar = progress_bar(elapsed, duration)

    auth = c("green", "AUTH OK") if token else c("red", "NO AUTH")
    line = (
        f"\r{c('bold', 'SIM')} {bar}  "
        f"{auth}  "
        f"RPS {c('cyan', f'{rps:.1f}')}  "
        f"Req {c('blue', str(total_req))}  "
        f"OK {c('green', str(ok))}  "
        f"Err {c('red', str(err))}  "
        f"Assets {c('yellow', str(assets))}"
        f"  {elapsed:.0f}s/{duration:.0f}s"
    )
    sys.stdout.write(line)
    sys.stdout.flush()


async def login(client: httpx.AsyncClient) -> str | None:
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"email": THOMAS_EMAIL, "password": THOMAS_PASSWORD},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token") or data.get("token")
            return token
        print(f"\n{c('red', 'Login failed')}: {resp.status_code} — {resp.text[:200]}")
    except Exception as exc:
        print(f"\n{c('red', 'Login error')}: {exc}")
    return None


def random_asset_payload(seq: int) -> dict:
    atype = random.choice(ASSET_TYPES)
    prefix = ASSET_PREFIXES[atype]
    year = random.randint(2024, 2026)
    asset_id = f"RWA-{prefix}-SIM-{year}-{seq:03d}"
    issuance = date(year, random.randint(1, 12), random.randint(1, 28))
    nominal = random.choice([5_000_000, 10_000_000, 25_000_000, 50_000_000, 100_000_000])
    name = random.choice(ASSET_NAMES[atype])
    return {
        "asset_id": asset_id,
        "isin": f"FR{uuid.uuid4().hex[:10].upper()}"[:12],
        "asset_type": atype,
        "asset_name": f"{name} #{seq}",
        "issuer_lei": f"969500{uuid.uuid4().hex[:14].upper()}",
        "nominal_value": float(nominal),
        "currency": random.choice(["EUR", "EUR", "EUR", "USD"]),
        "issuance_date": issuance.isoformat(),
        "justification": "Simulation load test — RWA tokenization batch",
    }


async def tokenize_asset(client: httpx.AsyncClient, headers: dict, seq: int) -> str | None:
    payload = random_asset_payload(seq)
    STATS["requests"] += 1
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/assets/tokenize",
            json=payload, headers=headers, timeout=15,
        )
        if resp.status_code in (200, 201):
            STATS["ok"] += 1
            asset_id = payload["asset_id"]
            STATS["assets_created"].append(asset_id)
            return asset_id
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1
    return None


async def transfer_asset(client: httpx.AsyncClient, headers: dict, asset_id: str) -> None:
    STATS["requests"] += 1
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/assets/transfer",
            json={
                "asset_id": asset_id,
                "to_owner": f"AMF_REGULATOR_{uuid.uuid4().hex[:8].upper()}",
                "price": float(random.randint(1_000_000, 80_000_000)),
                "justification": "Simulation — secondary market transfer",
            },
            headers=headers, timeout=15,
        )
        if resp.status_code in (200, 201):
            STATS["ok"] += 1
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def freeze_asset(client: httpx.AsyncClient, headers: dict, asset_id: str) -> None:
    STATS["requests"] += 1
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/assets/freeze",
            json={
                "asset_id": asset_id,
                "reason": "Simulation regulatory freeze — AML screening triggered",
                "regulatory_ref": f"AMF-AML-{date.today().year}-{random.randint(100, 999)}",
            },
            headers=headers, timeout=15,
        )
        if resp.status_code in (200, 201):
            STATS["ok"] += 1
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def read_assets(client: httpx.AsyncClient, headers: dict) -> None:
    STATS["requests"] += 1
    try:
        resp = await client.get(f"{BASE_URL}/api/v1/assets", headers=headers, timeout=10)
        if resp.status_code == 200:
            STATS["ok"] += 1
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def read_transactions(client: httpx.AsyncClient, headers: dict) -> None:
    STATS["requests"] += 1
    try:
        resp = await client.get(
            f"{BASE_URL}/api/v1/transactions",
            headers=headers, timeout=10,
        )
        if resp.status_code == 200:
            STATS["ok"] += 1
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def read_compliance(client: httpx.AsyncClient, headers: dict) -> None:
    STATS["requests"] += 1
    try:
        resp = await client.get(
            f"{BASE_URL}/api/v1/compliance/{THOMAS_USER_ID}",
            headers=headers, timeout=10,
        )
        if resp.status_code in (200, 404):
            STATS["ok"] += 1
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def run_screening(client: httpx.AsyncClient, headers: dict) -> None:
    STATS["requests"] += 1
    try:
        resp = await client.post(
            f"{BASE_URL}/api/v1/compliance/screening/run",
            json={"user_id": THOMAS_USER_ID},
            headers=headers, timeout=20,
        )
        if resp.status_code in (200, 201, 202):
            STATS["ok"] += 1
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def read_stats(client: httpx.AsyncClient, headers: dict) -> None:
    STATS["requests"] += 1
    try:
        resp = await client.get(
            f"{BASE_URL}/api/v1/transactions/stats/summary",
            headers=headers, timeout=10,
        )
        if resp.status_code == 200:
            STATS["ok"] += 1
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def health_check(client: httpx.AsyncClient) -> None:
    STATS["requests"] += 1
    try:
        resp = await client.get(f"{BASE_URL}/health", timeout=10)
        if resp.status_code == 200:
            STATS["ok"] += 1
        else:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def generate_error_traffic(client: httpx.AsyncClient, headers: dict) -> None:
    """Deliberately invalid requests to populate 4xx/5xx metrics."""
    STATS["requests"] += 1
    try:
        resp = await client.get(
            f"{BASE_URL}/api/v1/assets/NONEXISTENT-ASSET-XYZ",
            headers=headers, timeout=5,
        )
        if resp.status_code in (404, 422):
            STATS["ok"] += 1
        elif resp.status_code >= 500:
            STATS["errors"] += 1
    except Exception:
        STATS["errors"] += 1


async def simulate(duration: float, rps: float) -> None:
    STATS["start"] = time.time()

    SEP = "=" * 70
    print(f"\n{c('bold', SEP)}")
    print(f"{c('bold', '  RWA Platform -- Dashboard Load Simulation')}")
    print(f"{c('bold', SEP)}")
    print(f"  Target   : {c('cyan', BASE_URL)}")
    print(f"  Duration : {c('yellow', f'{duration:.0f}s')}")
    print(f"  Rate     : {c('yellow', f'{rps:.0f} req/s target')}")
    print(f"  User     : {c('dim', THOMAS_EMAIL)}")
    print(f"{c('bold', SEP)}\n")

    async with httpx.AsyncClient(follow_redirects=True) as client:

        print(f"  {c('dim', 'Authenticating...')} ", end="")
        token = await login(client)
        if not token:
            print(c("red", "FAILED — cannot continue without a valid token."))
            return
        print(c("green", f"OK  (token: {token[:20]}...)"))

        headers = {"Authorization": f"Bearer {token}"}

        asset_seq = 1
        interval = 1.0 / rps
        phase_counters = {
            "tokenize": 0,
            "transfer": 0,
            "freeze": 0,
            "reads": 0,
            "compliance": 0,
            "errors": 0,
        }

        print(f"\n  {c('dim', 'Generating traffic...')}\n")

        while True:
            elapsed = time.time() - STATS["start"]
            if elapsed >= duration:
                break

            status_line(bool(token), elapsed, duration)

            # Phase weights (change over time to simulate realistic patterns)
            phase = elapsed / duration
            tasks = []

            if phase < 0.25:
                # Ramp-up: mostly tokenization + reads
                tasks.append(tokenize_asset(client, headers, asset_seq))
                tasks.append(read_assets(client, headers))
                tasks.append(read_transactions(client, headers))
                tasks.append(health_check(client))
                asset_seq += 1
                phase_counters["tokenize"] += 1

            elif phase < 0.50:
                # Peak: transfers + compliance
                assets = STATS["assets_created"]
                if assets:
                    tasks.append(transfer_asset(client, headers, random.choice(assets)))
                tasks.append(read_compliance(client, headers))
                tasks.append(read_stats(client, headers))
                tasks.append(generate_error_traffic(client, headers))
                phase_counters["transfer"] += 1

            elif phase < 0.75:
                # Compliance screening burst
                assets = STATS["assets_created"]
                if assets and random.random() < 0.3:
                    tasks.append(freeze_asset(client, headers, random.choice(assets)))
                tasks.append(run_screening(client, headers))
                tasks.append(read_assets(client, headers))
                tasks.append(read_transactions(client, headers))
                tasks.append(health_check(client))
                phase_counters["compliance"] += 1

            else:
                # Cool-down: mixed reads + occasional errors
                tasks.append(read_assets(client, headers))
                tasks.append(read_transactions(client, headers))
                tasks.append(read_compliance(client, headers))
                tasks.append(generate_error_traffic(client, headers))
                tasks.append(read_stats(client, headers))
                phase_counters["errors"] += 1

            # Add random extra reads to increase throughput
            for _ in range(max(1, int(rps / 5))):
                tasks.append(read_assets(client, headers))

            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(max(0, interval - 0.01))

    elapsed = time.time() - STATS["start"]
    total = STATS["requests"]
    ok = STATS["ok"]
    err = STATS["errors"]
    success_rate = ok / max(total, 1) * 100
    SEP = "=" * 70

    print(f"\n\n{c('bold', SEP)}")
    print(f"{c('bold', '  Simulation Complete')}")
    print(f"{c('bold', SEP)}")
    print(f"  Duration     : {elapsed:.1f}s")
    print(f"  Total Req    : {c('blue',   str(total))}")
    print(f"  Success      : {c('green',  str(ok))}  ({success_rate:.1f}%)")
    print(f"  Errors       : {c('red',    str(err))}")
    print(f"  Avg RPS      : {c('cyan',   f'{total / elapsed:.1f}')}")
    print(f"  Assets       : {c('yellow', str(len(STATS['assets_created'])))}")
    print(f"{c('bold', SEP)}")
    print(f"\n  Dashboard    : {c('cyan', 'http://10.10.10.150:3000/d/rwa-ops-professional')}")
    print(f"  Prometheus   : {c('dim',  'http://10.10.10.150:9090/graph')}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="RWA Dashboard Load Simulation")
    parser.add_argument("--duration", type=float, default=120.0, help="Duration in seconds (default: 120)")
    parser.add_argument("--rps",      type=float, default=8.0,   help="Target requests per second (default: 8)")
    args = parser.parse_args()

    asyncio.run(simulate(args.duration, args.rps))


if __name__ == "__main__":
    main()
