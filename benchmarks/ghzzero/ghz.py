import numpy as np
import sys
import os
import time
import resource
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import Synthesizer


# optional sys arguments n, d1, solver
if len(sys.argv) > 1:
    n = int(sys.argv[1])
    d1 = int(sys.argv[2])
    solver = sys.argv[3]
else:
    n = 5
    d1 = n
    solver = "z3"
synthesizer = Synthesizer()

assert(n == d1)


start_time = time.time()
synthesizer.synthesis_zero("ghz.qasm")
end_time = time.time()
print(f"sat")
print(f"Time taken: {end_time - start_time} seconds")
print(f"Memory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss} KB")