#!/usr/bin/env python3
"""migrate-users.py — Provision DB users into Keycloak as the single source of truth.

For each row in the local `users` table that has no `keycloak_sub` yet:

  1. Create a Keycloak user (username=email, email=email).
  2. Carry over attributes Keycloak needs to mint a useful JWT — primarily
     `pex_role` (drives RBAC in the API) and `org_id` (drives row-level scoping).
  3. Force `UPDATE_PASSWORD` as a required action: we no longer store any
     password hash in the DB, so the user must set one on first login.
  4. Mark email as verified — we trust the email seeded from the DB.
  5. Write the new Keycloak `sub` (uuid) back into the DB row so the API can
     resolve the JWT to a local user record.

Idempotent: re-running skips already-linked rows and refreshes attributes on
users that exist in Keycloak by email but were never linked back.

    KEYCLOAK_ADMIN_PASSWORD=... \\
    DATABASE_URL=postgresql://rwaadmin:****@10.10.10.150:5432/rwadb \\
        python3 migrate-users.py \\
            --keycloak-url https://10.10.10.150:8443 \\
            --realm qx \\
            --ca-bundle /etc/ssl/keycloak/ca.crt
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import asyncpg
import httpx

REQUIRED_ENV = ("KEYCLOAK_ADMIN_PASSWORD", "DATABASE_URL")


def get_token(base: str, user: str, password: str, verify) -> str:
    r = httpx.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli",
              "username": user, "password": password},
        verify=verify, timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def find_kc_user_by_email(c: httpx.Client, realm: str, email: str) -> dict[str, Any] | None:
    users = c.get(f"/admin/realms/{realm}/users", params={"email": email, "exact": "true"}).json()
    return users[0] if users else None


def split_name(email: str) -> tuple[str, str]:
    """Best-effort first/last name from email local part `first.last@host`."""
    local = email.split("@", 1)[0]
    if "." in local:
        first, _, last = local.partition(".")
        return first.capitalize(), last.capitalize()
    return local.capitalize(), ""


def upsert_kc_user(c: httpx.Client, realm: str, row: dict) -> str:
    """Create the user in Keycloak (or refresh attributes if already present).
    Returns the Keycloak user uuid (`sub`)."""
    first, last = split_name(row["email"])
    payload = {
        "username": row["email"],
        "email": row["email"],
        "firstName": first,
        "lastName": last,
        "enabled": bool(row["is_active"]),
        "emailVerified": True,
        "attributes": {
            "pex_role": [row["role"]],
            "org_id": [str(row["org_id"])],
        },
        "requiredActions": ["UPDATE_PASSWORD"],
    }

    existing = find_kc_user_by_email(c, realm, row["email"])
    if existing:
        uid = existing["id"]
        c.put(f"/admin/realms/{realm}/users/{uid}", content=json.dumps(payload)).raise_for_status()
        return uid

    resp = c.post(f"/admin/realms/{realm}/users", content=json.dumps(payload))
    if resp.status_code not in (201, 204):
        raise RuntimeError(f"Failed to create {row['email']}: {resp.status_code} {resp.text}")
    return find_kc_user_by_email(c, realm, row["email"])["id"]


async def run(args: argparse.Namespace) -> int:
    base = args.keycloak_url.rstrip("/")
    verify = args.ca_bundle if args.ca_bundle else True
    token = get_token(base, args.admin_user, os.environ["KEYCLOAK_ADMIN_PASSWORD"], verify)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # asyncpg uses the postgresql:// scheme; strip the +asyncpg driver suffix
    # so the same DATABASE_URL the API uses works here too.
    dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    db = await asyncpg.connect(dsn)
    try:
        rows = await db.fetch(
            "SELECT id, email, role, org_id, is_active, keycloak_sub "
            "FROM users ORDER BY email"
        )

        created = linked = skipped = errored = 0
        with httpx.Client(base_url=base, headers=headers, verify=verify, timeout=30) as c:
            for row in rows:
                tag = f"{row['email']:40s} role={row['role']}"
                if row["keycloak_sub"]:
                    print(f"  = {tag} -- already linked ({row['keycloak_sub'][:8]}...)")
                    skipped += 1
                    continue
                if args.dry_run:
                    print(f"  ? {tag} -- would create/link")
                    continue

                pre_exists = find_kc_user_by_email(c, args.realm, row["email"]) is not None
                try:
                    sub = upsert_kc_user(c, args.realm, dict(row))
                except Exception as exc:
                    print(f"  X {tag} -- {exc}")
                    errored += 1
                    continue

                await db.execute(
                    "UPDATE users SET keycloak_sub=$1 WHERE id=$2", sub, row["id"]
                )
                if pre_exists:
                    print(f"  L {tag} -- linked existing KC user sub={sub}")
                    linked += 1
                else:
                    print(f"  + {tag} -- created sub={sub}")
                    created += 1
    finally:
        await db.close()

    print(
        f"\nDone. created={created} linked={linked} skipped={skipped} errored={errored} "
        f"total={len(rows)}"
    )
    return 0 if errored == 0 else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--keycloak-url", required=True)
    p.add_argument("--realm", required=True)
    p.add_argument("--admin-user", default="admin")
    p.add_argument("--ca-bundle", help="Path to CA cert verifying Keycloak's TLS")
    p.add_argument("--dry-run", action="store_true", help="List what would change, write nothing")
    args = p.parse_args()

    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        sys.exit(f"Set env vars: {', '.join(missing)}")

    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
