"""Circuit helpers on circuits with empty and identity layers."""

import os

import pytest

from gates import Circuit, Gate, GateSet, supported_gates
from synth import Synthesizer


def circuit_with_empty_layers():
    # one slot per layer; a slot never filled stays None (e.g. a placeholder circuit)
    circuit = Circuit(gates=[], q=2, d=5)
    circuit[0] = Gate("h", [0])
    circuit[1] = Gate("id", [1])
    circuit[2] = Gate("t", [1])
    circuit[3] = Gate("tdg", [0])
    return circuit


def test_gate_count_skips_empty_and_identity_layers():
    assert circuit_with_empty_layers().gate_count() == 3


def test_t_count_skips_empty_layers():
    assert circuit_with_empty_layers().t_count() == 2


def test_operations():
    assert [str(gate) for gate in circuit_with_empty_layers().operations()] == ["h q[0];", "t q[1];", "tdg q[0];"]


def test_draw_skips_empty_and_identity_layers(tmp_path):
    output = tmp_path / "circuit.png"
    circuit_with_empty_layers().draw(str(output))
    assert output.stat().st_size > 0


def test_model_without_a_gate_in_a_layer_is_rejected(workdir, monkeypatch):
    # every layer selects exactly one gate (possibly id), so an unfilled layer means a broken model
    synthesizer = Synthesizer()
    synthesizer.q, synthesizer.curr_depth = 1, 2
    circuit = Circuit(gates=[], q=1, d=2)
    circuit[0] = Gate("h", [0])
    monkeypatch.setattr(synthesizer.gen, "check_sat", lambda formula_file: True)
    monkeypatch.setattr(synthesizer.gen, "get_model", lambda: None)
    monkeypatch.setattr(synthesizer.parser, "parse", lambda *args, **kwargs: (True, circuit, []))
    with pytest.raises(RuntimeError, match=r"layer\(s\) \[1\]"):
        synthesizer.solve_and_extract_circuit(output_qasm="out.qasm")
    assert not os.path.exists("out.qasm")


def test_draw_every_supported_gate(tmp_path):
    # qiskit has no circuit method for some gates (xcx, sqrtswap)
    circuit = Circuit(gates=[], q=3, d=0)
    for qubits, names in enumerate(supported_gates, start=1):
        for name in names:
            circuit.append(Gate(name, list(range(qubits))))
    circuit.d = len(circuit.gates)
    output = tmp_path / "circuit.png"
    circuit.draw(str(output))
    assert output.stat().st_size > 0


# GateSet, Gate and Circuit API traps (#83)


def test_synthesis_leaves_the_callers_gate_set_alone(workdir):
    # F50: id used to be added to the caller's gate set on every layer
    with open("x.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[1];\nx q[0];\n")
    gate_set = GateSet()
    gate_set.add_gate("x", weight=1, qubits=1)
    res, circuit, _ = Synthesizer().synthesis(qasm_file="x.qasm", vectors="all", solving="smt", solver="yices2",
                                              gate_set=gate_set)
    assert res and [str(gate) for gate in circuit.operations()] == ["x q[0];"]
    assert gate_set.gates == {"x": 1} and gate_set.qubits == {"x": 1}


def test_circuit_append_extends_the_circuit():
    # F68: gates[:d] is the circuit, so an appended gate used to be invisible
    circuit = Circuit(gates=[], q=1, d=0)
    circuit.append(Gate("h", [0]))
    circuit.append(Gate("t", [0]))
    assert circuit.d == 2 and circuit.gate_count() == 2
    assert "h q[0];\nt q[0];" in str(circuit)
    assert circuit.bool_variables == ["L0_h_q0", "L1_t_q0"]


def test_gate_compares_with_anything_and_is_hashable():
    assert Gate("h", [0]) != None and Gate("h", [0]) != "h q[0];"
    assert Gate("cx", [0, 1]) == Gate("cx", [0, 1]) != Gate("cx", [1, 0])
    assert len({Gate("h", [0]), Gate("h", [0]), Gate("h", [1])}) == 2


def test_gate_set_with_both_gates_and_a_preset_is_rejected():
    with pytest.raises(ValueError, match="either gate_set or preset"):
        GateSet(["h"], preset="Clifford+T")


def test_union_keeps_the_subclass():
    class Weighted(GateSet):
        pass
    assert type(Weighted.union(GateSet(["h"]), GateSet(["t"]))) is Weighted
