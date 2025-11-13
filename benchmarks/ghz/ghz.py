import numpy as np
import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from z3_synth import synthesis, solve_and_extract_circuit
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator

n = 6
d1 = n
gen = SMTLibGenerator()

#REALS VERSION
# input |0^n>
#input_vector = [Complex.zero(gen) for _ in range(2**n)]
#input_vector[0] = Complex.one(gen)

# output |0^n> * 1/sqrt(2) + (|1> tensor |0^n-1>) * 1/sqrt(2)
#output_vector = [Complex.zero(gen) for _ in range(2**n)]
#output_vector[0] = Complex.inv_sqrt2(gen)
#output_vector[2**n - 1] = Complex.inv_sqrt2(gen)
#vector_pairs = [(input_vector, output_vector)]


# DYADIC VERSION
input_vector = [Cyclotomic8Dyadic.zero(gen) for _ in range(2**n)]
input_vector[0] = Cyclotomic8Dyadic.one(gen)

output_vector = [Cyclotomic8Dyadic.zero(gen) for _ in range(2**n)]
output_vector[0] = Cyclotomic8Dyadic.inv_sqrt2(gen)
output_vector[2**n - 1] = Cyclotomic8Dyadic.inv_sqrt2(gen)

vector_pairs = [(input_vector, output_vector)]

start_time = time.time()
synthesis(vector_pairs, n, d1, "ghz.smt2", gen)
solve_and_extract_circuit("ghz.smt2", n, d1, "ghz.qasm", "z3")
end_time = time.time()
print(f"Time taken: {end_time - start_time} seconds")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")