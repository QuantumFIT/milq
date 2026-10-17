"""Unit tests for the pieces of the pareto-incremental mode that need no full Gurobi license."""

import os
import time

import numpy as np
import pytest
from pysmt.shortcuts import Solver

import pareto
from complex.classic import Complex
from complex.fivetuple import FiveTuple
from complex.vector import Vector
from conftest import BENCHMARKS, unitary
from gates import Circuit, Gate, GateSet
from generator import Generator
from pareto import Pareto
from solvers import SolverError
from synth import Synthesizer, rus_recovery_pairs


def classic_vector(amplitudes):
    vec = Vector(q=len(amplitudes), element_representation=Complex, k=0)
    for i, amplitude in enumerate(amplitudes):
        vec[i] = Complex(a=float(np.real(amplitude)), b=float(np.imag(amplitude)))
    return vec


def values(vec):
    return np.array([e.real + 1j * e.imag for e in vec])


def test_best_on_empty_front():
    assert Pareto(timeout=60).best() == (False, None, [])


def test_rus_recovery_pairs_use_failure_state_and_concrete_input():
    # target q0, ancilla q1; the attempt fails when the ancilla is measured as 1
    output = classic_vector([0.5, 0.5, 0.5, -0.5])
    input_state = classic_vector([1, 0, 0, 0])
    [(failure_state, target)] = rus_recovery_pairs([output], [(input_state, output)], [1, 1])
    # normalized projection onto ancilla = 1, mapped back to the input state
    np.testing.assert_allclose(values(failure_state), [0, 0, 1 / np.sqrt(2), -1 / np.sqrt(2)], atol=1e-8)
    np.testing.assert_allclose(values(target), values(input_state))


def five_tuple_vector(a_values, k):
    vec = Vector(q=len(a_values), element_representation=FiveTuple, k=k)
    for i, a in enumerate(a_values):
        vec[i] = FiveTuple(a=a)
    return vec


@pytest.mark.parametrize("representation", ["Classic", "FiveTuple"])
def test_rus_cost(workdir, representation):
    # target q0, ancilla q1; the attempt succeeds when the ancilla is measured as 0
    if representation == "Classic":
        always, half = classic_vector([1, 0, 0, 0]), classic_vector([0.5, 0.5, 0.5, -0.5])
    else:
        always, half = five_tuple_vector([1, 0, 0, 0], k=0), five_tuple_vector([1, 1, 1, -1], k=2)
    synthesizer = Synthesizer()
    synthesizer.qubits_to_measure = [1]
    circuit, recovery = Circuit(gates=[], q=2, d=1), Circuit(gates=[], q=2, d=1)
    circuit.cost, recovery.cost = 3, 2
    # no recovery is needed when the attempt always succeeds
    assert synthesizer.rus_cost(circuit, None, [always]) == (3, pytest.approx(1.0))
    assert synthesizer.rus_cost(circuit, recovery, [half]) == (5, pytest.approx(0.5))


def test_filter_model_pysmt_excludes_model():
    gen = Generator(mode="pysmt", logger=None)
    gen.solver = Solver(name="z3")
    names = ["L0_h_q0", "L1_cx_q0_q1"]
    for name in names:
        gen.add_assertion(gen.declare_bool(name))
    assert gen.solver.solve()
    gen.filter_model(names, 2)
    assert not gen.solver.solve()


@pytest.mark.parametrize("expired_after", [1, 3])
def test_pareto_timeout_returns_cleanly(workdir, monkeypatch, expired_after):
    # the time limit is met right after the first solve, or later during enumeration
    calls = {"n": 0}

    def timeout_met(self):
        calls["n"] += 1
        return calls["n"] >= expired_after

    monkeypatch.setattr(pareto.Pareto, "timeout_met", timeout_met)
    res, circuit, vectors = Synthesizer().synthesis(qasm_file=os.path.join(BENCHMARKS, "ghz/2.qasm"), vectors="zero",
                                                    solving="smt", solver="yices2", mode="pareto-incremental",
                                                    complex_representation="FiveTuple", output_qasm="out.qasm")
    assert vectors == []
    assert res == (circuit is not None)


def one_gate_circuit(name="h"):
    circuit = Circuit(gates=[], q=1, d=1)
    circuit[0] = Gate(name, [0])
    return circuit


