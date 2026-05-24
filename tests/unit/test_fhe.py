"""Tests for the HElib CKKS FHE scoring pipeline.

These tests verify the FHEClient / FHEScorer API that wraps HElib CKKS.
They skip automatically if the native extension has not been compiled.

Scoring formula: score = J*0.3 + CB*0.4 + V*0.3
"""
import pytest

from core.features.fhe.scorer import FHEClient, FHEScorer


@pytest.fixture(scope="module")
def fhe_available():
    """Skip the entire module if HElib CKKS is not built."""
    try:
        from core.features.fhe.context import get_session
        get_session()
    except RuntimeError:
        pytest.skip("HElib CKKS native extension not compiled — skipping FHE tests")


@pytest.fixture
def client():
    return FHEClient()


@pytest.fixture
def scorer():
    return FHEScorer()


class TestFHEEncryptionRoundTrip:
    """Verify that encrypt → score produces correct weighted sums."""

    def test_balanced_indicators(self, fhe_available, client, scorer):
        """Standard case: 0.8 / 0.6 / 0.9 → 0.3*0.8 + 0.4*0.6 + 0.3*0.9 = 0.75"""
        ciphertext = client.encrypt_indicators(0.8, 0.6, 0.9)
        assert isinstance(ciphertext, bytes)
        assert len(ciphertext) > 0

        score = scorer.compute_score(ciphertext)
        expected = round((0.8 * 0.3) + (0.6 * 0.4) + (0.9 * 0.3), 4)
        assert abs(score - expected) < 0.01

    def test_all_zeros(self, fhe_available, client, scorer):
        """Zero risk everywhere → score = 0.0"""
        ciphertext = client.encrypt_indicators(0.0, 0.0, 0.0)
        score = scorer.compute_score(ciphertext)
        assert abs(score - 0.0) < 0.01

    def test_all_ones(self, fhe_available, client, scorer):
        """Maximum risk → score = 1.0"""
        ciphertext = client.encrypt_indicators(1.0, 1.0, 1.0)
        score = scorer.compute_score(ciphertext)
        assert abs(score - 1.0) < 0.01

    def test_ciphertext_is_opaque(self, fhe_available, client):
        """Ciphertext should not leak plaintext indicator values."""
        ct = client.encrypt_indicators(0.5, 0.5, 0.5)
        # The raw bytes should not contain recognisable float patterns
        assert b"0.5" not in ct

    def test_different_inputs_different_ciphertexts(self, fhe_available, client):
        """Two different inputs must produce different ciphertexts."""
        ct1 = client.encrypt_indicators(0.1, 0.2, 0.3)
        ct2 = client.encrypt_indicators(0.9, 0.8, 0.7)
        assert ct1 != ct2
