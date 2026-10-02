"""Gate semantics of the simulator against Qiskit reference matrices."""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.circuit.library import SwapGate
from qiskit.quantum_info import Operator

from complex.classic import Complex
from complex.fivetuple import FiveTuple
from conftest import unitary
from gates import supported_gates

QUBITS = 3
# out-of-order arguments exercise qubit indexing
ARGUMENTS = {1: [(2,)], 2: [(2, 0), (0, 1)], 3: [(2, 0, 1)]}

# (gate, representation or None for all) -> tracking issue
KNOWN_BUGS = {
    ("ch", "FiveTuple"): "#1",
    ("dcx", None): "#2",
    **{(gate, None): "#18" for gate in ["swap", "iswap", "cy", "cs", "csdg", "csx", "sqrtswap", "cswap", "ccz"]},
}


def reference(gate, qubits):
    circuit = QuantumCircuit(QUBITS)
    if gate == "xcx":  # CX with control on |0>
        circuit.x(qubits[0])
        circuit.cx(*qubits)
        circuit.x(qubits[0])
    elif gate == "sqrtswap":
        circuit.append(SwapGate().power(0.5), qubits)
    else:
        getattr(circuit, gate)(*qubits)
    return Operator(circuit).data


def cases():
    for arity, gates in enumerate(supported_gates, start=1):
        for gate in gates:
            for qubits in ARGUMENTS[arity]:
                for representation in (FiveTuple, Complex):
                    issue = KNOWN_BUGS.get((gate, representation.__name__)) or KNOWN_BUGS.get((gate, None))
                    marks = [pytest.mark.xfail(reason=f"known bug {issue}")] if issue else []
                    yield pytest.param(gate, qubits, representation, marks=marks,
                                       id=f"{gate}{list(qubits)}-{representation.__name__}")


@pytest.mark.parametrize("gate, qubits, representation", list(cases()))
def test_gate_matches_qiskit(tmp_path, gate, qubits, representation):
    qasm = tmp_path / "gate.qasm"
    qasm.write_text(f"OPENQASM 2.0;\nqreg q[{QUBITS}];\n{gate} " + ", ".join(f"q[{q}]" for q in qubits) + ";\n")
    np.testing.assert_allclose(unitary(str(qasm), representation), reference(gate, qubits), atol=1e-9)
