"""Encrypted AML Scoring Logic.

The client encrypts the risk indicators. The server computes the weighted 
sum without seeing the underlying values.
"""
from __future__ import annotations
import tenseal as ts

# Standard AML weights from our plaintext logic
WEIGHT_JURISDICTION = 0.3
WEIGHT_CROSS_BORDER = 0.4
WEIGHT_VOLUME = 0.3

class FHEScorer:
    """Server-side component: Performs computations on encrypted data."""

    def __init__(self, context: ts.Context):
        self.context = context

    def compute_encrypted_score(self, enc_indicators: ts.CKKSTensor) -> ts.CKKSTensor:
        """Computes the weighted AML score entirely homomorphically.
        
        Args:
            enc_indicators: A TenSEAL CKKSTensor containing 
                            [jurisdiction_risk, cross_border_activity, unusual_volume]
        Returns:
            An encrypted tensor containing the final baseline score.
        """
        # In FHE, we can multiply an encrypted vector by a plaintext vector
        weights = [WEIGHT_JURISDICTION, WEIGHT_CROSS_BORDER, WEIGHT_VOLUME]

        # enc_indicators * weights does element-wise multiplication
        # Then we sum the elements.
        weighted_vector = enc_indicators * weights

        # We need the sum of the vector components.
        # TenSEAL supports sum() over the vector.
        # Alternatively, we could do dot product if they were both vectors,
        # but CKKSTensor * list is element-wise.

        # Using polyval or dot product is faster, but simple sum works for small vectors.
        # For a 1D tensor, we can just sum it.
        enc_score = weighted_vector.sum()

        return enc_score

class FHEClient:
    """Client-side component: Encrypts data and decrypts results."""

    def __init__(self, context: ts.Context):
        self.context = context

    def encrypt_indicators(self, jurisdiction: float, cross_border: float, volume: float) -> ts.CKKSTensor:
        """Encrypts the 3 indicators into a single ciphertext vector."""
        vec = [jurisdiction, cross_border, volume]
        return ts.ckks_tensor(self.context, vec)

    def decrypt_score(self, enc_score: ts.CKKSTensor) -> float:
        """Decrypts the final score returned by the server."""
        # The result of sum() might be a tensor. We decrypt and take the first (and only) element.
        raw = enc_score.decrypt().tolist()
        val = raw[0] if isinstance(raw, list) else raw
        return round(float(val), 4)
