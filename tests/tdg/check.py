from mqt.core import load
import numpy as np
from mqt.ddsim import CircuitSimulator

filename = "tdg.qasm"

# Prepare input state: |11>
with open(filename, 'r') as f:
    original_qasm = f.read()

lines = original_qasm.split('\n')
qreg_line = next(line for line in lines if 'qreg' in line)
n_qubits = int(qreg_line.split('[')[1].split(']')[0])

# Create X gates to prepare |11> state
prep_gates = "\n".join([f"x q[{i}];" for i in range(n_qubits)])

creg_line_idx = next((i for i, line in enumerate(lines) if 'creg' in line), -1)
if creg_line_idx >= 0:
    new_qasm = '\n'.join(lines[:creg_line_idx+1]) + '\n' + prep_gates + '\n' + '\n'.join(lines[creg_line_idx+1:])
else:
    qreg_line_idx = next((i for i, line in enumerate(lines) if 'qreg' in line), -1)
    new_qasm = '\n'.join(lines[:qreg_line_idx+1]) + '\n' + prep_gates + '\n' + '\n'.join(lines[qreg_line_idx+1:])

import tempfile
import os
with tempfile.NamedTemporaryFile(mode='w', suffix='.qasm', delete=False) as tmp:
    tmp.write(new_qasm)
    tmp_filename = tmp.name

try:
    qc = load(tmp_filename)
    sim = CircuitSimulator(qc)
    
    # run the simulation
    result = sim.simulate(shots=1024)
    
    # get the final DD
    dd = sim.get_constructed_dd()
    # transform the DD to a vector
    vec = dd.get_vector()
    # transform to a numpy array (without copying)
    sv = np.array(vec, copy=False)
    print("Final state vector:")
    print(sv)
    print(f"\nInput state was |11> (index {2**n_qubits - 1})")
    print(f"Expected: Tdg applied to |11>")
finally:
    # Clean up temporary file
    os.unlink(tmp_filename)