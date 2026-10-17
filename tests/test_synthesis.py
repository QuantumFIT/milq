"""End-to-end synthesis with the bundled SMT solvers and (size-limited) Gurobi."""

import os

import numpy as np
import pytest

from conftest import BENCHMARKS, unitary
from synth import Synthesizer
from gates import GateSet
from sim import Simulator

GHZ = [("ghz/2.qasm", 2), ("ghz/3.qasm", 3)]


def gate_count(circuit):
    return len([gate for gate in circuit.gates if gate is not None and gate.name != "id"])


@pytest.mark.parametrize("solver", ["yices2", "cvc5"])
@pytest.mark.parametrize("benchmark, optimal_gates", GHZ, ids=[b for b, _ in GHZ])
def test_smt_incremental_is_optimal_and_equivalent(workdir, solver, benchmark, optimal_gates):
    qasm_file = os.path.join(BENCHMARKS, benchmark)
    res, circuit, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="all", solving="smt", solver=solver,
                                              mode="incremental", complex_representation="FiveTuple",
                                              output_qasm="out.qasm")
    assert res
    assert gate_count(circuit) == optimal_gates
    np.testing.assert_allclose(unitary("out.qasm"), unitary(qasm_file), atol=1e-9)


def test_gurobi_incremental_zero_state(workdir):
    # small enough for the size-limited license shipped with gurobipy
    qasm_file = os.path.join(BENCHMARKS, "ghz/2.qasm")
    res, circuit, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="zero", solving="gurobi", solver="gurobi",
                                              mode="incremental", complex_representation="Classic",
                                              output_qasm="out.qasm")
    assert res
    assert gate_count(circuit) == 2
    # only |0>^n is specified, so compare the first column
    np.testing.assert_allclose(unitary("out.qasm")[:, 0], unitary(qasm_file)[:, 0], atol=1e-9)


@pytest.mark.parametrize("solving, solver, representation", [("smt", "yices2", "FiveTuple"), ("gurobi", "gurobi", "Classic")])
def test_pareto_incremental_enumerates_front(workdir, solving, solver, representation):
    qasm_file = os.path.join(BENCHMARKS, "ghz/2.qasm")
    res, circuit, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="zero", solving=solving, solver=solver,
                                              mode="pareto-incremental", complex_representation=representation,
                                              output_qasm="out.qasm", pareto_timeout=60, max_depth=2)
    assert res
    assert gate_count(circuit) == 2
    # both Bell-state preparations, h + cx in either orientation, are optimal points
    points = sorted(os.listdir("pareto_front"))
    assert len(points) == 2
    assert os.path.exists("pareto_front.pdf")
    for point in points:
        np.testing.assert_allclose(unitary(os.path.join("pareto_front", point))[:, 0], unitary(qasm_file)[:, 0], atol=1e-9)


def test_jamiolkowski_basic_mode(workdir):
    # only the first half of the 2*q qubits has selection variables; add_constraints asked for all of them (KeyError)
    with open("ht.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[1];\nh q[0];\nt q[0];\n")
    res, circuit, _ = Synthesizer().synthesis(qasm_file="ht.qasm", vectors="jamiolkowski", solving="smt", solver="yices2",
                                              mode="basic", complex_representation="FiveTuple", gate_set=GateSet(["h", "t"]))
    assert res
    assert [str(gate) for gate in circuit.gates] == ["h q[0];", "t q[0];"]
    # #80, F22: the circuit acts on the input's qubit, not on the 2 qubits of the Choi state
    assert circuit.q == 1 and "qubit[1] q;\nbit[1] c;" in str(circuit)


@pytest.mark.parametrize("solving, solver", [("smt", "yices2"), ("milp", "cbc")])
def test_identity_without_id_gate_is_unsat(workdir, monkeypatch, solving, solver):
    # without id, the depth-2 circuits over t, tdg are t;tdg and tdg;t (forbidden) and t;t, tdg;tdg (not identity)
    add_gate = GateSet.add_gate
    monkeypatch.setattr(GateSet, "add_gate", lambda self, gate, *args, **kwargs:
                        None if gate == "id" else add_gate(self, gate, *args, **kwargs))
    with open("identity.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[1];\nt q[0];\ntdg q[0];\n")
    gate_set = GateSet(["t", "tdg"])
    res, _, _ = Synthesizer().synthesis(qasm_file="identity.qasm", vectors="all", solving=solving, solver=solver,
                                        mode="basic", complex_representation="FiveTuple", gate_set=gate_set)
    # assert identity is not actually in the gate-set and returns unsat
    assert "id" not in gate_set.gates
    assert not res


@pytest.mark.parametrize("solving, solver", [("smt", "yices2"), ("milp", "cbc")])
@pytest.mark.parametrize("body, gates, expected", [
    ("", ["h"], ["id q[0];"]),                # d = 0: the empty circuit
    ("s q[0];\n", ["t"], ["t q[0];"] * 2),    # d = 1, needs depth 2
    ("z q[0];\n", ["t"], ["t q[0];"] * 4),    # d = 1, needs depth 4
])
def test_incremental_past_input_depth(workdir, solving, solver, body, gates, expected):
    # past d, the weight of each new layer was declared once per vector pair: smtlib solvers rejected the
    # redeclaration, and in milp the extra entries shifted the weights so that some layers could only hold id
    with open("in.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[1];\n" + body)
    res, circuit, _ = Synthesizer().synthesis(qasm_file="in.qasm", vectors="all", solving=solving, solver=solver,
                                              mode="incremental", complex_representation="FiveTuple", gate_set=GateSet(gates))
    assert res
    assert [str(gate) for gate in circuit.gates] == expected


