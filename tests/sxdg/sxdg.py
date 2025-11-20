import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from z3_synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

n = 1 
d1 = 4
gen = SMTLibGenerator()


input_vec1 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec1[i] = Cyclotomic8Dyadic.zero(gen)
input_vec1[0] = Cyclotomic8Dyadic.one(gen)

output_vec1 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=2)

output_vec1[0] = (Cyclotomic8Dyadic.one(gen) - Cyclotomic8Dyadic.one(gen).multiply_by_i(gen));
output_vec1[1] = (Cyclotomic8Dyadic.one(gen) + Cyclotomic8Dyadic.one(gen).multiply_by_i(gen));

input_vec2 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec2[i] = Cyclotomic8Dyadic.zero(gen)
input_vec2[1] = Cyclotomic8Dyadic.one(gen)

output_vec2 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=2)
output_vec2[0] = (Cyclotomic8Dyadic.one(gen) + Cyclotomic8Dyadic.one(gen).multiply_by_i(gen));
output_vec2[1] = (Cyclotomic8Dyadic.one(gen) - Cyclotomic8Dyadic.one(gen).multiply_by_i(gen));

vector_pairs = [
    (input_vec1, output_vec1),
    (input_vec2, output_vec2),
]
gate_set = ['I', 'SXdg', 'H', 'S', 'T', 'CX', 'Tdg', 'Sdg', 'SX']

start_time = time.time()
synthesis(vector_pairs, n, d1, "sxdg.smt2", gen, gate_set)
solve_and_extract_circuit("sxdg.smt2", n, d1, "sxdg.qasm", "z3")
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

