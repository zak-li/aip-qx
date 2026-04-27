"""FHE Context and Key Management using TenSEAL (CKKS).

CKKS (Cheon-Kim-Kim-Song) is the preferred homomorphic encryption scheme
for approximate floating-point arithmetic.
"""
import tenseal as ts

def create_ckks_context() -> ts.Context:
    """Create a TenSEAL context for CKKS.
    
    Security parameters:
    - poly_modulus_degree = 8192 (Provides ~128 bits of security)
    - coeff_mod_bit_sizes = [60, 40, 40, 60] (Suitable for our depth of multiplications)
    - global_scale = 2**40 (Precision for floats)
    """
    context = ts.context(
        ts.SCHEME_TYPE.CKKS,
        poly_modulus_degree=8192,
        coeff_mod_bit_sizes=[60, 40, 40, 60]
    )

    context.global_scale = 2**40

    # We generate Galois keys for vector rotations (not strictly needed for just scalar mults,
    # but good practice for full vectors)
    context.generate_galois_keys()

    return context

def serialize_context(context: ts.Context, save_secret_key: bool = False) -> bytes:
    """Serialize the context to send it over the network."""
    return context.serialize(save_secret_key=save_secret_key)

def deserialize_context(data: bytes) -> ts.Context:
    """Load the context from bytes."""
    return ts.context_from(data)
