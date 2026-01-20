from mqt.core import load
import numpy as np
from mqt.ddsim import CircuitSimulator

filename = "test.qasm"
qc = load(filename)
sim = CircuitSimulator(qc)

# run the simulation
result = sim.simulate(shots=1024)

# get the final DD
dd = sim.get_constructed_dd()
# transform the DD to a vector
vec = dd.get_vector()
# transform to a numpy array (without copying)
sv = np.array(vec, copy=False)
print(sv)