#!/usr/bin/env python3
"""configure-identity-first.py — Switch the realm to a two-page login flow.

Builds a top-level Keycloak authentication flow from scratch:

    Cookie                      [ALTERNATIVE]
    Identity Provider Redirector [ALTERNATIVE]
    forms                        [ALTERNATIVE]  (sub-flow)
        Username Form            [REQUIRED]
        Password Form            [REQUIRED]

The user lands on a username-only screen, posts, then sees a password-only
screen. We deliberately don't copy from the built-in 'browser' flow because
that drags in Kerberos + Conditional OTP in the wrong slot, and reordering
sub-flows via the admin REST API is error-prone. Cleaner to construct.

Idempotent: re-running wipes the existing `browser-identity-first` flow and
rebuilds it so the configuration is deterministic.

    KEYCLOAK_ADMIN_PASSWORD=... python3 configure-identity-first.py \
        --keycloak-url https://10.10.10.150:8443 \
        --realm rwa-platform \
        --admin-user admin \
        --ca-bundle /etc/ssl/keycloak/ca.crt
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

FLOW = "browser-identity-first"
FORMS_ALIAS = "browser-identity-first forms"


def get_admin_token(base: str, user: str, password: str, verify) -> str:
    r = httpx.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli",
              "username": user, "password": password},
        verify=verify, timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--keycloak-url", required=True)
    p.add_argument("--realm", required=True)
    p.add_argument("--admin-user", default="admin")
    p.add_argument("--ca-bundle", help="Path to CA cert to verify Keycloak TLS")
    args = p.parse_args()

    pwd = os.environ.get("KEYCLOAK_ADMIN_PASSWORD")
    if not pwd:
        sys.exit("Set KEYCLOAK_ADMIN_PASSWORD before running.")

    base = args.keycloak_url.rstrip("/")
    verify = args.ca_bundle if args.ca_bundle else True

    token = get_admin_token(base, args.admin_user, pwd, verify)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    realm_url = f"{base}/admin/realms/{args.realm}"

    with httpx.Client(headers=headers, verify=verify, timeout=30) as c:
        # ── 0. If realm is currently bound to FLOW, switch it back to 'browser'
        #       before deleting, otherwise the DELETE fails ("flow is in use").
        realm_cfg = c.get(realm_url).json()
        if realm_cfg.get("browserFlow") == FLOW:
            print("  Temporarily binding realm to built-in 'browser' so we can delete the old flow")
            realm_cfg["browserFlow"] = "browser"
            c.put(realm_url, content=json.dumps(realm_cfg)).raise_for_status()

        # ── 1. Wipe any prior version so this script is fully idempotent.
        flows = c.get(f"{realm_url}/authentication/flows").json()
        old = next((f for f in flows if f["alias"] == FLOW), None)
        if old:
            print(f"  Deleting prior '{FLOW}' flow (id={old['id']})")
            c.delete(f"{realm_url}/authentication/flows/{old['id']}").raise_for_status()

        # ── 2. Create the top-level flow.
        print(f"  Creating top-level flow '{FLOW}'")
        c.post(
            f"{realm_url}/authentication/flows",
            content=json.dumps({
                "alias": FLOW,
                "description": "Identity-first browser login (username then password)",
                "providerId": "basic-flow",
                "topLevel": True,
                "builtIn": False,
            }),
        ).raise_for_status()

        # ── 3. Add executions at the top level, in order.
        for provider in ("auth-cookie", "identity-provider-redirector"):
            print(f"    + {provider}")
            c.post(
                f"{realm_url}/authentication/flows/{FLOW}/executions/execution",
                content=json.dumps({"provider": provider}),
            ).raise_for_status()

        # Sub-flow that holds the two forms.
        print("    + sub-flow 'forms'")
        c.post(
            f"{realm_url}/authentication/flows/{FLOW}/executions/flow",
            content=json.dumps({
                "alias": FORMS_ALIAS,
                "type": "basic-flow",
                "description": "Identity-first forms (username → password)",
                "provider": "registration-page-form",
            }),
        ).raise_for_status()

        # Username then password inside the sub-flow.
        for provider in ("auth-username-form", "auth-password-form"):
            print(f"      + {provider}")
            c.post(
                f"{realm_url}/authentication/flows/{FORMS_ALIAS}/executions/execution",
                content=json.dumps({"provider": provider}),
            ).raise_for_status()

        # ── 4. Set requirements.
        # Cookie + IDP Redirector + forms are all ALTERNATIVE at the top level;
        # both inner form executions are REQUIRED.
        wanted_top = {
            "auth-cookie": "ALTERNATIVE",
            "identity-provider-redirector": "ALTERNATIVE",
        }
        for ex in c.get(f"{realm_url}/authentication/flows/{FLOW}/executions").json():
            want = None
            if ex.get("providerId") in wanted_top:
                want = wanted_top[ex["providerId"]]
            elif ex.get("authenticationFlow") and ex.get("displayName") == FORMS_ALIAS:
                want = "ALTERNATIVE"
            if want and ex.get("requirement") != want:
                print(f"    set {ex.get('displayName')} → {want}")
                ex["requirement"] = want
                c.put(
                    f"{realm_url}/authentication/flows/{FLOW}/executions",
                    content=json.dumps(ex),
                ).raise_for_status()

        for ex in c.get(f"{realm_url}/authentication/flows/{FORMS_ALIAS}/executions").json():
            if ex.get("requirement") != "REQUIRED":
                print(f"    set {ex.get('displayName')} → REQUIRED")
                ex["requirement"] = "REQUIRED"
                c.put(
                    f"{realm_url}/authentication/flows/{FORMS_ALIAS}/executions",
                    content=json.dumps(ex),
                ).raise_for_status()

        # ── 5. Bind the realm to the new flow.
        realm_cfg = c.get(realm_url).json()
        realm_cfg["browserFlow"] = FLOW
        c.put(realm_url, content=json.dumps(realm_cfg)).raise_for_status()
        print(f"\n  Realm '{args.realm}' bound to '{FLOW}'")

    print("\nDone. Identity-first login is active.")


if __name__ == "__main__":
    main()
