import numpy as np
import sys
import os
import time
import resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from z3_synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

# TODO

if len(sys.argv) > 1:
    n = int(sys.argv[1])
    d1 = int(sys.argv[2])
    solver = sys.argv[3]
    k_glob = int(sys.argv[4])
    a = int(sys.argv[5])
else:
    n = 3
    d1 = 16
    solver = "cvc5"
    k_glob = 6
    a = 2**(n+1)


gen = SMTLibGenerator()
input_vec = Vector(q=2**n, generator=gen,
                element_representation=Cyclotomic8Dyadic, k=0)
for i in range(2**n):
    input_vec[i] = Cyclotomic8Dyadic.zero(gen)
input_vec[0] = Cyclotomic8Dyadic.one(gen)


output_vec = Vector(q=2**n, generator=gen,
                    element_representation=Cyclotomic8Dyadic, k=k_glob)
for i in range(2**n):
    output_vec[i] = Cyclotomic8Dyadic.zero(gen)
output_vec[3] = Cyclotomic8Dyadic.one(gen).multiply_by_minus_one(gen)

vector_pairs = [(input_vec, output_vec)]

gate_set = ['I', 'H', 'CX', 'Z', 'CCX', 'CZ', 'X']

start_time = time.time()
try:
    synthesis(vector_pairs, n, d1, "grover.smt2", gen, gate_set)
    solve_and_extract_circuit("grover.smt2", n, d1, "grover.qasm", solver)

    end_time = time.time()

    print("sat")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

except Exception as e:
    print(f"Error: {e}")
    print("unsat")
