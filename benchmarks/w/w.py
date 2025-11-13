import numpy as np
import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from z3_synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

n = 3
d1 = 10
gen = SMTLibGenerator()

# REALS
#input_vector = [Complex.zero(gen) for _ in range(2**n)]
#input_vector[0] = Complex.one(gen)
#output_vector = [Complex.zero(gen) for _ in range(2**n)]
#for i in range(n):
#    output_vector[1 << (n - 1 - i)] = Complex.inv_sqrt2(gen)
#vector_pairs = [(input_vector, output_vector)]


# DYADIC
# Input: |0^n>
input_vector = [Cyclotomic8Dyadic.zero(gen) for _ in range(2**n)]
input_vector[0] = Cyclotomic8Dyadic.one(gen)

# Output: |W_n> = (|100...0> + |010...0> + ... + |000...1>) / sqrt(n)
output_vector = [Cyclotomic8Dyadic.zero(gen) for _ in range(2**n)]
for i in range(n):
    output_vector[1 << (n - 1 - i)] = Cyclotomic8Dyadic.inv_sqrt2(gen)
vector_pairs = [(input_vector, output_vector)]

start_time = time.time()
synthesis(vector_pairs, n, d1, "w_state.smt2", gen)
solve_and_extract_circuit("w_state.smt2", n, d1, "w_state.qasm", "z3")
print(f"Time taken: {time.time() - start_time:.2f} s")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")
