import numpy as np
import sys
import os
import time
import resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import Synthesizer
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic, nTuple
from smtlib_generator import SMTLibGenerator

if len(sys.argv) > 1:
    n = int(sys.argv[1])
    d1 = int(sys.argv[2])
    solver = sys.argv[3]
    s = sys.argv[4]
    k_glob = int(sys.argv[5])
    a = int(sys.argv[6])
else:
    n = 3
    d1 = 8
    solver = "cvc5"
    s = "101"
    k_glob = 6
    a = 2**n
assert(2*n == k_glob)
assert(d1 == (2*n + 1 + (n // 2)))
assert(len(s) == n)
assert(a == 2**n)


gen = SMTLibGenerator()
synthesizer = Synthesizer(gen=gen, gate_set=['H'], solver=solver)


input_vec = Vector(q=2**n, generator=gen,
                   element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[0] = Cyclotomic8Dyadic.one(gen)


k_glob = 0

output_vec = Vector(q=2**n, generator=gen,
                    element_representation=Cyclotomic8Dyadic, k=k_glob)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
    
output_vec[0] = Cyclotomic8Dyadic.one(gen)

#s_index = int(s, 2)
#output_vec[s_index] = Cyclotomic8Dyadic.one(gen)
#output_vec[s_index].a = a

#vector_pairs = [(input_vec, output_vec)]


gate_set = ['I', 'H', 'CX', 'Z']

start_time = time.time()
try:
    synthesizer.synthesis_gate_optimal(vector_pairs, n, d1)

    end_time = time.time()

    print("sat")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

except Exception as e:
    print(f"Error: {e}")
    print("unsat")
