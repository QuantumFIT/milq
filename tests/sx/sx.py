import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import Synthesizer
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

n = 1 
d1 = 4
gen = SMTLibGenerator(dreal=True)
gate_set = ['I', 'SX']
synthesizer = Synthesizer(gen=gen, gate_set=gate_set, solver="dreal")


input_vec1 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec1[i] = Cyclotomic8Dyadic.zero(gen)
input_vec1[0] = Cyclotomic8Dyadic.one(gen)

output_vec1 = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=2)
for i in range(2**n):
    output_vec1[i] = Cyclotomic8Dyadic.zero(gen)
output_vec1[0] = (Complex.one(gen) * Complex.one_half(gen) + (Complex.one(gen) * Complex.i_phase(gen)) * Complex.one_half(gen));
output_vec1[1] = (Complex.one(gen) * Complex.one_half(gen) - (Complex.one(gen) * Complex.i_phase(gen)) * Complex.one_half(gen));

input_vec2 = Vector(q=2**n, generator=gen, element_representation=Complex)
for i in range(2**n):
    input_vec2[i] = Complex.zero(gen)
input_vec2[1] = Complex.one(gen)

output_vec2 = Vector(q=2**n, generator=gen, element_representation=Complex)
for i in range(2**n):
    output_vec2[i] = Complex.zero(gen)
output_vec2[0] = (Complex.one(gen) * Complex.one_half(gen) - (Complex.one(gen) * Complex.i_phase(gen)) * Complex.one_half(gen));
output_vec2[1] = (Complex.one(gen) * Complex.one_half(gen) + (Complex.one(gen) * Complex.i_phase(gen)) * Complex.one_half(gen));

vector_pairs = [
    (input_vec1, output_vec1),
    (input_vec2, output_vec2),
]
start_time = time.time()
synthesizer.synthesis(vector_pairs, n, d1, "sx.smt2")
synthesizer.solve_and_extract_circuit("sx.smt2", n, d1, "sx.qasm", "dreal")
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

