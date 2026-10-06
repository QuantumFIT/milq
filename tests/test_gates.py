"""Circuit helpers on circuits with empty and identity layers."""

from gates import Circuit, Gate


def circuit_with_empty_layers():
    # as produced by the model parser: one slot per layer, unused layers stay None
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
