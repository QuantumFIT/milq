
import pytest

from complex.classic import Complex
from complex.fivetuple import FiveTuple
from complex.matrix import Matrix
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


def test_ntuple_is_not_implemented(tmp_path):
    # nTuple is dead code until it is rewritten
    from synth import Synthesizer
    path = tmp_path / "c.qasm"
    path.write_text('OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[1] q;\nh q[0];\n')
    with pytest.raises(NotImplementedError):
        Synthesizer().synthesis(qasm_file=str(path), vectors="all", solving="smt", solver="z3",
                                mode="incremental", complex_representation="nTuple", output_qasm=str(tmp_path / "o.qasm"))
