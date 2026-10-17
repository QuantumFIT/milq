
import pytest

from complex.classic import Complex
from complex.fivetuple import FiveTuple
from complex.matrix import Matrix
from complex.vector import Vector
from gates import GateSet, self_adjoints
from generator import Generator
from sim import Simulator


def test_optimal_presets_keep_gate_arity():
    # set_cx_optimal used to re-register cx as a 1-qubit gate
    g = GateSet(['h', 'cx', 't', 'tdg'])
    g.set_cx_optimal()
    assert g.get_gates(2) == ['cx'] and g.gates['cx'] == 1
    g.set_t_optimal()
    assert g.gates['t'] == g.gates['tdg'] == 1 and g.gates['cx'] == 0
    assert g.qubits == {'h': 1, 'cx': 2, 't': 1, 'tdg': 1, 'id': 1}


def test_dcx_is_not_self_adjoint():
    # dcx has order 3
    assert 'dcx' not in self_adjoints


def test_symbolic_conjugate():
    # conjugate checked its argument instead of self.gen
    x = FiveTuple(name='x', generator=Generator(mode='smtlib'))
    assert x.conjugate().gen is x.gen


def test_expand_to_rejects_target_out_of_range():
    # target == qubits used to loop forever
    with pytest.raises(ValueError):
        Matrix.x(FiveTuple, q=2, qubits=2)


@pytest.mark.parametrize("body, gates", [
    ('qubit[2] q;\nh q[0]; x q[1];\n', [('h', [0]), ('x', [1])]),
    ('qubit[2] q; h q[0];\n', [('h', [0])]),
    ('qubit[1] q;\n/* comment\n h q[0]; */\nh q[0];\n', [('h', [0])]),
    ('qubit[2] q;\ncx\tq[0], q[1];\n', [('cx', [0, 1])]),
    ('qubit[2] q;\ncx q[0],\n   q[1];\n', [('cx', [0, 1])]),
    ('qubit[2] q;\nh q[0];\nbit c0 = measure q[1];\n', [('h', [0]), ('measure', [1])]),
    ('qubit[2] q;\nbit[2] bits;\nh q[0];\nbits[1] = measure q[1];\n', [('h', [0]), ('measure', [1])]),
    ('qubit[2] q;\nbit[2] c = "00";\nh q[0];\nc[1] = measure q[1];\n', [('h', [0]), ('measure', [1])]),
    ('qubit[2] q;\nbit[2] c;\nh q[0];\nc = measure q;\n', [('h', [0]), ('measure', [0]), ('measure', [1])]),
    ('qubit[2] q;\nh q[0];\nbit[2] c = measure q;\n', [('h', [0]), ('measure', [0]), ('measure', [1])]),
])
def test_qasm_statements(tmp_path, body, gates):
    # statements are ';'-separated, not one per line
    path = tmp_path / "c.qasm"
    path.write_text('OPENQASM 3.0;\ninclude "stdgates.inc";\n' + body)
    assert Simulator(str(path), complex_representation=Complex).parse_file()[0] == gates


def test_unknown_complex_representation(tmp_path):
    from synth import Synthesizer
    path = tmp_path / "c.qasm"
    path.write_text('OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[1] q;\nh q[0];\n')
    with pytest.raises(ValueError, match="complex_representation can be only FiveTuple or Classic"):
        Synthesizer().synthesis(qasm_file=str(path), vectors="all", solving="smt", solver="yices2",
                                mode="incremental", complex_representation="nTuple", output_qasm=str(tmp_path / "o.qasm"))


def test_vector_copy_keeps_name_bound_and_n():
    # #82, F61: copy dropped name and bound, so a dot product with the copy raised TypeError
    vector = Vector(q=2, name="V", generator=Generator(mode='smtlib'), element_representation=FiveTuple, k=0, n=1, bound=4, k_bound=4)
    copy = vector.copy()
    assert (copy.name, copy.bound, copy.n, copy.k) == ("V", 4, 1, vector.k)
    assert copy.vec is not vector.vec
    Vector.dot(copy, vector)


def test_division():
    # #82, F62: Complex / Complex returned None and FiveTuple / int raised
    quotient = Complex(1, 1) / Complex(1, 2)  # (1 + i)(1 - 2i) / 5
    assert (quotient.real, quotient.imag) == pytest.approx((0.6, -0.2))
    assert FiveTuple(2, 4, 0, -2) / 2 == FiveTuple(1, 2, 0, -1)


def test_vector_equality_is_value_equality():
    # #82, F63: the same state with k + 1 (numerators scaled by sqrt(2)) compared unequal
    plus = Vector(q=2, element_representation=FiveTuple, k=1)
    plus[0], plus[1] = FiveTuple.one(None), FiveTuple.one(None)
    scaled = Vector(q=2, element_representation=FiveTuple, k=2)
    scaled[0], scaled[1] = FiveTuple.one(None).increase_k(None), FiveTuple.one(None).increase_k(None)
    assert plus == scaled and scaled == plus
    scaled[1] = scaled[1].multiply_by_minus_one(None)
    assert not plus == scaled
