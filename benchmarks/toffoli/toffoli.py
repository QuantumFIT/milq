import numpy as np
import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

n = 3
d1 = 16
gen = SMTLibGenerator()

vector_pairs = []
for state in range(2**n):
    input_vector = [Cyclotomic8Dyadic.zero(gen) for _ in range(2**n)]
    input_vector[state] = Cyclotomic8Dyadic.one(gen)
    
    a = (state >> 2) & 1
    b = (state >> 1) & 1
    c = state & 1
    output_state = (a << 2) | (b << 1) | (c ^ (a & b))
    
    output_vector = [Cyclotomic8Dyadic.zero(gen) for _ in range(2**n)]
    output_vector[output_state] = Cyclotomic8Dyadic.one(gen)
    
    vector_pairs.append((input_vector, output_vector))

start_time = time.time()
synthesis(vector_pairs, n, d1, "toffoli.smt2", gen)
solve_and_extract_circuit("toffoli.smt2", n, d1, "toffoli.qasm", "z3")
print(f"Time taken: {time.time() - start_time:.2f} s")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")
