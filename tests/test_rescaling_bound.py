"""FiveTuple equivalence when the k gap between the output and the target exceeds the input's max_k (#65)."""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

from complex.fivetuple import FiveTuple
from complex.vector import Vector
from gates import GateSet, max_k_increment
from synth import Synthesizer

SMT = dict(solving="smt", solver="yices2", complex_representation="FiveTuple")


def write_qasm(path, gates):
    with open(path, "w") as f:
        f.write('OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[1] q;\n')
        f.writelines(f"{gate} q[0];\n" for gate in gates)
    return str(path)


def operator(gates):
    # reference unitary computed by Qiskit, independently of MILQ's simulator
    qc = QuantumCircuit(1)
    for gate in gates:
        getattr(qc, gate)(0)
    return Operator(qc).data


def synthesized_gates(circuit):
    return [gate.name for gate in circuit.gates if gate is not None and gate.name != "id"]


def test_shorter_depth_bound_still_needs_an_exact_circuit(workdir):
    # t x t x = w*I; with d=1 the search goes past the input depth, where the old bound left the equivalence
    # unconstrained and h h h h (= I) was accepted
    qasm_file = write_qasm(workdir / "in.qasm", ["t", "x", "t", "x"])
    res, circuit, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="all", mode="incremental", d=1,
                                              output_qasm="out.qasm", **SMT)
    assert res
    np.testing.assert_allclose(operator(synthesized_gates(circuit)), operator(["t", "x", "t", "x"]), atol=1e-9)


def test_unreachable_target_is_not_synthesized(workdir):
    # X is not a product of H gates, at any depth
    qasm_file = write_qasm(workdir / "in.qasm", ["x"])
    res, circuit, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="all", mode="incremental",
                                              gate_set=GateSet(["h"]), max_depth=6, output_qasm="out.qasm", **SMT)
    assert (res, circuit) == (False, None)


def test_restricted_gate_set_gives_an_exact_circuit(workdir):
    # Z = h sx sx h; the old bound accepted sx sx (= X)
    qasm_file = write_qasm(workdir / "in.qasm", ["z"])
    res, circuit, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="all", mode="incremental",
                                              gate_set=GateSet(["h", "sx"]), output_qasm="out.qasm", **SMT)
    assert res
    gates = synthesized_gates(circuit)
    assert len(gates) == 4
    np.testing.assert_allclose(operator(gates), operator(["z"]), atol=1e-9)


def zero_to_one(k_target):
    # |0> -> |1>, with the target written as 4/sqrt(2)^k_target
    inp = Vector(q=2, element_representation=FiveTuple, k=0)
    out = Vector(q=2, element_representation=FiveTuple, k=k_target)
    inp[0] = FiveTuple(a=1, b=0, c=0, d=0)
    out[1] = FiveTuple(a=4, b=0, c=0, d=0)
    return [(inp, out)]


@pytest.mark.parametrize("k_target", [4, 4.0])
@pytest.mark.parametrize("mode", ["basic", "incremental"])
def test_custom_target_with_a_large_k(workdir, mode, k_target):
    # the old bound only covered the gap of the input depth, and the empty circuit was accepted
    res, circuit, _ = Synthesizer().synthesis(vectors="custom", vector_pairs=zero_to_one(k_target), q=1, d=1,
                                              gate_set=GateSet(["x", "h"]), mode=mode, output_qasm="out.qasm", **SMT)
    assert res
    assert synthesized_gates(circuit) == ["x"]


def test_float_k_reaches_pysmt_as_an_integer(workdir):
    # yices2 tolerates a k of 4.0 in the formula; pySMT crashed on it, so the vectors must carry the int
    res, circuit, _ = Synthesizer().synthesis(vectors="custom", vector_pairs=zero_to_one(4.0), q=1, d=1,
                                              gate_set=GateSet(["x", "h"]), mode="basic", output_qasm="out.qasm",
                                              solving="pysmt", solver="z3", complex_representation="FiveTuple")
    assert res
    assert synthesized_gates(circuit) == ["x"]


def test_custom_target_with_a_fractional_k(workdir):
    with pytest.raises(ValueError, match="k of a FiveTuple vector must be an integer, got 4.5"):
        Synthesizer().synthesis(vectors="custom", vector_pairs=zero_to_one(4.5), q=1, d=1, gate_set=GateSet(["x", "h"]),
                                mode="incremental", output_qasm="out.qasm", **SMT)


MILP = dict(solving="milp", solver="cbc", complex_representation="FiveTuple")


@pytest.mark.parametrize("target, gate_set, expected", [
    # past the input's max_k, the stale k bound and big-M made the correct circuit infeasible (#65 F15)
    (["x"], ["sx", "z"], ["sx", "sx"]),
    (["z"], ["h", "sx"], ["h", "sx", "sx", "h"]),
])
def test_milp_finds_circuits_past_the_input_depth(workdir, target, gate_set, expected):
    qasm_file = write_qasm(workdir / "in.qasm", target)
    res, circuit, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="all", mode="incremental",
                                              gate_set=GateSet(gate_set), max_depth=6, output_qasm="out.qasm", **MILP)
    assert res
    gates = synthesized_gates(circuit)
    assert len(gates) == len(expected)
    np.testing.assert_allclose(operator(gates), operator(target), atol=1e-9)


def test_milp_custom_target_with_a_large_k(workdir):
    res, circuit, _ = Synthesizer().synthesis(vectors="custom", vector_pairs=zero_to_one(4), q=1, d=1,
                                              gate_set=GateSet(["x", "h"]), mode="basic", output_qasm="out.qasm", **MILP)
    assert res
    assert synthesized_gates(circuit) == ["x"]


@pytest.mark.parametrize("mode", ["basic", "incremental"])
def test_milp_input_with_a_large_k(workdir, mode):
    # the intermediate states' k was capped at 2*(depth+1), below the input's own k of 6
    inp = Vector(q=2, element_representation=FiveTuple, k=6)
    out = Vector(q=2, element_representation=FiveTuple, k=6)
    inp[0] = FiveTuple(a=1, b=0, c=0, d=0)
    out[1] = FiveTuple(a=1, b=0, c=0, d=0)
    res, circuit, _ = Synthesizer().synthesis(vectors="custom", vector_pairs=[(inp, out)], q=1, d=1,
                                              gate_set=GateSet(["x", "h"]), mode=mode, output_qasm="out.qasm", **MILP)
    assert res
    assert synthesized_gates(circuit) == ["x"]


@pytest.mark.parametrize("gates, expected", [(["x", "z", "t"], 0), (["h", "t"], 1), (["h", "sx"], 2), (["cx", "csx"], 2)])
def test_k_increment_follows_the_gate_set(gates, expected):
    # the k bounds of the encoding come from this, a gate missing from k_increments would make them too small
    assert max_k_increment(GateSet(gates)) == expected
