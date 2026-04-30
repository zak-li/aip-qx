from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ── key setup ─────────────────────────────────────────────────────────────────

class SetupKeyRequest(BaseModel):
    public_key_x: str = Field(..., description="secp256k1 public key X coordinate (hex)")
    public_key_y: str = Field(..., description="secp256k1 public key Y coordinate (hex)")


class SetupKeyResponse(BaseModel):
    credential_id: str
    claim: dict[str, Any]
    issuer_sig: str           # ECDSA signature (hex) — client stores this
    expires_at: datetime
    sanctions_tree_root: str  # Merkle root of the current sanctions tree


# ── proof submission ──────────────────────────────────────────────────────────

class ProofRequest(BaseModel):
    public_key_x: str = Field(..., description="secp256k1 public key X (hex)")
    public_key_y: str = Field(..., description="secp256k1 public key Y (hex)")
    # Schnorr proof
    proof_Rx: str = Field(..., description="Schnorr commitment R.x (hex)")
    proof_Ry: str = Field(..., description="Schnorr commitment R.y (hex)")
    proof_s: str  = Field(..., description="Schnorr response scalar s (hex)")
    # Domain context
    purpose: str  = Field(..., max_length=128, description="e.g. asset_transfer")
    context: str  = Field(..., max_length=256, description="Purpose-specific context string")
    # One-time nullifier (SHA-256(user_secret || context_bytes))
    nullifier: str = Field(..., description="Hex-encoded nullifier")
    # Credential (claim + sig) — server re-verifies it was issued by this platform
    credential_claim: dict[str, Any]
    credential_sig: str


class ProofResponse(BaseModel):
    valid: bool
    purpose: str
    message: str


# ── status ────────────────────────────────────────────────────────────────────

class ZKPStatusResponse(BaseModel):
    credential_id: str | None
    has_credential: bool
    age_ok: bool
    kyc_ok: bool
    not_sanctioned: bool
    kyc_level: int
    expires_at: datetime | None
    revoked: bool
    sanctions_tree_root: str
