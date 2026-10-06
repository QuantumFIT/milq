"""Circuit helpers on circuits with empty and identity layers."""

import os

import pytest

from gates import Circuit, Gate
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
