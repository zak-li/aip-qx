"""Privacy-preserving AML scoring via HElib CKKS.

The client encrypts its three risk indicators locally; the server computes
the weighted sum entirely on the ciphertext and decrypts only the final
scalar score — the raw indicator values are never visible to the server.

Scoring pipeline:
    1. FHEClient.encrypt_indicators()  → ciphertext bytes
    2. FHEScorer.compute_score()       → decrypted float (server-side)
"""
from __future__ import annotations

from core.features.fhe.context import get_session

WEIGHT_JURISDICTION: float = 0.3
WEIGHT_CROSS_BORDER: float = 0.4
WEIGHT_VOLUME: float = 0.3

_WEIGHTS = [WEIGHT_JURISDICTION, WEIGHT_CROSS_BORDER, WEIGHT_VOLUME]


class FHEClient:
    """Client-side component: encrypts risk indicators into a CKKS ciphertext."""

    def encrypt_indicators(
        self,
        jurisdiction: float,
        cross_border: float,
        volume: float,
    ) -> bytes:
        """Return an opaque ciphertext encoding the three indicators."""
        session = get_session()
        return bytes(session.encrypt([jurisdiction, cross_border, volume]))


class FHEScorer:
    """Server-side component: scores the encrypted indicators homomorphically."""

    def compute_score(self, ciphertext: bytes) -> float:
        """Multiply by AML weights, sum slots, decrypt — returns a score in [0, 1].

        The server never accesses the plaintext indicators; only the final
        weighted sum is decrypted.
        """
        session = get_session()
        raw = session.score(ciphertext, _WEIGHTS)
        return round(float(raw), 4)
