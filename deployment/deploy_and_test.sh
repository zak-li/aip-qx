#!/bin/bash
# =============================================================================
#  RWA Platform — Deploy & Test Vault Integration
#  Run this directly on 10.10.10.150 as user zakaria
# =============================================================================
set -euo pipefail

VAULT_ADDR_LOCAL="http://127.0.0.1:8200"
PROJECT_DIR="/home/zakaria/rwa-platform"
POLICY_FILE="/etc/vault.d/rwa-platform-policy.hcl"
PASS="zakaria"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}  $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; }
info() { echo -e "${CYAN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

echo "================================================================"
echo " RWA Platform — Vault Integration Deploy & Test"
echo " $(date)"
echo "================================================================"

# ─── 1. VAULT STATUS ────────────────────────────────────────────────
echo -e "\n${CYAN}=== 1. VAULT STATUS ===${NC}"
if ! VAULT_ADDR=$VAULT_ADDR_LOCAL vault status 2>&1; then
    warn "Vault not responding — trying to start..."
    echo "$PASS" | sudo -S systemctl start vault
    sleep 5
    echo "$PASS" | sudo -S systemctl start vault-unseal
    sleep 3
fi

VAULT_STATUS=$(VAULT_ADDR=$VAULT_ADDR_LOCAL vault status -format=json 2>/dev/null || echo '{}')
SEALED=$(echo "$VAULT_STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('sealed','unknown'))" 2>/dev/null || echo "unknown")

if [ "$SEALED" = "True" ] || [ "$SEALED" = "true" ]; then
    fail "Vault is SEALED — auto-unseal failed"
    info "Run manually: vault operator unseal \$(cat /etc/vault.d/unseal.key)"
    exit 1
fi
ok "Vault is UNSEALED and running"

# ─── 2. GET SERVICE TOKEN ────────────────────────────────────────────
echo -e "\n${CYAN}=== 2. TOKEN VALIDATION ===${NC}"
SERVICE_TOKEN=$(grep "^VAULT_TOKEN=" "${PROJECT_DIR}/.env" | cut -d= -f2 | tr -d '"' | tr -d "'")
if [ -z "$SERVICE_TOKEN" ]; then
    fail "VAULT_TOKEN not found in ${PROJECT_DIR}/.env"
    exit 1
fi
info "Token from .env: ${SERVICE_TOKEN:0:8}..."

# Verify token is valid
TOKEN_CHECK=$(VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$SERVICE_TOKEN" vault token lookup -format=json 2>/dev/null || echo '{}')
TOKEN_VALID=$(echo "$TOKEN_CHECK" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d.get('data',{}).get('id') else 'fail')" 2>/dev/null || echo "fail")

if [ "$TOKEN_VALID" != "ok" ]; then
    fail "Service token is invalid or expired!"
    info "Getting ROOT token from env or entering it manually..."
    read -s -p "Enter root token: " ROOT_TOKEN
    echo

    # Re-create service token
    NEW_TOKEN=$(VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$ROOT_TOKEN" \
        vault token create -policy=rwa-platform -ttl=720h -renewable=true \
        -display-name=rwa-platform-service -format=json | \
        python3 -c "import sys,json; print(json.load(sys.stdin)['auth']['client_token'])")

    # Update .env
    sed -i "s|^VAULT_TOKEN=.*|VAULT_TOKEN=${NEW_TOKEN}|" "${PROJECT_DIR}/.env"
    SERVICE_TOKEN="$NEW_TOKEN"
    ok "New service token created and saved to .env"
else
    TOKEN_TTL=$(echo "$TOKEN_CHECK" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'].get('ttl','?'))" 2>/dev/null || echo "?")
    ok "Token valid — TTL remaining: ${TOKEN_TTL}s"
fi

# ─── 3. UPDATE VAULT POLICY ─────────────────────────────────────────
echo -e "\n${CYAN}=== 3. VAULT POLICY UPDATE ===${NC}"

# Get root token for policy update
ROOT_TOKEN_ENV=$(grep "^VAULT_ROOT_TOKEN=" "${PROJECT_DIR}/.env" 2>/dev/null | cut -d= -f2 | tr -d '"' | tr -d "'" || true)
if [ -z "$ROOT_TOKEN_ENV" ]; then
    warn "No VAULT_ROOT_TOKEN in .env — skipping policy update (needs root token)"
    warn "To fix manually: vault policy write rwa-platform /etc/vault.d/rwa-platform-policy.hcl"
else
    echo "$PASS" | sudo -S tee "$POLICY_FILE" > /dev/null << 'POLICY'
path "rwa-fabric/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "rwa-fabric/metadata/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
POLICY

    VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$ROOT_TOKEN_ENV" \
        vault policy write rwa-platform "$POLICY_FILE" && \
        ok "Policy 'rwa-platform' updated" || fail "Policy update failed"
fi

# ─── 4. DEPLOY UPDATED wallet.py ────────────────────────────────────
echo -e "\n${CYAN}=== 4. DEPLOY wallet.py ===${NC}"
WALLET_PATH="${PROJECT_DIR}/backend/fabric_client/wallet.py"

# Check current mount_point usage
if grep -q "mount_point='rwa-fabric'" "$WALLET_PATH" 2>/dev/null; then
    ok "wallet.py already has correct mount_point='rwa-fabric'"
else
    warn "wallet.py needs update — applying fix..."
    cat > /tmp/wallet_new.py << 'WALLET_EOF'
import ctypes
import datetime
import gc
import json
import logging
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import hvac
from cryptography import x509
from cryptography.x509.oid import NameOID

from backend.config import FabricSettings

def _zero_string(s: str) -> None:
    try:
        buf_len = len(s)
        if buf_len == 0:
            return
        raw = (ctypes.c_char * (buf_len + 1)).from_address(id(s) + sys.getsizeof(s) - buf_len - 1)
        ctypes.memset(raw, 0, buf_len)
    except Exception:
        pass
    finally:
        del s
        gc.collect()

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class Identity:
    label: str
    cert_pem: str
    msp_id: str

class FabricWallet:
    def __init__(self, settings: FabricSettings) -> None:
        self.settings = settings
        self._identities: dict[str, Identity] = {}

        self._vault = hvac.Client(url=self.settings.vault_addr, token=self.settings.vault_token)

        try:
            if not self._vault.is_authenticated():
                self._log_op(logging.ERROR, "Vault authentication failed. Token may be invalid.")
                raise PermissionError("Vault authentication failed.")
        except Exception as e:
            self._log_op(logging.WARNING, f"Could not connect to Vault at {self.settings.vault_addr}: {e}")

        self._initialize_from_metadata()

    def _log_op(self, level: int, msg: str, context: dict[str, str | int] | None = None) -> None:
        logger.log(level, json.dumps({"message": msg, "context": context or {}}))

    def _validate_certificate(self, cert_pem: str) -> None:
        cert = x509.load_pem_x509_certificate(cert_pem.encode('utf-8'))
        now = datetime.datetime.now(datetime.timezone.utc)
        if now < cert.not_valid_before_utc or now > cert.not_valid_after_utc:
            raise ValueError("Certificate is expired or not yet valid systematically.")

        common_names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not common_names or not common_names[0].value:
            raise ValueError("Certificate Common Name structural definitions distinctly empty.")

    def _resolve_base_dir(self) -> Path:
        if self.settings.environment == "test":
            return Path(__file__).parent.parent.parent / "tests" / "fixtures"
        return self.settings.fabric_wallet_path.resolve().parent

    def _initialize_from_metadata(self) -> None:
        wallet_path = self.settings.fabric_wallet_path.resolve()
        base_dir = self._resolve_base_dir()

        if not wallet_path.is_file():
            raise ValueError(f"Wallet path {wallet_path} critically absent disk physically.")

        metadata = json.loads(wallet_path.read_text(encoding='utf-8'))

        for target in ["Admin@bank01", "Admin@amf-regulateur"]:
            if target in metadata:
                info = metadata[target]
                if not isinstance(info, dict):
                    continue

                cert_path = Path(str(info.get("cert_path", ""))).resolve()
                key_path = Path(str(info.get("key_path", ""))).resolve()

                if not cert_path.is_relative_to(base_dir) or not key_path.is_relative_to(base_dir):
                    raise PermissionError("Path traversal bypass intercepted explicitly bounding limits natively.")

                if cert_path.exists() and key_path.exists():
                    self.put_identity(
                        label=target,
                        cert_pem=cert_path.read_text(encoding='utf-8'),
                        private_key_pem=key_path.read_text(encoding='utf-8'),
                        msp_id=str(info.get("msp_id", ""))
                    )
                else:
                    self._log_op(
                        logging.ERROR,
                        "Cryptographic targets pair physically absent disk",
                        {"label": target, "cert": str(cert_path), "key": str(key_path)}
                    )

    def get_identity(self, label: str) -> Identity:
        if label not in self._identities:
            self._log_op(logging.ERROR, "Identity struct isolation lookup missing internally", {"label": label})
            raise KeyError(f"Identity {label} absent logic mapping structurally.")
        return self._identities[label]

    def list_identities(self) -> list[str]:
        return list(self._identities.keys())

    def put_identity(self, label: str, cert_pem: str, private_key_pem: str, msp_id: str) -> None:
        self._validate_certificate(cert_pem)

        try:
            self._vault.secrets.kv.v2.create_or_update_secret(
                path=label,
                mount_point='rwa-fabric',
                secret={'private_key_pem': private_key_pem}
            )
            self._log_op(logging.INFO, "Identity private key securely stored in HashiCorp Vault", {"label": label})
        except Exception as e:
            self._log_op(logging.ERROR, f"Vault write failed: {e}", {"label": label})
            if self.settings.environment == "production":
                raise RuntimeError(f"Vault connectivity critically missing: {e}")

        self._identities[label] = Identity(
            label=label,
            cert_pem=cert_pem,
            msp_id=msp_id,
        )

        _zero_string(private_key_pem)

    @contextmanager
    def extract_private_key(self, label: str) -> Generator[str, None, None]:
        identity = self.get_identity(label)

        try:
            secret_response = self._vault.secrets.kv.v2.read_secret_version(
                path=label,
                mount_point='rwa-fabric',
            )
            decrypted_key = secret_response['data']['data']['private_key_pem']
            self._log_op(logging.INFO, "Private key extracted from Vault dynamically", {"label": label})
        except Exception as e:
            self._log_op(logging.ERROR, f"Failed extracting secret from Vault: {e}", {"label": label})
            raise RuntimeError(f"Vault key extraction failed: {e}")

        try:
            yield decrypted_key
        finally:
            _zero_string(decrypted_key)
WALLET_EOF

    cp "$WALLET_PATH" "${WALLET_PATH}.bak.$(date +%s)"
    cp /tmp/wallet_new.py "$WALLET_PATH"
    ok "wallet.py deployed"
fi

# ─── 5. KV ENGINE CHECK ──────────────────────────────────────────────
echo -e "\n${CYAN}=== 5. VAULT KV ENGINE CHECK ===${NC}"
KV_LIST=$(VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$SERVICE_TOKEN" \
    vault secrets list -format=json 2>/dev/null || echo '{}')
HAS_RWA=$(echo "$KV_LIST" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if 'rwa-fabric/' in d else 'no')" 2>/dev/null || echo "no")

if [ "$HAS_RWA" = "yes" ]; then
    ok "KV engine 'rwa-fabric/' is mounted"
else
    warn "KV engine 'rwa-fabric/' NOT found — needs root token to mount"
    if [ -n "${ROOT_TOKEN_ENV:-}" ]; then
        VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$ROOT_TOKEN_ENV" \
            vault secrets enable -path=rwa-fabric kv-v2 && \
            ok "KV engine 'rwa-fabric/' mounted" || warn "Already mounted or failed"
    fi
fi

# ─── 6. VAULT WRITE/READ TEST ────────────────────────────────────────
echo -e "\n${CYAN}=== 6. VAULT READ/WRITE TEST ===${NC}"
TEST_PATH="deploy-test-$(date +%s)"
TEST_VALUE="VAULT_INTEGRATION_OK_$(date +%Y%m%d)"

# Write
WRITE_RC=0
VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$SERVICE_TOKEN" \
    vault kv put rwa-fabric/"$TEST_PATH" private_key_pem="$TEST_VALUE" > /dev/null 2>&1 || WRITE_RC=$?

if [ $WRITE_RC -eq 0 ]; then
    ok "KV write to rwa-fabric/$TEST_PATH succeeded"
else
    fail "KV write FAILED (rc=$WRITE_RC) — check policy"
fi

# Read
READ_VAL=$(VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$SERVICE_TOKEN" \
    vault kv get -field=private_key_pem rwa-fabric/"$TEST_PATH" 2>/dev/null || echo "READ_FAILED")

if [ "$READ_VAL" = "$TEST_VALUE" ]; then
    ok "KV read verified: $READ_VAL"
else
    fail "KV read FAILED or value mismatch: got '$READ_VAL'"
fi

# Delete test secret
VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$SERVICE_TOKEN" \
    vault kv metadata delete rwa-fabric/"$TEST_PATH" > /dev/null 2>&1 && \
    ok "KV delete (metadata) succeeded" || warn "KV metadata delete failed (policy may need update)"

# ─── 7. LIST FABRIC SECRETS ──────────────────────────────────────────
echo -e "\n${CYAN}=== 7. FABRIC IDENTITY SECRETS IN VAULT ===${NC}"
SECRETS=$(VAULT_ADDR=$VAULT_ADDR_LOCAL VAULT_TOKEN="$SERVICE_TOKEN" \
    vault kv list rwa-fabric/ 2>/dev/null || echo "LIST_FAILED")
echo "$SECRETS"

if echo "$SECRETS" | grep -q "Admin@"; then
    ok "Fabric admin identities found in Vault"
else
    warn "No Fabric admin identities yet — will be populated on uvicorn startup"
fi

# ─── 8. PYTHON WALLET UNIT TEST ──────────────────────────────────────
echo -e "\n${CYAN}=== 8. PYTHON WALLET INTEGRATION TEST ===${NC}"
python3 << PYTEST
import os, sys
sys.path.insert(0, '${PROJECT_DIR}')
os.environ.setdefault('ENVIRONMENT', 'production')

import hvac

SERVICE_TOKEN = '${SERVICE_TOKEN}'
VAULT_ADDR    = '${VAULT_ADDR_LOCAL}'

client = hvac.Client(url=VAULT_ADDR, token=SERVICE_TOKEN)

print(f"  authenticated : {client.is_authenticated()}")
assert client.is_authenticated(), "FAIL: not authenticated"

# Write via Python (same as FabricWallet.put_identity)
client.secrets.kv.v2.create_or_update_secret(
    path='python-wallet-test',
    mount_point='rwa-fabric',
    secret={'private_key_pem': '-----BEGIN RSA PRIVATE KEY-----\nTEST_KEY\n-----END RSA PRIVATE KEY-----'}
)
print("  put_identity  : OK (write to rwa-fabric/python-wallet-test)")

# Read via Python (same as FabricWallet.extract_private_key)
resp = client.secrets.kv.v2.read_secret_version(
    path='python-wallet-test',
    mount_point='rwa-fabric',
)
val = resp['data']['data']['private_key_pem']
assert 'TEST_KEY' in val, f"FAIL: unexpected value '{val}'"
print(f"  extract_key   : OK (got key with {len(val)} chars)")

# Cleanup
try:
    client.secrets.kv.v2.delete_metadata_and_all_versions(
        path='python-wallet-test',
        mount_point='rwa-fabric',
    )
    print("  cleanup       : OK (delete_metadata succeeded)")
except Exception as e:
    print(f"  cleanup       : WARN — {e} (non-critical)")

print("\n  [RESULT] hvac wallet integration: PASS")
PYTEST

# ─── 9. SERVICE RESTART ──────────────────────────────────────────────
echo -e "\n${CYAN}=== 9. RESTART BACKEND SERVICES ===${NC}"

for SVC in rwa-uvicorn rwa-celery; do
    if echo "$PASS" | sudo -S systemctl is-enabled "$SVC" &>/dev/null; then
        echo "$PASS" | sudo -S systemctl restart "$SVC" && \
            ok "$SVC restarted" || fail "$SVC restart failed"
    else
        warn "$SVC not enabled/found — skipping"
    fi
done

sleep 4

# ─── 10. UVICORN HEALTH CHECK ────────────────────────────────────────
echo -e "\n${CYAN}=== 10. API HEALTH CHECK ===${NC}"
for i in 1 2 3; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        ok "API /health → HTTP 200"
        break
    fi
    warn "Attempt $i: HTTP $HTTP_CODE — waiting..."
    sleep 3
done

# ─── 11. UVICORN LOG TAIL (Vault lines) ──────────────────────────────
echo -e "\n${CYAN}=== 11. UVICORN STARTUP LOGS (Vault-related) ===${NC}"
echo "$PASS" | sudo -S journalctl -u rwa-uvicorn --no-pager -n 50 2>/dev/null | \
    grep -iE "(vault|wallet|identity|fabric|error|warning)" | tail -20 || \
    warn "No uvicorn logs found"

# ─── 12. RUN UNIT TESTS ──────────────────────────────────────────────
echo -e "\n${CYAN}=== 12. PROJECT UNIT TESTS ===${NC}"
cd "$PROJECT_DIR"
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    python -m pytest tests/unit/ -v --tb=short -q 2>&1 | tail -40 || warn "Some tests failed"
else
    warn "No venv found at ${PROJECT_DIR}/.venv — skipping pytest"
fi

# ─── SUMMARY ─────────────────────────────────────────────────────────
echo ""
echo "================================================================"
echo " DEPLOY & TEST COMPLETE — $(date)"
echo "================================================================"
