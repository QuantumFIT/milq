"""End-to-end synthesis with the bundled SMT solvers and (size-limited) Gurobi."""

import os

import numpy as np
import pytest

from conftest import BENCHMARKS, unitary
from synth import Synthesizer
from gates import GateSet

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


def test_jamiolkowski_basic_mode(workdir):
    # only the first half of the 2*q qubits has selection variables; add_constraints asked for all of them (KeyError)
    with open("ht.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[1];\nh q[0];\nt q[0];\n")
    res, circuit, _ = Synthesizer().synthesis(qasm_file="ht.qasm", vectors="jamiolkowski", solving="smt", solver="yices2",
                                              mode="basic", complex_representation="FiveTuple", gate_set=GateSet(["h", "t"]))
    assert res
    assert [str(gate) for gate in circuit.gates] == ["h q[0];", "t q[0];"]


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
