import pytest
import tenseal as ts
from backend.features.fhe.context import create_ckks_context, serialize_context, deserialize_context
from backend.features.fhe.scorer import FHEClient, FHEScorer

@pytest.fixture(scope="module")
def fhe_context():
    """Provides a single FHE context for the entire test module to save time."""
    return create_ckks_context()

def test_context_creation_and_serialization(fhe_context):
    """Test that context can be created and serialized without the secret key."""
    # Serialize keeping the secret key (Client side)
    client_bytes = serialize_context(fhe_context, save_secret_key=True)
    assert len(client_bytes) > 0
    
    # Serialize dropping the secret key (Server side)
    server_bytes = serialize_context(fhe_context, save_secret_key=False)
    assert len(server_bytes) > 0

    # Test deserialization
    restored_context = deserialize_context(server_bytes)
    assert restored_context.is_private() is False # Secret key is gone
    assert restored_context.is_public() is True

def test_client_encryption_decryption(fhe_context):
    """Test that a client can encrypt and decrypt without alteration."""
    client = FHEClient(fhe_context)
    j_risk, cb_risk, v_risk = 0.5, 0.5, 0.5
    
    enc_tensor = client.encrypt_indicators(j_risk, cb_risk, v_risk)
    
    # Check that it's actually encrypted (TenSEAL tensor)
    assert isinstance(enc_tensor, ts.CKKSTensor)
    
    # Decrypt and verify
    raw = enc_tensor.decrypt().tolist()
    assert len(raw) == 3
    assert abs(raw[0] - j_risk) < 0.001
    assert abs(raw[1] - cb_risk) < 0.001
    assert abs(raw[2] - v_risk) < 0.001

def test_server_homomorphic_evaluation(fhe_context):
    """Test that the server computes the correct weighted AML score blindly."""
    client = FHEClient(fhe_context)
    server = FHEScorer(fhe_context)
    
    # 1. Client encrypts (Jurisdiction: 0.8, Cross-border: 0.6, Volume: 0.9)
    j_risk, cb_risk, v_risk = 0.8, 0.6, 0.9
    enc_indicators = client.encrypt_indicators(j_risk, cb_risk, v_risk)
    
    # 2. Server evaluates
    enc_score = server.compute_encrypted_score(enc_indicators)
    assert isinstance(enc_score, ts.CKKSTensor)
    
    # 3. Client decrypts
    decrypted_score = client.decrypt_score(enc_score)
    
    # 4. Verify Accuracy
    # Formula: J*0.3 + CB*0.4 + V*0.3
    expected_score = round((0.8 * 0.3) + (0.6 * 0.4) + (0.9 * 0.3), 4)
    
    assert abs(decrypted_score - expected_score) < 0.001

def test_server_evaluation_extreme_values(fhe_context):
    """Test the scoring logic with edge cases (all zeros and all ones)."""
    client = FHEClient(fhe_context)
    server = FHEScorer(fhe_context)
    
    # All zeros
    enc_zero = client.encrypt_indicators(0.0, 0.0, 0.0)
    score_zero = client.decrypt_score(server.compute_encrypted_score(enc_zero))
    assert abs(score_zero - 0.0) < 0.001
    
    # All ones
    enc_ones = client.encrypt_indicators(1.0, 1.0, 1.0)
    score_ones = client.decrypt_score(server.compute_encrypted_score(enc_ones))
    assert abs(score_ones - 1.0) < 0.001
