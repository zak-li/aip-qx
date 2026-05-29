#!/usr/bin/env python3
"""rename-rwa-to-pex.py — One-shot migration of the Keycloak realm name.

Performs the coordinated rename inside the live Keycloak instance:

  - Realm:        `rwa-platform` → `pex`
  - Client:       `rwa-api`      → `pex-api`
  - User attr:    `rwa_role`     → `pex_role`  (on every user)
  - Protocol map: claim name + user.attribute  → `pex_role`

Idempotent — re-running detects an already-renamed realm and exits cleanly.

    KEYCLOAK_ADMIN_PASSWORD=... python3 rename-rwa-to-pex.py \
        --keycloak-url https://10.10.10.150:8443 \
        --admin-user admin \
        --ca-bundle /etc/ssl/keycloak/ca.crt
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

OLD_REALM = "rwa-platform"
NEW_REALM = "pex"
OLD_CLIENT = "rwa-api"
NEW_CLIENT = "pex-api"
OLD_ATTR = "rwa_role"
NEW_ATTR = "pex_role"


def get_token(base: str, user: str, password: str, verify) -> str:
    r = httpx.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli",
              "username": user, "password": password},
        verify=verify, timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--keycloak-url", required=True)
    p.add_argument("--admin-user", default="admin")
    p.add_argument("--ca-bundle")
    args = p.parse_args()

    pwd = os.environ.get("KEYCLOAK_ADMIN_PASSWORD")
    if not pwd:
        sys.exit("Set KEYCLOAK_ADMIN_PASSWORD before running.")

    base = args.keycloak_url.rstrip("/")
    verify = args.ca_bundle or True
    token = get_token(base, args.admin_user, pwd, verify)
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    with httpx.Client(headers=H, verify=verify, timeout=30) as c:
        # ── 1. Detect which realm exists. Rename if needed.
        existing = {r["realm"] for r in c.get(f"{base}/admin/realms").json()}
        if NEW_REALM in existing and OLD_REALM not in existing:
            print(f"  Realm '{NEW_REALM}' already exists — assuming rename was done.")
            realm = NEW_REALM
        elif OLD_REALM in existing:
            print(f"  Renaming realm '{OLD_REALM}' → '{NEW_REALM}'")
            cfg = c.get(f"{base}/admin/realms/{OLD_REALM}").json()
            cfg["realm"] = NEW_REALM
            cfg["displayName"] = "Pex"
            c.put(f"{base}/admin/realms/{OLD_REALM}", content=json.dumps(cfg)).raise_for_status()
            realm = NEW_REALM
        else:
            sys.exit(f"Neither '{OLD_REALM}' nor '{NEW_REALM}' exists.")

        realm_url = f"{base}/admin/realms/{realm}"

        # ── 2. Rename the OIDC client.
        clients = c.get(f"{realm_url}/clients?clientId={OLD_CLIENT}").json()
        if clients:
            uuid = clients[0]["id"]
            cfg = clients[0]
            cfg["clientId"] = NEW_CLIENT
            cfg["name"] = "Pex API"
            # Refresh redirect URIs to use the (unchanged) callback path.
            print(f"  Renaming client '{OLD_CLIENT}' → '{NEW_CLIENT}'")
            c.put(f"{realm_url}/clients/{uuid}", content=json.dumps(cfg)).raise_for_status()
        else:
            print(f"  Client '{OLD_CLIENT}' not found — assumed already renamed.")
            uuid = c.get(f"{realm_url}/clients?clientId={NEW_CLIENT}").json()[0]["id"]

        # ── 3. Update protocol mappers on the client.
        mappers = c.get(f"{realm_url}/clients/{uuid}/protocol-mappers/models").json()
        for m in mappers:
            if m.get("name") == OLD_ATTR:
                m["name"] = NEW_ATTR
                cfg = m.get("config", {})
                cfg["user.attribute"] = NEW_ATTR
                cfg["claim.name"] = NEW_ATTR
                m["config"] = cfg
                print(f"  Renaming mapper '{OLD_ATTR}' → '{NEW_ATTR}'")
                c.put(
                    f"{realm_url}/clients/{uuid}/protocol-mappers/models/{m['id']}",
                    content=json.dumps(m),
                ).raise_for_status()
            elif m.get("name") == "audience-" + OLD_CLIENT:
                m["name"] = "audience-" + NEW_CLIENT
                cfg = m.get("config", {})
                cfg["included.client.audience"] = NEW_CLIENT
                m["config"] = cfg
                print(f"  Updating audience mapper → '{NEW_CLIENT}'")
                c.put(
                    f"{realm_url}/clients/{uuid}/protocol-mappers/models/{m['id']}",
                    content=json.dumps(m),
                ).raise_for_status()

        # ── 4. Rename the user attribute on every user.
        users = c.get(f"{realm_url}/users?max=1000").json()
        for u in users:
            attrs = u.get("attributes") or {}
            if OLD_ATTR in attrs and NEW_ATTR not in attrs:
                attrs[NEW_ATTR] = attrs.pop(OLD_ATTR)
                u["attributes"] = attrs
                print(f"  Updating attr on user {u.get('username','?')}")
                c.put(
                    f"{realm_url}/users/{u['id']}",
                    content=json.dumps(u),
                ).raise_for_status()

    print(f"\nDone. Realm '{realm}' is the canonical Pex realm.")


if __name__ == "__main__":
    main()
