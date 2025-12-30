import numpy as np
import sys
import os
import time
import resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import Synthesizer
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

if len(sys.argv) > 1:
    n = int(sys.argv[1])
    d1 = int(sys.argv[2])
    solver = sys.argv[3]
    k_glob = int(sys.argv[4])
    a = int(sys.argv[5])
else:
    n = 2 # length of the start e.g {c1 |i000> : |i|=2}
    d1 = 9
    solver = "cvc5"
    k_glob = 6
    a = 2**(n+1)
    
# n+1 hadamards at start + 1 z + n ccx's + n+1 hadamards at end
assert(d1 == (2*(n+1) + 1 + n  ))
assert(k_glob == 2*(n + 1))
assert(a == 2**(n+1))


gen = SMTLibGenerator()
gate_set = ['I', 'H', 'CX', 'Z', 'CCX']
synthesizer = Synthesizer(gen=gen, gate_set=gate_set, solver=solver)

# |000> -> |001>
# |100> -> |111>

# |00000> -> |00001>
# |01000> -> |01011>
# |10000> -> |10101>
# |11000> -> |11111>


vector_pairs = []

for q in range(2**n):
    # input (length n) tensor (n+1) zeros ...
    qubits = 2*n + 1
    input_vec = Vector(q=2**qubits, generator=gen,
                    element_representation=Cyclotomic8Dyadic, k=0)
    for i in range(2**qubits):
        input_vec[i] = Cyclotomic8Dyadic.zero(gen)
        
    updated_idx = q << (n+1)
    input_vec[updated_idx] = Cyclotomic8Dyadic.one(gen)


    # output 
    # |i i 1> where |i|=n

    output_vec = Vector(q=2**qubits, generator=gen,
                        element_representation=Cyclotomic8Dyadic, k=k_glob)
    for i in range(2**qubits):
        output_vec[i] = Cyclotomic8Dyadic.zero(gen)
        
    updated_out_idx = (q << (n+1)) | (q << 1) | 1
    output_vec[updated_out_idx] = Cyclotomic8Dyadic.one(gen)
    output_vec[updated_out_idx].a = a

    vector_pairs.append((input_vec, output_vec))

start_time = time.time()
try:
    synthesizer.synthesis(vector_pairs, 2*n+1, d1, "mobv.smt2")
    synthesizer.solve_and_extract_circuit("mobv.smt2", n, d1, "mobv.qasm", solver)

    end_time = time.time()

    print("sat")
    print(f"Time taken: {end_time - start_time} seconds")
    print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

except Exception as e:
    print(f"Error: {e}")
    print("unsat")
