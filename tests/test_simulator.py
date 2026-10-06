"""Gate semantics of the simulator against Qiskit reference matrices."""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.circuit.library import SwapGate
from qiskit.quantum_info import Operator

from complex.classic import Complex
from complex.fivetuple import FiveTuple
from conftest import to_complex, unitary
from gates import supported_gates
from sim import Simulator

QUBITS = 3
# out-of-order arguments exercise qubit indexing
ARGUMENTS = {1: [(2,)], 2: [(2, 0), (0, 1)], 3: [(2, 0, 1)]}

# (gate, representation or None for all) -> tracking issue
KNOWN_BUGS = {
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


@pytest.mark.parametrize("targets, ancillas", [(1, 1), (2, 1), (1, 2), (3, 1)])
@pytest.mark.parametrize("representation", [FiveTuple, Complex], ids=lambda r: r.__name__)
def test_rus_input_states(tmp_path, targets, ancillas, representation):
    # every basis state and |+>^T on the targets (lowest qubits), ancillas in |0>
    qasm = tmp_path / "id.qasm"
    qasm.write_text(f"OPENQASM 2.0;\nqreg q[{targets + ancillas}];\nid q[0];\n")
    pairs = Simulator(str(qasm), complex_representation=representation).simulate_rus(targets, ancillas)
    ancilla_zero = np.eye(2**ancillas)[0]
    expected = [np.kron(ancilla_zero, np.eye(2**targets)[b]) for b in range(2**targets)]
    expected.append(np.kron(ancilla_zero, np.full(2**targets, 2 ** (-targets / 2))))
    states = [[to_complex(amplitude, state.k, representation) for amplitude in state] for state, _ in pairs]
    assert len(states) == len(expected)
    for state, reference in zip(states, expected):
        np.testing.assert_allclose(state, reference, atol=1e-9)


def test_fivetuple_mul_matches_complex():
    """Concrete FiveTuple product (a + b*w + c*w^2 + d*w^3) agrees with complex multiplication."""
    w = np.exp(1j * np.pi / 4)
    value = lambda t: t.a + t.b * w + t.c * w**2 + t.d * w**3
    basis = [FiveTuple(a=1), FiveTuple(b=1), FiveTuple(c=1), FiveTuple(d=1)]
    for x in basis:
        for y in basis:
            assert np.isclose(value(x * y), value(x) * value(y))
