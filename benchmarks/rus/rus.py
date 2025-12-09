import numpy as np
import sys
import os
import time
import resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import synthesis, solve_and_extract_circuit
from sim import simulate_circuit, simulate_rus
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

q = 2
if len(sys.argv) > 1:
    qasm_file = sys.argv[1]
    d = int(sys.argv[2])
    solver = sys.argv[3]
else:
    qasm_file = '6/spec.qasm'
    d = 20
    solver = "opensmt"

# first simulate to get the vectors
generator = SMTLibGenerator()
gate_set = ['I', 'H', 'T', 'Tdg', 'CZ']
start_smt = time.time()
vectors = simulate_rus(qasm_file, generator=generator)
#for vec_pair in vectors:
#    print("Input vec:")
#    for i in range(len(vec_pair[0].vec)):
#        print(vec_pair[0].vec[i].to_real(vec_pair[0].k))
#    print("Output vec:")
#    for i in range(len(vec_pair[1].vec)):\
#        print(vec_pair[1].vec[i].to_real(vec_pair[1].k))
#    print("--------------------------------")


try:
    synthesis(vectors, q, d, "smt.smt2", generator, gate_set)
    solve_and_extract_circuit("smt.smt2", q, d, "smt.qasm", solver)
    end_smt = time.time()
    print(f"SMT time: {end_smt - start_smt} seconds")
except Exception as e:
    print(f"Error: {e}")
    print("unsat")