@pytest.mark.parametrize("mode", ["incremental", "basic", "binary", "pareto-incremental"])
def test_output_file_keeps_end_of_circuit_measurements(workdir, mode):
    # #57: the measurements were added to the returned circuit only after the file was written
    with open("in.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[2];\ncreg c[2];\nh q[0];\ncx q[0], q[1];\nmeasure q[0] -> c[0];\n")
    res, circuit, _ = Synthesizer().synthesis(qasm_file="in.qasm", vectors="zero", solving="smt", solver="yices2", mode=mode,
                                              complex_representation="Classic", output_qasm="out.qasm",
                                              pareto_timeout=60, max_depth=2)
    assert res
    with open("out.qasm") as f:
        written = f.read()
    assert "c[0] = measure q[0];" in written
    assert written == str(circuit)


BELL_2 = "OPENQASM 2.0;\nqreg q[2];\n{}h q[0];\ncx q[0], q[1];\n{}"
BELL_3 = "OPENQASM 3.0;\ninclude \"stdgates.inc\";\nqubit[2] q;\n{}h q[0];\ncx q[0], q[1];\n{}"
# (input, classical declarations, measurements as (qubit, classical bit)) of the input and the output
MEASUREMENTS = [
    (BELL_2.format("creg c[2];\n", "measure q[0] -> c[1];\n"), ["bit[2] c"], [(0, "c[1]")]),
    (BELL_2.format("creg a[1];\ncreg b[1];\n", "measure q[0] -> b[0];\nmeasure q[1] -> a[0];\n"),
     ["bit[1] a", "bit[1] b"], [(0, "b[0]"), (1, "a[0]")]),
    (BELL_2.format("creg c[2];\n", "measure q -> c;\n"), ["bit[2] c"], [(0, "c[0]"), (1, "c[1]")]),
    (BELL_3.format("bit[2] bits;\n", "bits[1] = measure q[0];\n"), ["bit[2] bits"], [(0, "bits[1]")]),
    (BELL_3.format("", "bit m = measure q[1];\n"), ["bit m"], [(1, "m")]),
    (BELL_3.format("", "bit[2] c = measure q;\n"), ["bit[2] c"], [(0, "c[0]"), (1, "c[1]")]),
    (BELL_3.format('bit[2] c = "00";\n', "c[1] = measure q[1];\n"), ['bit[2] c = "00"'], [(1, "c[1]")]),
    (BELL_3.format("", "measure q[1];\n"), [], [(1, None)]),
]


def parsed_measurements(path):
    simulator = Simulator(path)
    simulator.parse_file()
    stats = simulator.circuit_stats()
    return stats["classical_declarations"], stats["measurements"]


@pytest.mark.parametrize("qasm, declarations, measurements", MEASUREMENTS)
def test_input_measurements_are_parsed_with_their_classical_bits(workdir, qasm, declarations, measurements):
    with open("in.qasm", "w") as f:
        f.write(qasm)
    assert parsed_measurements("in.qasm") == (declarations, measurements)


@pytest.mark.parametrize("qasm, declarations, measurements", MEASUREMENTS)
def test_output_measures_into_the_input_classical_bits(workdir, qasm, declarations, measurements):
    # #57: measure q[0] -> c[1] was written as c[0] = measure q[0]
    with open("in.qasm", "w") as f:
        f.write(qasm)
    res, circuit, _ = Synthesizer().synthesis(qasm_file="in.qasm", vectors="zero", solving="smt", solver="yices2",
                                              mode="incremental", complex_representation="Classic", output_qasm="out.qasm")
    assert res
    # read back by MILQ's parser, the output declares and measures the same classical bits (bit[2] c if none)
    assert parsed_measurements("out.qasm") == (declarations or ["bit[2] c"], measurements)


def test_no_measurement_writes_no_measurements(workdir):
    with open("in.qasm", "w") as f:
        f.write(BELL_2.format("creg out[2];\n", "measure q[0] -> out[1];\n"))
    res, circuit, _ = Synthesizer().synthesis(qasm_file="in.qasm", vectors="zero", solving="smt", solver="yices2",
                                              mode="incremental", complex_representation="Classic", output_qasm="out.qasm",
                                              no_measurement=True)
    assert res
    assert parsed_measurements("out.qasm") == (["bit[2] c"], [])


@pytest.mark.parametrize("given, gates, weights", [
    # #79, F23: a given gate set is used as it is, also in RUS mode
    (["h", "t", "tdg", "cx"], {"h", "t", "tdg", "cx", "id"}, {"h": 1, "t": 1, "tdg": 1, "cx": 1, "id": 0}),
    # without one: the input's gates and Clifford+T, weighted by T-count
    (None, {"id", "x", "z", "h", "s", "sdg", "cx", "t", "tdg"}, {"t": 1, "tdg": 1}),
])
def test_rus_gate_set(workdir, monkeypatch, given, gates, weights):
    used = {}
    def capture(self, vector_pairs, output_qasm):
        used.update(self.gate_set.gates)
        return False, None, None
    monkeypatch.setattr(Synthesizer, "_synth", capture)
    Synthesizer().synthesis(qasm_file=os.path.join(BENCHMARKS, "rus/2/spec.qasm"), vectors="rus", solving="smt",
                            solver="yices2", complex_representation="Classic",
                            gate_set=None if given is None else GateSet(given))
    assert set(used) == gates
    assert {gate: weight for gate, weight in used.items() if weight} == {g: w for g, w in weights.items() if w}

