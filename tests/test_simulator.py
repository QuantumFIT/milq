"""Gate semantics of the simulator against Qiskit reference matrices."""

import os
import subprocess
import sys

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.circuit.library import SwapGate
from qiskit.quantum_info import Operator

from complex.classic import Complex
from complex.fivetuple import FiveTuple
from complex.vector import Vector
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


def test_rus_from_matrix():
    # a target unitary instead of a circuit: qubits come from the matrix size, ancillas are added on top
    from complex.matrix import Matrix
    from sim import Simulator
    assert Matrix.cx(qubits=3).qubits == 3
    pairs = Simulator(matrix=Matrix.h(), complex_representation=Complex).simulate_rus(targets=1, ancillas=1)
    s = np.sqrt(1 / 2)
    expected = [[s, s, 0, 0], [s, -s, 0, 0], [1, 0, 0, 0]] # H|0>, H|1>, H|+>
    for (_, out), want in zip(pairs, expected):
        np.testing.assert_allclose([e.real + 1j * e.imag for e in out], want, atol=1e-9)


def fivetuple_value(t, k):
    w = np.exp(1j * np.pi / 4)
    return (t.a + t.b * w + t.c * w**2 + t.d * w**3) / np.sqrt(2) ** k


@pytest.mark.parametrize("k1, k2", [(0, 1), (0, 2), (1, 4), (3, 0)])
def test_vector_rescale_with_keeps_values(k1, k2):
    from complex.vector import Vector
    v1 = Vector(q=2, element_representation=FiveTuple, k=k1)
    v2 = Vector(q=2, element_representation=FiveTuple, k=k2)
    v1[0], v1[1] = FiveTuple(1, 2, 3, 4), FiveTuple(-1, 0, 2, -3)
    v2[0], v2[1] = FiveTuple(0, 1, -1, 2), FiveTuple(3, -2, 0, 1)
    r1, r2 = v1.rescale_with(v2)
    assert r1.k == r2.k == max(k1, k2)
    for before, after in [(v1, r1), (v2, r2)]:
        for i in range(2):
            assert np.isclose(fivetuple_value(after[i], after.k), fivetuple_value(before[i], before.k))



def test_vector_rescale_with_rejects_generator(tmp_path):
    from complex.vector import Vector
    from generator import Generator
    from logger import Logger
    gen = Generator(mode="smtlib", logger=Logger(verbosity=0, filename=str(tmp_path / "log")))
    v1 = Vector(q=1, generator=gen, element_representation=FiveTuple, k=9)
    v2 = Vector(q=1, element_representation=FiveTuple, k=10)
    with pytest.raises(NotImplementedError):
        v1.rescale_with(v2)
    with pytest.raises(NotImplementedError):
        v2.rescale_with(v1)

@pytest.mark.parametrize("name", [None, "v"])
@pytest.mark.parametrize("k, element, expected", [
    (1, (0, 3, 0, 1), (1, 2)),   # odd k: ((3-1)/sqrt2 + (3+1)/sqrt2 i) / sqrt2
    (2, (4, 0, -2, 0), (2, -1)),  # even k
])
def test_vector_to_real_with_generator(tmp_path, name, k, element, expected):
    from pysmt.shortcuts import Not, Solver
    from complex.vector import Vector
    from generator import Generator
    from logger import Logger
    gen = Generator(mode="pysmt", logic="QF_NRA", logger=Logger(verbosity=0, filename=str(tmp_path / "log")))
    gen.solver = Solver(name="z3")
    vec = Vector(q=1, name=name, generator=gen, element_representation=FiveTuple, k=k, k_bound=4)
    if name is None:
        vec[0] = FiveTuple(*element, generator=gen)
    else:
        # symbolic coefficients and k, pinned to the test values
        for attr, value in zip("abcd", element):
            gen.add_assertion(gen.Equals(getattr(vec[0], attr), gen.Int(value)))
        gen.add_assertion(gen.Equals(vec.k, gen.Int(k)))
    real = vec.to_real(max_k=4)[0]
    matches = gen.And(gen.Equals(real.real, gen.Real(expected[0])), gen.Equals(real.imag, gen.Real(expected[1])))
    assert gen.check_sat()
    gen.add_assertion(Not(matches))
    assert not gen.check_sat()


# simulator stats (#87, F65)

MEASURED = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\ncreg c[1];\nh q[0];\nmeasure q[0] -> c[0];\n'


@pytest.mark.parametrize("second", ["simulate_circuit", "simulate_zero", "simulate_custom"])
def test_repeated_simulations_do_not_accumulate_stats(tmp_path, second):
    qasm = tmp_path / "measured.qasm"
    qasm.write_text(MEASURED)
    simulator = Simulator(str(qasm), complex_representation=Complex)
    simulator.simulate_circuit()
    if second == "simulate_custom":
        simulator.simulate_custom([pair[0] for pair in simulator.simulate_zero()])
    else:
        getattr(simulator, second)()
    stats = simulator.circuit_stats()
    assert stats["d"] == 1
    assert stats["input_circuit"] == [("h", [0]), ("measure", [0])]
    assert stats["measured_qubits"] == [0]  # once, not once per input vector
    assert stats["measurements"] == [(0, "c[0]")]
    assert len(stats["classical_declarations"]) == 1


