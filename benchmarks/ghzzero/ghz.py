import numpy as np
import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from z3_synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator


# optional sys arguments n, d1, solver
if len(sys.argv) > 1:
    n = int(sys.argv[1])
    d1 = int(sys.argv[2])
    solver = sys.argv[3]
else:
    n = 2
    d1 = n
    solver = "z3"
gen = SMTLibGenerator()

assert(n == d1)

#REALS VERSION
# input |0^n>
#input_vector = [Complex.zero(gen) for _ in range(2**n)]
#input_vector[0] = Complex.one(gen)

# output |0^n> * 1/sqrt(2) + (|1> tensor |0^n-1>) * 1/sqrt(2)
#output_vector = [Complex.zero(gen) for _ in range(2**n)]
#output_vector[0] = Complex.inv_sqrt2(gen)
#output_vector[2**n - 1] = Complex.inv_sqrt2(gen)
#vector_pairs = [(input_vector, output_vector)]


# DYADIC VERSION
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k = 0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[0] = Cyclotomic8Dyadic.one(gen)

output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k = 1)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[0] = Cyclotomic8Dyadic.one(gen)
output_vec[2**n - 1] = Cyclotomic8Dyadic.one(gen)

vector_pairs = [(input_vec, output_vec)]
gate_set = ['I', 'H', 'S', 'T', 'CX']

start_time = time.time()
try:
    synthesis(vector_pairs, n, d1, "ghzzero.smt2", gen, gate_set)
    solve_and_extract_circuit("ghzzero.smt2", n, d1, "ghzzero.qasm", solver)
    end_time = time.time()
    print(f"sat")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")
except Exception:
    print(f"unsat")