@pytest.mark.parametrize("maximize_y, points, front", [
    (False, [(2, 2), (3, 1), (3, 3), (5, 7)], [(2, 2), (3, 1)]),          # e.g. gate count vs. T-count
    (True, [(2, 0.5), (3, 0.9), (3, 0.4), (40, 1.0)], [(2, 0.5), (3, 0.9), (40, 1.0)]),  # T-count vs. P[success]
])
def test_front_keeps_undominated_points_without_bounds(workdir, maximize_y, points, front):
    pareto_front = Pareto(timeout=60, maximize_y=maximize_y)
    for x, y in points:
        pareto_front.add_point(x, y, 1, one_gate_circuit(), None)
    assert sorted((p[0], p[1]) for p in pareto_front.get_frontier()) == front
    assert len(os.listdir("pareto_front")) == len(points)  # every point is kept, none is cut off by a bound


def test_worker_errors_are_raised_in_the_parent():
    def failing():
        raise SolverError("yices2 failed: boom")
    with pytest.raises(SolverError, match="boom") as raised:
        Pareto(timeout=60).start(failing)
    assert any("pareto worker" in note for note in getattr(raised.value, "__notes__", []))


def test_worker_exiting_without_a_result_is_an_error():
    with pytest.raises(RuntimeError, match="exit code 3"):
        Pareto(timeout=60).start(lambda: os._exit(3))


def test_large_result_does_not_block_the_worker():
    # larger than the pipe buffer: joining the worker before reading its result would wait until the timeout
    big = "x" * 20_000_000
    start = time.monotonic()
    assert Pareto(timeout=30).start(lambda: big) == big
    assert time.monotonic() - start < 10


def test_non_rus_points_are_gate_count_and_weighted_cost(workdir, monkeypatch):
    # t;t equals s; with s free (weight 0) the front is the single s gate, t;t costs 2
    qasm = workdir / "tt.qasm"
    qasm.write_text("OPENQASM 2.0;\nqreg q[1];\nt q[0];\nt q[0];\n")
    gate_set = GateSet(["t", "s"])
    gate_set.add_gate("s", weight=0, qubits=1)
    points = []
    original_add_point = Pareto.add_point
    monkeypatch.setattr(Pareto, "add_point", lambda self, x, y, *rest: (points.append((x, y)), original_add_point(self, x, y, *rest)))
    res, circuit, _ = Synthesizer().synthesis(qasm_file=str(qasm), vectors="all", solving="smt", solver="yices2",
                                              mode="pareto-incremental", complex_representation="FiveTuple",
                                              gate_set=gate_set, output_qasm="out.qasm", pareto_timeout=60, max_depth=2)
    assert res
    assert [gate.name for gate in circuit.operations()] == ["s"]
    assert (1, 0) in points and (2, 2) in points
    # the output file holds the returned circuit, not the last enumerated model
    output = (workdir / "out.qasm").read_text()
    assert "s q[0];" in output and "t q[0];" not in output


def test_every_circuit_is_enumerated_once(workdir, monkeypatch):
    # without empty (id) layers, a circuit is found once, at the depth equal to its gate count
    points = []
    original_add_point = Pareto.add_point
    def record(self, x, y, depth, circuit, recovery_circuit):
        points.append((depth, tuple(str(gate) for gate in circuit.gates)))
        original_add_point(self, x, y, depth, circuit, recovery_circuit)
    monkeypatch.setattr(Pareto, "add_point", record)
    qasm_file = os.path.join(BENCHMARKS, "ghz/2.qasm")
    res, _, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="zero", solving="smt", solver="yices2",
                                        mode="pareto-incremental", complex_representation="FiveTuple",
                                        output_qasm="out.qasm", pareto_timeout=120, max_depth=3)
    assert res
    assert {depth for depth, _ in points} == {2, 3}
    assert all(len(gates) == depth and not any(g.startswith("id ") for g in gates) for depth, gates in points)
    assert len({gates for _, gates in points}) == len(points)
    for point in os.listdir("pareto_front"):  # every enumerated circuit prepares the same state
        np.testing.assert_allclose(unitary(os.path.join("pareto_front", point))[:, 0], unitary(qasm_file)[:, 0], atol=1e-9)


def test_stale_recovery_file_is_removed(workdir):
    # #74, F52: <out>_recovery.qasm belongs to the best point; a point without recovery leaves none behind
    qasm = workdir / "x.qasm"
    qasm.write_text("OPENQASM 2.0;\nqreg q[1];\nx q[0];\n")
    (workdir / "out_recovery.qasm").write_text("stale")
    res, _, _ = Synthesizer().synthesis(qasm_file=str(qasm), vectors="all", solving="smt", solver="yices2",
                                        mode="pareto-incremental", output_qasm="out.qasm", pareto_timeout=60, max_depth=1)
    assert res
    assert not (workdir / "out_recovery.qasm").exists()
