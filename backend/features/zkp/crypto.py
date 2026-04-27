"""Schnorr sigma protocol over secp256k1 (Fiat-Shamir NIZK).

Proof of knowledge of discrete log:  PROVE you know x  s.t.  Y = x*G
without revealing x.

Protocol (Schnorr / Fiat-Shamir):
  Prove:
    k  <- random scalar
    R  = k * G
    c  = SHA256(R || Y || context)           # challenge (Fiat-Shamir)
    s  = (k - c*x) mod N
    nullifier = SHA256("NULLIFIER" | x | context)
    return SchnorrProof(R, s), nullifier

  Verify:
    c  = SHA256(R || Y || context)
    R' = s*G + c*Y
    accept iff R' == R
"""
from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass

from py_ecc.secp256k1.secp256k1 import G, N, P, add, multiply

Point = tuple[int, int]


# secp256k1: y² ≡ x³ + 7  (mod P)
_SECP256K1_B = 7


def is_on_curve(point: Point) -> bool:
    """Return True iff `point` is a valid affine point on secp256k1.

    Rejects the point at infinity, points outside the field, and points whose
    coordinates do not satisfy the curve equation. Without this check, an
    attacker can submit `(0, 0)` or other invalid points and bypass Schnorr
    verification because `multiply(invalid, scalar)` may return None or
    behave unexpectedly.
    """
    if point is None:
        return False
    try:
        x, y = point
    except (TypeError, ValueError):
        return False
    if not (0 <= x < P) or not (0 <= y < P):
        return False
    return (y * y - x * x * x - _SECP256K1_B) % P == 0


# ── helpers ──────────────────────────────────────────────────────────────────

def _point_to_bytes(p: Point) -> bytes:
    return p[0].to_bytes(32, "big") + p[1].to_bytes(32, "big")


def _scalar_from_bytes(b: bytes) -> int:
    return int.from_bytes(b, "big") % N


def _hash_to_scalar(*parts: bytes) -> int:
    h = hashlib.sha256()
    for part in parts:
        h.update(struct.pack(">I", len(part)))
        h.update(part)
    return _scalar_from_bytes(h.digest())


def random_scalar() -> int:
    while True:
        x = int.from_bytes(os.urandom(32), "big")
        if 1 <= x < N:
            return x


# ── key generation ────────────────────────────────────────────────────────────

def generate_keypair() -> tuple[int, Point]:
    """Return (private_key_int, public_key_point)."""
    x = random_scalar()
    Y = multiply(G, x)
    return x, Y


def public_key_from_private(x: int) -> Point:
    return multiply(G, x)


# ── proof structure ───────────────────────────────────────────────────────────

@dataclass(slots=True)
class SchnorrProof:
    Rx: int   # R = k*G  (x-coord)
    Ry: int   # R        (y-coord)
    s: int    # response scalar

    def to_dict(self) -> dict:
        return {
            "Rx": hex(self.Rx),
            "Ry": hex(self.Ry),
            "s":  hex(self.s),
        }

    @classmethod
    def from_dict(cls, d: dict) -> SchnorrProof:
        return cls(
            Rx=int(d["Rx"], 16),
            Ry=int(d["Ry"], 16),
            s=int(d["s"], 16),
        )


# ── prove ─────────────────────────────────────────────────────────────────────

def schnorr_prove(x: int, Y: Point, context: bytes) -> tuple[SchnorrProof, bytes]:
    """Generate a Schnorr NIZK proof + nullifier.

    Args:
        x:       private key scalar
        Y:       public key point (must equal x*G)
        context: domain-separation bytes (e.g. b"asset_transfer:<asset_id>")

    Returns:
        (proof, nullifier_bytes)
    """
    k = random_scalar()
    R: Point = multiply(G, k)

    c = _hash_to_scalar(_point_to_bytes(R), _point_to_bytes(Y), context)
    s = (k - c * x) % N

    nullifier = hashlib.sha256(
        b"NULLIFIER" + x.to_bytes(32, "big") + context
    ).digest()

    return SchnorrProof(R[0], R[1], s), nullifier


# ── verify ────────────────────────────────────────────────────────────────────

def schnorr_verify(proof: SchnorrProof, Y: Point, context: bytes) -> bool:
    """Verify a Schnorr NIZK proof without learning x.

    Validates both the public key and the commitment lie on the curve before
    running the verification equation, so attacker-supplied invalid points
    cannot short-circuit the check.
    """
    R = (proof.Rx, proof.Ry)

    if not is_on_curve(Y) or not is_on_curve(R):
        return False
    if not (0 <= proof.s < N):
        return False

    c = _hash_to_scalar(_point_to_bytes(R), _point_to_bytes(Y), context)

    # R' = s*G + c*Y  must equal  R
    sG = multiply(G, proof.s % N)
    cY = multiply(Y, c % N)
    R_check = add(sG, cY)

    return R_check is not None and R_check == R


# ── serialisation helpers ─────────────────────────────────────────────────────

def point_to_hex(p: Point) -> tuple[str, str]:
    return hex(p[0]), hex(p[1])


def point_from_hex(x_hex: str, y_hex: str) -> Point:
    return int(x_hex, 16), int(y_hex, 16)
