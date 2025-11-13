import numpy as np
import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from z3_synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

# try to implement sdg gate
# with d = 2, expect two tdg gates, it is equivalent
n = 2
d1 = 1
gen = SMTLibGenerator()

# DYADIC VERSION
input_vector = [Cyclotomic8Dyadic.zero(gen) for _ in range(2**n)]
input_vector[0] = Cyclotomic8Dyadic.one(gen)

input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k = 0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[2**n - 1] = Cyclotomic8Dyadic.one(gen)

output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k = 0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[2**n - 1] = Cyclotomic8Dyadic.one(gen).multiply_by_minus_i(gen)

vector_pairs = [(input_vec, output_vec)]
gate_set = ['I', 'H', 'S', 'T', 'CNOT', 'Tdg', 'Sdg']

start_time = time.time()
synthesis(vector_pairs, n, d1, "sdg.smt2", gen, gate_set)
solve_and_extract_circuit("sdg.smt2", n, d1, "sdg.qasm", "z3")
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")