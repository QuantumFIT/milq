import numpy as np
import sys
import os
import time
import resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import Synthesizer
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic, nTuple
from smtlib_generator import SMTLibGenerator
from sim import simulate_circuit

if len(sys.argv) > 1:
    n = int(sys.argv[1])
    d1 = int(sys.argv[2])
    solver = sys.argv[3]
    s = sys.argv[4]
    k_glob = int(sys.argv[5])
    a = int(sys.argv[6])
else:
    n = 2
    d1 = 6
    solver = "dreal"
    s = "11"
    k_glob = 4
    a = 2**n
assert(2*n == k_glob)
assert(d1 == (2*n + 1 + (n // 2)))
assert(len(s) == n)
assert(a == 2**n)

n = 1
d1 = 2
gen = SMTLibGenerator(dreal=True)
gate_set = ['H']
synthesizer = Synthesizer(gen=gen, gate_set=gate_set, solver=solver)

input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[0] = Cyclotomic8Dyadic.one(gen)

# "mock" hadamard output -- check rescaling
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=8)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[0] = Cyclotomic8Dyadic.one(gen)
output_vec[0].a = 16

vectors = [(input_vec, output_vec)]

start_time = time.time()
try:
    synthesizer.synthesis(vectors, n, d1, "bv.smt2")
    print(gen.generate(Cyclotomic8Dyadic))
    synthesizer.solve_and_extract_circuit("bv.smt2", n, d1, "bv.qasm", solver)

    end_time = time.time()

    print("sat")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

except Exception as e:
    print(f"Error: {e}")
    print("unsat")
