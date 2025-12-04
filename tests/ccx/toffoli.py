import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

n = 3 
d1 = 4
gen = SMTLibGenerator()


vector_pairs = []

# Test all 8 states to verify Toffoli behavior
for state in range(2**n):
    input_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
    for i in range(2**n):
        input_vec[i] = Cyclotomic8Dyadic.zero(gen)
    input_vec[state] = Cyclotomic8Dyadic.one(gen)
    
    # Extract qubit values matching benchmark pattern:
    # a = qubit2 (bit 2, most significant), b = qubit1 (bit 1), c = qubit0 (bit 0, least significant)
    a = (state >> 2) & 1  # qubit 2
    b = (state >> 1) & 1  # qubit 1
    c = state & 1         # qubit 0
    
    # Toffoli: flip c (qubit0) if a=1 AND b=1
    c_out = c ^ (a & b)
    
    output_state = (a << 2) | (b << 1) | c_out
    
    output_vec = Vector(q=2**n, generator=gen, element_representation=Cyclotomic8Dyadic, k=0)
    for i in range(2**n):
        output_vec[i] = Cyclotomic8Dyadic.zero(gen)
    output_vec[output_state] = Cyclotomic8Dyadic.one(gen)
    
    print(input_vec)
    print(output_vec)
    vector_pairs.append((input_vec, output_vec))

gate_set = ['I', 'H', 'S', 'T', 'CX', 'X', 'Y', 'Z', 'CCX']

start_time = time.time()
synthesis(vector_pairs, n, d1, "ccx.smt2", gen, gate_set)
solve_and_extract_circuit("ccx.smt2", n, d1, "ccx.qasm", "z3")
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")

