import numpy as np
import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import synthesis, solve_and_extract_circuit
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

# |00> -> 1/sqrt(2) * (|00> + |11>)
# |01> -> 1/sqrt(2) * (|01> + |10>)
# |10> -> 1/sqrt(2) * (|00> - |11>)
# |11> -> 1/sqrt(2) * (|01> - |10>)

vector_pairs = []
for q in range(2**n):
    # |a0 a1 ... an-1> ---> 1/sqrt(2) * (|0 a1 ... an-1> + (-1)^a0 |1 a1 ... an-1>)
    input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k = 0)
    for i in range(2**n):
        input_vec[i] = Cyclotomic8Dyadic.zero(gen)
    input_vec[q] = Cyclotomic8Dyadic.one(gen)
    
    output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k = 1)
    for i in range(2**n):
        output_vec[i] = Cyclotomic8Dyadic.zero(gen)


    # get the bits
    bits = [(q >> i) & 1 for i in reversed(range(n))]
    b0 = bits[0]
    rest = bits[1:]

    # |0 a1 ... an-1>
    idx1_bits = [0] + rest
    idx1 = int("".join(str(x) for x in idx1_bits), 2)

    idx2_bits = [1] + [(x ^ 1) for x in rest]
    idx2 = int("".join(str(x) for x in idx2_bits), 2)

    output_vec[idx1] = Cyclotomic8Dyadic.one(gen)
    if b0 == 0:
        output_vec[idx2] = Cyclotomic8Dyadic.one(gen)
    else:
        output_vec[idx2] = Cyclotomic8Dyadic.one(gen).multiply_by_minus_one(gen)
    
    
    
    vector_pairs.append((input_vec, output_vec))


gate_set = ['I', 'H', 'S', 'T', 'CX']

start_time = time.time()
try:
    synthesis(vector_pairs, n, d1, "ghzall.smt2", gen, gate_set)
    solve_and_extract_circuit("ghzall.smt2", n, d1, "ghzall.qasm", solver)
    end_time = time.time()
    print(f"sat")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")
except Exception:
    print(f"unsat")