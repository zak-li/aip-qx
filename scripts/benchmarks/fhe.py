#!/usr/bin/env python3
"""
Benchmark suite for the FHE-AML Scoring Protocol (Plaintext vs TenSEAL CKKS).
Measures Encryption Time, Server Evaluation Time, Decryption Time, and Size.

Usage:
  python scripts/benchmarks/fhe.py
"""

import os
import sys
import time
from statistics import mean, stdev

# Add the project root to python path to import the backend
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.features.fhe.context import create_ckks_context, serialize_context
from core.features.fhe.scorer import FHEClient, FHEScorer

ITERATIONS = 100

def benchmark_fhe():
    print("Initializing FHE Context (this takes a moment)...")
    context = create_ckks_context()
    
    client = FHEClient(context)
    # Server gets the context but typically without the secret key. 
    # For this local benchmark, we use the same context object.
    # In production: context.make_context_public() drops the secret key.
    public_context_bytes = serialize_context(context, save_secret_key=False)
    print(f"Public Context Size (sent to Server): {len(public_context_bytes) / 1024:.2f} KB")
    
    server = FHEScorer(context)
    
    # Mock Risk Indicators for the user
    # [jurisdiction_risk, cross_border, volume]
    j_risk = 0.85
    cb_risk = 0.60
    v_risk = 0.90
    
    # Expected Plaintext Score: (0.85*0.3) + (0.60*0.4) + (0.90*0.3) = 0.255 + 0.240 + 0.270 = 0.765
    expected_score = round((j_risk * 0.3) + (cb_risk * 0.4) + (v_risk * 0.3), 4)
    
    enc_times = []
    eval_times = []
    dec_times = []
    plain_times = []
    ciphertext_sizes = []
    
    print(f"Running FHE benchmarks ({ITERATIONS} iterations)...")
    
    for i in range(ITERATIONS):
        # 1. Plaintext baseline — we time the arithmetic itself; the
        # result isn't used (we benchmark latency, not correctness).
        t0 = time.perf_counter()
        _ = (j_risk * 0.3) + (cb_risk * 0.4) + (v_risk * 0.3)
        t1 = time.perf_counter()
        plain_times.append((t1 - t0) * 1000)
        
        # 2. Client Encryption
        t0 = time.perf_counter()
        enc_indicators = client.encrypt_indicators(j_risk, cb_risk, v_risk)
        t1 = time.perf_counter()
        enc_times.append((t1 - t0) * 1000)
        
        if i == 0:
            ciphertext_sizes.append(len(enc_indicators.serialize()))
            
        # 3. Server Evaluation
        t0 = time.perf_counter()
        enc_score = server.compute_encrypted_score(enc_indicators)
        t1 = time.perf_counter()
        eval_times.append((t1 - t0) * 1000)
        
        # 4. Client Decryption
        t0 = time.perf_counter()
        decrypted_score = client.decrypt_score(enc_score)
        t1 = time.perf_counter()
        dec_times.append((t1 - t0) * 1000)
        
        assert abs(decrypted_score - expected_score) < 0.001, f"FHE Math error: expected {expected_score}, got {decrypted_score}"

    print("\n" + "="*80)
    print(" FHE-AML Performance Benchmark Results ".center(80, "="))
    print("="*80)
    
    print(f"{'Metric':<30} | {'Average (ms)':<20} | {'Std Dev (ms)':<20}")
    print("-" * 80)
    print(f"{'Plaintext Scoring':<30} | {mean(plain_times):<20.4f} | {stdev(plain_times) if len(plain_times)>1 else 0:<20.4f}")
    print(f"{'FHE Client Encryption':<30} | {mean(enc_times):<20.2f} | {stdev(enc_times):<20.2f}")
    print(f"{'FHE Server Evaluation':<30} | {mean(eval_times):<20.2f} | {stdev(eval_times):<20.2f}")
    print(f"{'FHE Client Decryption':<30} | {mean(dec_times):<20.2f} | {stdev(dec_times):<20.2f}")
    print("-" * 80)
    print(f"Encrypted Tensor Size: {ciphertext_sizes[0] / 1024:.2f} KB")
    print(f"Accuracy Check: Plaintext ({expected_score}) == FHE ({decrypted_score}) -> PASSED")
    print("="*80)

if __name__ == "__main__":
    benchmark_fhe()
