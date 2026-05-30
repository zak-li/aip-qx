#!/usr/bin/env python3
"""setup-realm.py — Configure the qx realm in Keycloak via Admin REST API.

Run once after first boot:
    python3 setup-realm.py \
        --keycloak-url https://localhost:8443 \
        --admin-user admin \
        --admin-pass <password>
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time

import httpx

# ─── Application roles matching user_role_enum ──────────────────────────────
APP_ROLES = [
    "SUPER_ADMIN",
    "ADMIN_ORG",
    "EMETTEUR",
    "CUSTODIAN",
    "TRADER",
    "REGULATEUR",
    "AUDITEUR",
    "COMPLIANCE_OFFICER",
    "READONLY",
]

REALM = "qx"
CLIENT_ID = "qx-api"


def get_admin_token(base: str, user: str, password: str) -> str:
    resp = httpx.post(
        f"{base}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": user,
            "password": password,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def admin(base: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=f"{base}/admin/realms",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )


def ensure_realm(client: httpx.Client, base: str, token: str) -> None:
    r = client.get(f"/{REALM}")
    if r.status_code == 200:
        print(f"  Realm '{REALM}' already exists — updating settings")
        client.put(f"/{REALM}", content=json.dumps(_realm_payload()))
        return

    print(f"  Creating realm '{REALM}'")
    r2 = httpx.post(
        f"{base}/admin/realms",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        content=json.dumps(_realm_payload()),
        timeout=30,
    )
    r2.raise_for_status()


def _realm_payload() -> dict:
    return {
        "realm": REALM,
        "displayName": "AIP Qx",
        "enabled": True,
        "sslRequired": "external",
        # Token lifetimes
        "accessTokenLifespan": 900,                    # 15 min
        "ssoSessionMaxLifespan": 86400 * 30,           # 30 days
        "ssoSessionIdleTimeout": 3600,                 # 1 hour idle
        "refreshTokenMaxReuse": 0,                     # no refresh token reuse
        # Security policies
        "bruteForceProtected": True,
        "failureFactor": 5,
        "waitIncrementSeconds": 60,
        "maxFailureWaitSeconds": 900,
        "minimumQuickLoginWaitSeconds": 60,
        "quickLoginCheckMilliSeconds": 1000,
        # Password policy
        "passwordPolicy": (
            "length(12) and "
            "upperCase(1) and "
            "lowerCase(1) and "
            "digits(1) and "
            "specialChars(1) and "
            "notUsername and "
            "passwordHistory(5)"
        ),
        # Email (configure SMTP separately in admin UI)
        "loginWithEmailAllowed": True,
        "duplicateEmailsAllowed": False,
        "verifyEmail": False,
        # Registration disabled — managed by platform admins
        "registrationAllowed": False,
        "resetPasswordAllowed": True,
        # OTP / MFA policy
        "otpPolicyType": "totp",
        "otpPolicyAlgorithm": "HmacSHA256",
        "otpPolicyDigits": 6,
        "otpPolicyPeriod": 30,
        "otpPolicyLookAheadWindow": 0,
    }


def ensure_roles(client: httpx.Client) -> None:
    existing = {r["name"] for r in client.get(f"/{REALM}/roles").json()}
    for role in APP_ROLES:
        if role in existing:
            continue
        print(f"  Creating realm role: {role}")
        client.post(
            f"/{REALM}/roles",
            content=json.dumps({"name": role, "description": f"RWA platform role: {role}"}),
        ).raise_for_status()


def ensure_client(client: httpx.Client) -> str:
    """Create or update the qx-api client. Returns the client UUID.

    Re-running this must not invalidate a previously-issued secret: if the
    client already exists we leave its secret alone. Only the first creation
    prints a new secret to copy into KEYCLOAK_CLIENT_SECRET.
    """
    existing = client.get(f"/{REALM}/clients", params={"clientId": CLIENT_ID}).json()
    client_secret = None if existing else secrets.token_urlsafe(48)

    payload = {
        "clientId": CLIENT_ID,
        "name": "RWA API",
        "description": "Backend API + OIDC SSO client",
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,               # confidential client
        "standardFlowEnabled": True,         # authorization_code
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,  # no password grant
        "serviceAccountsEnabled": True,      # client_credentials for gRPC
        "authorizationServicesEnabled": False,
        # PKCE required
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "access.token.signed.response.alg": "RS256",
            "id.token.signed.response.alg": "RS256",
            "use.refresh.tokens": "true",
            "client_credentials.use_refresh_token": "false",
        },
        "redirectUris": [
            "http://10.10.10.150:8000/api/v1/auth/callback",
            "https://10.10.10.150:8443/api/v1/auth/callback",
            "http://localhost:8000/api/v1/auth/callback",
        ],
        "webOrigins": [
            "http://10.10.10.150:8000",
            "https://10.10.10.150:8443",
            "http://localhost:8000",
        ],
    }
    if client_secret is not None:
        payload["secret"] = client_secret

    if existing:
        uuid = existing[0]["id"]
        print(f"  Updating client '{CLIENT_ID}' (uuid={uuid}) — keeping existing secret")
        client.put(f"/{REALM}/clients/{uuid}", content=json.dumps(payload)).raise_for_status()
    else:
        print(f"  Creating client '{CLIENT_ID}'")
        r = client.post(f"/{REALM}/clients", content=json.dumps(payload))
        r.raise_for_status()
        uuid = client.get(f"/{REALM}/clients", params={"clientId": CLIENT_ID}).json()[0]["id"]
        print("\n  *** CLIENT SECRET (copy to KEYCLOAK_CLIENT_SECRET in .env) ***")
        print(f"  {client_secret}\n")

    return uuid


def ensure_mappers(client: httpx.Client, client_uuid: str) -> None:
    """Add protocol mappers so pex_role appears as a top-level JWT claim."""
    existing_names = {
        m["name"]
        for m in client.get(f"/{REALM}/clients/{client_uuid}/protocol-mappers/models").json()
    }

    mappers = [
        {
            "name": "pex_role",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "consentRequired": False,
            "config": {
                "user.attribute": "pex_role",
                "claim.name": "pex_role",
                "jsonType.label": "String",
                "id.token.claim": "true",
                "access.token.claim": "true",
                "userinfo.token.claim": "true",
            },
        },
        {
            "name": "audience-qx-api",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "consentRequired": False,
            "config": {
                "included.client.audience": CLIENT_ID,
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        },
        {
            "name": "org_id",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "consentRequired": False,
            "config": {
                "user.attribute": "org_id",
                "claim.name": "org_id",
                "jsonType.label": "String",
                "id.token.claim": "false",
                "access.token.claim": "true",
                "userinfo.token.claim": "false",
            },
        },
    ]

    for mapper in mappers:
        if mapper["name"] in existing_names:
            print(f"  Mapper '{mapper['name']}' already exists — skipping")
            continue
        print(f"  Adding mapper: {mapper['name']}")
        client.post(
            f"/{REALM}/clients/{client_uuid}/protocol-mappers/models",
            content=json.dumps(mapper),
        ).raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keycloak-url", default="https://localhost:8443")
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-pass", required=True)
    args = parser.parse_args()

    base = args.keycloak_url.rstrip("/")

    print("Authenticating with Keycloak Admin API...")
    for attempt in range(10):
        try:
            token = get_admin_token(base, args.admin_user, args.admin_pass)
            break
        except Exception as exc:
            print(f"  Attempt {attempt + 1}/10 failed: {exc}  — retrying in 5s")
            time.sleep(5)
    else:
        print("ERROR: Could not authenticate after 10 attempts", file=sys.stderr)
        sys.exit(1)

    with admin(base, token) as c:
        print("\n[1/4] Ensuring realm...")
        ensure_realm(c, base, token)

        print("\n[2/4] Ensuring realm roles...")
        ensure_roles(c)

        print("\n[3/4] Ensuring OIDC client...")
        client_uuid = ensure_client(c)

        print("\n[4/4] Ensuring protocol mappers...")
        ensure_mappers(c, client_uuid)

    print("\nKeycloak realm configuration complete.")
    print(f"  Admin UI: {base}/admin/master/console/#/{REALM}")
    print(f"  OIDC discovery: {base}/realms/{REALM}/.well-known/openid-configuration")


if __name__ == "__main__":
    main()
