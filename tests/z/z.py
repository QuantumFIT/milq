import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import Synthesizer
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

n = 2
d1 = 1
gen = SMTLibGenerator()
gate_set = ['I', 'Z']
synthesizer = Synthesizer(gen=gen, gate_set=gate_set, solver="z3")


input_vec0 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec0[i] = Cyclotomic8Dyadic.zero(gen)
input_vec0[0] = Cyclotomic8Dyadic.one(gen)
output_vec0 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec0[i] = Cyclotomic8Dyadic.zero(gen)
output_vec0[0] = Cyclotomic8Dyadic.one(gen)

input_vec1 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec1[i] = Cyclotomic8Dyadic.zero(gen)
input_vec1[2] = Cyclotomic8Dyadic.one(gen)
output_vec1 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec1[i] = Cyclotomic8Dyadic.zero(gen)
output_vec1[2] = Cyclotomic8Dyadic.one(gen).multiply_by_minus_one(gen)



vector_pairs = [
    (input_vec0, output_vec0),
    (input_vec1, output_vec1),
]

start_time = time.time()
synthesizer.synthesis(vector_pairs, n, d1, "z.smt2")
synthesizer.solve_and_extract_circuit("z.smt2", n, d1, "z.qasm", "z3")
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

