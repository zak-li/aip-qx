from backend.features.zkp.crypto import SchnorrProof, generate_keypair, schnorr_prove, schnorr_verify
from backend.features.zkp.merkle import MerkleTree, verify_non_membership


def test_schnorr_proof_validity():
    """Test that a valid Schnorr proof verifies correctly."""
    x, Y = generate_keypair()
    context = b"test_context"
    
    proof, nullifier = schnorr_prove(x, Y, context)
    
    assert proof is not None
    assert nullifier is not None
    assert len(nullifier) == 32
    
    # Verification should succeed
    is_valid = schnorr_verify(proof, Y, context)
    assert is_valid is True

def test_schnorr_proof_invalid_context():
    """Test that altering the context invalidates the proof."""
    x, Y = generate_keypair()
    context = b"test_context"
    
    proof, _ = schnorr_prove(x, Y, context)
    
    # Verification with different context should fail
    bad_context = b"altered_context"
    is_valid = schnorr_verify(proof, Y, bad_context)
    assert is_valid is False

def test_schnorr_proof_invalid_key():
    """Test that verifying with the wrong public key invalidates the proof."""
    x, Y = generate_keypair()
    _, Y_wrong = generate_keypair()
    context = b"test_context"
    
    proof, _ = schnorr_prove(x, Y, context)
    
    # Verification with wrong public key should fail
    is_valid = schnorr_verify(proof, Y_wrong, context)
    assert is_valid is False

def test_schnorr_proof_tampered_scalar():
    """Test that altering the response scalar invalidates the proof."""
    x, Y = generate_keypair()
    context = b"test_context"
    
    proof, _ = schnorr_prove(x, Y, context)
    
    # Tamper with the scalar s
    bad_proof = SchnorrProof(Rx=proof.Rx, Ry=proof.Ry, s=proof.s + 1)
    
    is_valid = schnorr_verify(bad_proof, Y, context)
    assert is_valid is False

def test_merkle_tree_build():
    """Test that building a Merkle tree from a sorted list of names works."""
    names = ["Alice", "Bob", "Charlie", "Dave"]
    tree = MerkleTree.build(names)
    
    assert tree is not None
    assert tree.root is not None
    # Ensure it's sorted lowercase
    assert tree.sorted_names == ["alice", "bob", "charlie", "dave"]

def test_merkle_non_membership_proof_valid():
    """Test generating and verifying a valid non-membership proof."""
    names = ["Alice", "Bob", "Dave"]  # Charlie is missing
    tree = MerkleTree.build(names)
    
    proof = tree.non_membership_proof("Charlie")
    
    assert proof is not None
    assert proof.queried_name == "Charlie"
    assert proof.left_leaf_name == "bob"
    assert proof.right_leaf_name == "dave"
    
    # Verify the proof against the root
    is_valid = verify_non_membership(proof, tree.root.hex())
    assert is_valid is True

def test_merkle_non_membership_proof_present():
    """Test that requesting a non-membership proof for an existing element returns None."""
    names = ["Alice", "Bob", "Charlie", "Dave"]
    tree = MerkleTree.build(names)
    
    proof = tree.non_membership_proof("Charlie")
    
    # Should not be able to generate a non-membership proof if the person is in the list
    assert proof is None
