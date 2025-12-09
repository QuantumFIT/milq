import numpy as np
import sys
import os
import time
import resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

# --- parameters ---
if len(sys.argv) > 1:
    n = int(sys.argv[1])
    d1 = int(sys.argv[2])
    solver = sys.argv[3]
    k_glob = int(sys.argv[4])
    oracle_type = sys.argv[5]
else:
    n = 2
    d1 = 9
    solver = "cvc5"
    k_glob = 6
    oracle_type = "b"

assert(d1 == (2*(n+1) + 1 + n))
assert(k_glob == 2*(n + 1))

gen = SMTLibGenerator()
qubits = 2*n + 1

vector_pairs = []

def f(x):
    if oracle_type == "0":
        return 0
    elif oracle_type == "1":
        return 1
    elif oracle_type == "b":
        bits = [(x >> (n-1-i)) & 1 for i in range(n)]
        parity = 0
        for b in bits:
            parity ^= b
        return parity
    else:
        raise ValueError("Unknown oracle type")

for q in range(2**n):
    input_vec = Vector(q=2**n, generator=gen,
                       element_representation=Cyclotomic8Dyadic, k=0)
    for i in range(2**n):
        input_vec[i] = Cyclotomic8Dyadic.zero(gen)
    input_vec[q] = Cyclotomic8Dyadic.one(gen)

    # output vector
    output_vec = Vector(q=2**n, generator=gen,
                        element_representation=Cyclotomic8Dyadic, k=k_glob)
    for i in range(2**n):
        output_vec[i] = Cyclotomic8Dyadic.zero(gen)
    fx = f(q)
    output_idx = (q << (n+1)) | (q << 1) | fx
    output_vec[output_idx] = Cyclotomic8Dyadic.one(gen)

    vector_pairs.append((input_vec, output_vec))

# --- gate set ---
gate_set = ['I', 'H', 'CX', 'Z', 'CCX']

start_time = time.time()
try:
    synthesis(vector_pairs, qubits, d1, "dj.smt2", gen, gate_set)
    solve_and_extract_circuit("dj.smt2", qubits, d1, "dj.qasm", solver)

    end_time = time.time()

    print("sat")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

except Exception as e:
    print(f"Error: {e}")
    print("unsat")