@pytest.mark.parametrize("measurements, expected", [
    ("measure q[1] -> c[1];\nmeasure q[0] -> c[0];\nmeasure q[1] -> c[1];\n", [1, 0]),
    ("measure q -> c;\n", [0, 1]),
])
def test_measured_qubits_are_unique_in_order(tmp_path, measurements, expected):
    qasm = tmp_path / "measured.qasm"
    qasm.write_text(f'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\ncreg c[2];\nh q[0];\n{measurements}')
    simulator = Simulator(str(qasm), complex_representation=Complex)
    simulator.simulate_circuit()
    assert simulator.circuit_stats()["measured_qubits"] == expected


def test_no_measurement_measures_no_qubit(tmp_path):
    qasm = tmp_path / "measured.qasm"
    qasm.write_text(MEASURED)
    simulator = Simulator(str(qasm), complex_representation=Complex, no_measurement=True)
    simulator.simulate_circuit()
    assert simulator.circuit_stats()["measured_qubits"] == []


# simulate_matrix (#84, F30): every gate the vector simulator knows

def matrix_values(matrix, representation):
    return np.array([[to_complex(e, matrix.k, representation) for e in row] for row in matrix.matrix])


@pytest.mark.parametrize("gate, qubits, representation", list(cases()))
def test_simulate_matrix_matches_qiskit(tmp_path, gate, qubits, representation):
    qasm = tmp_path / "gate.qasm"
    qasm.write_text(f"OPENQASM 2.0;\nqreg q[{QUBITS}];\n{gate} " + ", ".join(f"q[{q}]" for q in qubits) + ";\n")
    matrix = Simulator(str(qasm), complex_representation=representation).simulate_matrix()
    np.testing.assert_allclose(matrix_values(matrix, representation), reference(gate, qubits), atol=1e-9)


def test_simulate_matrix_rejects_measurements(tmp_path):
    qasm = tmp_path / "measured.qasm"
    qasm.write_text("OPENQASM 2.0;\nqreg q[1];\ncreg c[1];\nh q[0];\nmeasure q[0] -> c[0];\n")
    with pytest.raises(ValueError, match="no unitary matrix"):
        Simulator(str(qasm), complex_representation=Complex).simulate_matrix()
    matrix = Simulator(str(qasm), complex_representation=Complex, no_measurement=True).simulate_matrix()
    np.testing.assert_allclose(matrix_values(matrix, Complex), np.array([[1, 1], [1, -1]]) / np.sqrt(2), atol=1e-9)


# cli/simulator.py (#84, F30, F71, F77)

CLI = os.path.join(os.path.dirname(__file__), "..", "cli", "simulator.py")


def run_cli(qasm, *args):
    return subprocess.run([sys.executable, CLI, str(qasm), *args], capture_output=True, text=True, timeout=60)


def test_cli_matrix_prints_k(tmp_path):
    qasm = tmp_path / "ht.qasm"
    qasm.write_text("OPENQASM 2.0;\nqreg q[1];\nh q[0];\nt q[0];\nsx q[0];\n")
    run = run_cli(qasm, "-v", "matrix", "-c", "FiveTuple")
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip().endswith("k=3")  # h adds 1, sx 2


@pytest.mark.parametrize("outcome", ["2", "-1"])
def test_cli_rejects_other_measurement_outcomes(tmp_path, outcome):
    qasm = tmp_path / "m.qasm"
    qasm.write_text("OPENQASM 2.0;\nqreg q[2];\ncreg c[1];\nh q[0];\ncx q[0], q[1];\nmeasure q[1] -> c[0];\n")
    run = run_cli(qasm, "-v", "zero", "-c", "Classic", "-m", outcome)
    assert run.returncode == 2 and "invalid choice" in run.stderr


def test_measurement_outcome_is_0_or_1():
    vector = Vector(q=2, element_representation=Complex, k=0)
    with pytest.raises(ValueError, match="only 0 or 1, not 2"):
        vector.measure([0], 2)
    with pytest.raises(ValueError, match="only 0 or 1"):
        Simulator(matrix=None, qasm_file="unused.qasm", meas=2)


def test_matrix_repr_shows_k():
    from complex.matrix import Matrix
    assert repr(Matrix.h(FiveTuple)).endswith("k=1")


# simulate_jamiolkowski (#80, F22)

def test_jamiolkowski_keeps_the_input_gate_set(tmp_path):
    qasm = tmp_path / "t.qasm"
    qasm.write_text("OPENQASM 2.0;\nqreg q[1];\nt q[0];\n")
    simulator = Simulator(str(qasm), complex_representation=FiveTuple)
    simulator.simulate_jamiolkowski()
    stats = simulator.circuit_stats()
    assert list(stats["gate_set"]) == ["t"] and stats["q"] == 2
