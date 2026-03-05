import numpy as np
import sys
import os
import time
import resource

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/'))
from synth import Synthesizer
from gates import GateSet

q = 2
if len(sys.argv) > 1:
    qasm_file = sys.argv[1]
    outf = sys.argv[2]

start_smt = time.time()
gate_set = GateSet(gate_set=['id', 'h', 't', 'tdg', 's', 'sdg', 'cx', 'cz', 'x'])
synthesizer = Synthesizer(gate_set=gate_set, solver="gurobi")
synthesizer.synthesis_rus(qasm_file, outf)
end_smt = time.time()
print(f"SMT time: {end_smt - start_smt} seconds")