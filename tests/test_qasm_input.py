"""Input circuits MILQ cannot read raise QasmParseError, a ValueError naming the statement (#71, F67)."""

import pytest
from qiskit import QuantumCircuit, qasm2, qasm3

from complex.classic import Complex
from sim import QasmParseError, Simulator

HEADER = 'OPENQASM 3.0;\ninclude "stdgates.inc";\n'


def parse(tmp_path, text):
    path = tmp_path / "in.qasm"
    path.write_text(text)
    return Simulator(str(path), complex_representation=Complex).parse_file()[0]


@pytest.mark.parametrize("text, message", [
    ("qubit[2] q;\nh q[0];\nreset q[0];\n", "`reset q\\[0\\]`: the statement is not supported"),
    ("qubit[1] q;\ngate foo a { h a;\n", "`gate foo a { h a`: the gate definition is not closed"),
    # F11: operands are checked against the gate's arity and the register
    ("qubit[2] q;\nsx q[0], q[1];\n", "sx acts on 1 qubit\\(s\\), not 2"),
    ("qubit[2] q;\ncx q[0];\n", "cx acts on 2 qubit\\(s\\), not 1"),
    ("qubit[2] q;\ncx q[0], q[0];\n", "a qubit is used twice"),
    ("qubit[1] q;\nt q[3];\n", "the register q has qubits 0 to 0"),
    ("qubit[2] q;\nh q[-1];\n", "the register q has qubits 0 to 1"),
    # F12: a gate after a measurement of its qubit
    ("qubit[1] q;\nbit[1] c;\nh q[0];\nc[0] = measure q[0];\nh q[0];\n", "only end-of-circuit measurements are supported"),
    # F27: a second register, and a register whose name ends with the declared one's
    ("qubit[2] q;\nqubit[1] anc;\ncx q[0], anc[0];\n", "`qubit\\[1\\] anc`: only one quantum register is supported"),
    ("qubit[1] q;\nh qq[0];\n", "the operand `qq\\[0\\]` is not a qubit of the register q"),
    # F28: a whole-register operand of a multi-qubit gate
    ("qubit[2] q;\ncx q[0], q;\n", "only a single-qubit gate can apply to the whole register"),
    # F66: a used user-defined gate, a native gate redefined
    ("gate foo a { h a; }\nqubit[1] q;\nfoo q[0];\n", "`foo q\\[0\\]`: the statement is not supported"),
    ("gate cs a, b { cx a, b; }\nqubit[2] q;\ncs q[0], q[1];\n", "a definition of the native gate cs must be milq's own"),
    # a phase that is not a multiple of pi/4, and a helper gate whose body uses its parameter
    ("gate cs a, b { p(pi/3) a; cx a, b; }\nqubit[2] q;\ncs q[0], q[1];\n", "a definition of the native gate cs must be milq's own"),
    ("gate cu1x(l) a, b { u1(l/2) a; cx a, b; u1(-l/2) b; cx a, b; u1(l/2) b; }\n"
     "gate csx a, b { h b; cu1x(pi/2) a, b; h b; }\nqubit[2] q;\ncsx q[0], q[1];\n", "a definition of the native gate csx must be milq's own"),
])
def test_parse_errors_name_the_statement(tmp_path, text, message):
    path = tmp_path / "in.qasm"
    path.write_text(HEADER + text)
    with pytest.raises(QasmParseError, match=message) as raised:
        Simulator(str(path), complex_representation=Complex).parse_file()
    assert isinstance(raised.value, ValueError) and str(path) in str(raised.value)


@pytest.mark.parametrize("text, gates", [
    # F28: barriers are skipped, a single-qubit gate on the register applies to each qubit
    ("qubit[2] q;\nh q;\nbarrier q;\nbarrier q[0], q[1];\nx q[1];\n", [('h', [0]), ('h', [1]), ('x', [1])]),
    # F64: classical registers named like the measure keyword
    ("bit[1] measured;\nqubit[1] q;\nh q[0];\nmeasured[0] = measure q[0];\n", [('h', [0]), ('measure', [0])]),
    ("qubit[1] q;\nbit[1] measurements;\nh q[0];\n", [('h', [0])]),
    # F12: a gate on another qubit after a measurement commutes with it
    ("qubit[2] q;\nmeasure q[0];\nh q[1];\n", [('measure', [0]), ('h', [1])]),
    # F66: an unused user-defined gate is dropped, milq's own definitions of native gates are accepted
    ("gate foo a { h a; }\ngate csx a, b { ctrl @ sx a, b; }\nqubit[2] q;\ncsx q[0], q[1];\n", [('csx', [0, 1])]),
    # Qiskit 1.x defines cs and csdg with phase gates, and csx with a helper gate for the angle it uses
    ("gate cs q0,q1 { p(pi/4) q0; cx q0,q1; p(-pi/4) q1; cx q0,q1; p(pi/4) q1; }\n"
     "gate csdg q0,q1 { p(-pi/4) q0; cx q0,q1; p(pi/4) q1; cx q0,q1; p(-pi/4) q1; }\n"
     "qubit[2] q;\ncs q[0], q[1];\ncsdg q[1], q[0];\n", [('cs', [0, 1]), ('csdg', [1, 0])]),
    ("gate cu1_1(_gate_p_0) _gate_q_0, _gate_q_1 {\n  u1(pi/4) _gate_q_0;\n  cx _gate_q_0, _gate_q_1;\n"
     "  u1(-pi/4) _gate_q_1;\n  cx _gate_q_0, _gate_q_1;\n  u1(pi/4) _gate_q_1;\n}\n"
     "gate csx _gate_q_0, _gate_q_1 {\n  h _gate_q_1;\n  cu1_1(pi/2) _gate_q_0, _gate_q_1;\n  h _gate_q_1;\n}\n"
     "qubit[2] q;\ncsx q[0], q[1];\n", [('csx', [0, 1])]),
])
def test_accepted_inputs(tmp_path, text, gates):
    assert parse(tmp_path, HEADER + text) == gates


@pytest.mark.parametrize("dumps", [qasm2.dumps, qasm3.dumps])
def test_qiskit_export_is_read(tmp_path, dumps):
    # F28, F66: measure_all() writes a barrier, Qiskit defines sxdg, dcx, iswap, cs, csdg, csx and ccz in its own way
    circuit = QuantumCircuit(3)
    circuit.sxdg(0)
    circuit.dcx(0, 1)
    circuit.iswap(0, 1)
    circuit.cs(0, 1)
    circuit.csdg(1, 2)
    circuit.csx(0, 2)
    circuit.ccz(0, 1, 2)
    circuit.measure_all()
    assert parse(tmp_path, dumps(circuit)) == [
        ('sxdg', [0]), ('dcx', [0, 1]), ('iswap', [0, 1]), ('cs', [0, 1]), ('csdg', [1, 2]), ('csx', [0, 2]),
        ('ccz', [0, 1, 2]), ('measure', [0]), ('measure', [1]), ('measure', [2])]
