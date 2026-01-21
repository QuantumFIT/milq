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

n = 1
d1 = 2
solver = "dreal"

res = simulate_circuit("test.qasm", complex_representation=Cyclotomic8Dyadic, generator=None)
gen = SMTLibGenerator(approximate_equivalence=False, logic="QF_NRA")
gate_set = ['H', 'X']
synthesizer = Synthesizer(gen=gen, gate_set=gate_set, solver=solver)
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[0] = Cyclotomic8Dyadic.one(gen)

# "mock" hadamard output -- check rescaling
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=1)
output_vec[0] = Cyclotomic8Dyadic.one(gen)
output_vec[0].a = 1
output_vec[1] = Cyclotomic8Dyadic.one(gen)
output_vec[1].a = -1

vectors = [(input_vec, output_vec)]

start_time = time.time()
try:
    synthesizer.synthesis(vectors, n, d1, "minimal.smt2")
    synthesizer.solve_and_extract_circuit("minimal.smt2", n, d1, "minimal.qasm", solver)

    end_time = time.time()

    print("sat")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

except Exception as e:
    print(f"Error: {e}")
    print("unsat")
