
import socket
import sys
from datetime import UTC, datetime

VM_HOST = "10.10.10.150"

SERVICES = [
    ("SSH",                    22,   "Accès distant Ubuntu",                True),
    ("PostgreSQL",             5432, "Base de données principale (rwadb)",  True),
    ("Redis",                  6379, "Cache & broker Celery",              True),
    ("Fabric Orderer",         7050, "Ordonnanceur Hyperledger Fabric",    True),
    ("Fabric Peer BANK01",        7051, "Nœud Bank01 (peer0)",          True),
    ("Fabric Peer REG01",        7091, "Nœud REG01 Régulateur (peer0)",       True),
    ("CouchDB BANK01",            5984, "State DB BANK01 (World State)",        True),
    ("CouchDB REG01",            7984, "State DB REG01 (World State)",        True),
    ("Chaincode RWA-Token",    9999, "Smart Contract (CCaaS)",            True),
    ("Prometheus",             9090, "Collecte de métriques",             False),
    ("Grafana",                3000, "Dashboard monitoring",              False),
    ("Postgres Exporter",      9187, "Exporteur métriques PostgreSQL",    False),
    ("Redis Exporter",         9121, "Exporteur métriques Redis",         False),
]

def check_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False

def run_health_check() -> bool:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    print()
    print("═" * 66)
    print("  🔍  RWA PLATFORM — INFRASTRUCTURE HEALTH CHECK")
    print(f"  📡  Cible : {VM_HOST}")
    print(f"  🕐  {now}")
    print("═" * 66)

    print("\n── Connectivité réseau ──")
    if not check_tcp(VM_HOST, 22, timeout=5.0):
        print(f"  ❌  VM {VM_HOST} INJOIGNABLE (port 22 fermé)")
        print("      → La machine est probablement éteinte ou le réseau est coupé.")
        print("═" * 66)
        return False
    print(f"  ✅  VM {VM_HOST} accessible (SSH port 22)")

    results = []
    critical_down = []
    optional_down = []

    print("\n── Services d'infrastructure ──")
    for name, port, desc, critical in SERVICES:
        if name == "SSH":
            results.append((name, port, True, critical))
            continue

        alive = check_tcp(VM_HOST, port)
        results.append((name, port, alive, critical))

        icon = "✅" if alive else "❌"
        status = "UP" if alive else "DOWN"
        tag = "CRITIQUE" if critical and not alive else ""
        print(f"  {icon}  {name:<25s} :{port:<6d} {status:<6s} {tag}")

        if not alive:
            if critical:
                critical_down.append((name, port, desc))
            else:
                optional_down.append((name, port, desc))

    total = len(SERVICES)
    up_count = sum(1 for _, _, alive, _ in results if alive)
    down_count = total - up_count

    print()
    print("═" * 66)

    if down_count == 0:
        print("  🟢  TOUS LES SERVICES SONT OPÉRATIONNELS")
        print(f"      {up_count}/{total} services UP")
        print("═" * 66)
        return True

    if critical_down:
        print(f"  🔴  {len(critical_down)} SERVICE(S) CRITIQUE(S) DOWN")
        for name, port, desc in critical_down:
            print(f"      ⚠  {name} (:{port}) — {desc}")

    if optional_down:
        print(f"  🟡  {len(optional_down)} service(s) optionnel(s) DOWN")
        for name, port, desc in optional_down:
            print(f"      [i] {name} (:{port}) -- {desc}")

    print(f"\n      Score : {up_count}/{total} services UP")
    print("═" * 66)

    if critical_down:
        print("\n  💡  Solution : Connectez-vous en SSH et lancez :")
        print(f"      ssh zakaria@{VM_HOST}")
        print("      sudo systemctl start rwa-platform")
        print()
        return False

    return True

if __name__ == "__main__":
    ok = run_health_check()
    sys.exit(0 if ok else 1)
