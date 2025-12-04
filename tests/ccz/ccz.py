import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

n = 3 
d1 = 5
gen = SMTLibGenerator()


vector_pairs = []

# a
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[0] = Cyclotomic8Dyadic.one(gen)
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[0] = Cyclotomic8Dyadic.one(gen)
vector_pairs.append((input_vec, output_vec))

# b
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[1] = Cyclotomic8Dyadic.one(gen)
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[1] = Cyclotomic8Dyadic.one(gen)
vector_pairs.append((input_vec, output_vec))

# c
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[2] = Cyclotomic8Dyadic.one(gen)
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[2] = Cyclotomic8Dyadic.one(gen)
vector_pairs.append((input_vec, output_vec))

# d 
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[3] = Cyclotomic8Dyadic.one(gen)
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[3] = Cyclotomic8Dyadic.one(gen)
vector_pairs.append((input_vec, output_vec))

# e
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[4] = Cyclotomic8Dyadic.one(gen)
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[4] = Cyclotomic8Dyadic.one(gen)
vector_pairs.append((input_vec, output_vec))

# f
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[5] = Cyclotomic8Dyadic.one(gen)
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[5] = Cyclotomic8Dyadic.one(gen)
vector_pairs.append((input_vec, output_vec))

# g
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[6] = Cyclotomic8Dyadic.one(gen)
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[6] = Cyclotomic8Dyadic.one(gen)
vector_pairs.append((input_vec, output_vec))

# h -> -h
input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[7] = Cyclotomic8Dyadic.one(gen)
output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[7] = Cyclotomic8Dyadic.one(gen).multiply_by_minus_one(gen)
vector_pairs.append((input_vec, output_vec))



gate_set = ['I', 'H', 'S', 'T', 'CX', 'X', 'Y', 'Z', 'CCZ']

start_time = time.time()
synthesis(vector_pairs, n, d1, "ccz.smt2", gen, gate_set)
solve_and_extract_circuit("ccz.smt2", n, d1, "ccz.qasm", "z3")
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

