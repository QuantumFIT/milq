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
