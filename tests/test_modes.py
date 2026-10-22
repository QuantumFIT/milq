"""Fixed-depth search modes, approximate synthesis and end-of-circuit measurements."""

import os

import numpy as np
import pytest

from conftest import BENCHMARKS, unitary
from gates import GateSet
from synth import Synthesizer

GHZ2 = os.path.join(BENCHMARKS, "ghz/2.qasm")
# the MILP backend with CBC takes 10-40 s per mode here, so it is left out
BACKENDS = [("smt", "yices2", "FiveTuple"), ("gurobi", "gurobi", "Classic")]


@pytest.mark.parametrize("mode", ["basic", "binary", "topdown", "bottomup"])
@pytest.mark.parametrize("solving, solver, representation", BACKENDS)
def test_fixed_depth_modes(workdir, mode, solving, solver, representation):
    res, circuit, _ = Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving=solving, solver=solver, mode=mode,
                                              complex_representation=representation, d=3, output_qasm="out.qasm")
    assert res
    if mode == "basic" and solving == "smt":
        # SMT solvers do not minimize: basic returns some circuit within d layers
        assert circuit.gate_count() <= 3
    else:
        assert circuit.gate_count() == 2
    np.testing.assert_allclose(unitary("out.qasm")[:, 0], unitary(GHZ2)[:, 0], atol=1e-9)


@pytest.mark.parametrize("solving, solver", [("smt", "yices2"), ("gurobi", "gurobi")])
def test_approximate_synthesis(workdir, solving, solver):
    res, circuit, _ = Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving=solving, solver=solver,
                                              mode="incremental", complex_representation="Classic", approx=True,
                                              fidelity_threshold=0.99, output_qasm="out.qasm")
    assert res
    # GHZ needs both gates: with one gate the fidelity is at most 1/2
    assert circuit.gate_count() == 2
    np.testing.assert_allclose(abs(np.vdot(unitary("out.qasm")[:, 0], unitary(GHZ2)[:, 0])), 1, atol=1e-6)


def test_approximate_synthesis_needs_a_nonlinear_backend(workdir):
    with pytest.raises(NotImplementedError, match="approximate equivalence not supported for milp"):
        Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving="milp", solver="cbc", mode="basic",
                                complex_representation="Classic", approx=True, fidelity_threshold=0.99)


@pytest.mark.parametrize("solving, solver, mode", [("smt", "yices2", "incremental"), ("smt", "yices2", "basic"),
                                                   ("gurobi", "gurobi", "basic")])
def test_end_of_circuit_measurement(workdir, solving, solver, mode):
    # measuring q[0] = 0 after h; cx leaves |00>, which the empty circuit also gives
    with open("in.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[2];\ncreg c[2];\nh q[0];\ncx q[0], q[1];\nmeasure q[0] -> c[0];\n")
    res, circuit, _ = Synthesizer().synthesis(qasm_file="in.qasm", vectors="zero", solving=solving, solver=solver, mode=mode,
                                              complex_representation="Classic", output_qasm="out.qasm")
    assert res
    assert circuit.gate_count() == 0
    assert "c[0] = measure q[0];" in str(circuit)


def test_end_of_circuit_measurement_needs_classic(workdir):
    with open("in.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[1];\ncreg c[1];\nh q[0];\nmeasure q[0] -> c[0];\n")
    with pytest.raises(ValueError, match="only supported for a\\+bj"):
        Synthesizer().synthesis(qasm_file="in.qasm", vectors="zero", solving="smt", solver="yices2",
                                complex_representation="FiveTuple")


@pytest.mark.parametrize("mode", ["basic", "binary", "topdown", "bottomup"])
def test_cost_search_with_a_gate_heavier_than_one(workdir, mode):
    # the cost searches stopped at d+1, which only holds for unit weights (#72 F18)
    (workdir / "in.qasm").write_text('OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[1];\nh q[0];\n')
    gate_set = GateSet(["h", "x"])
    gate_set.set_gate("h", weight=3, qubits=1)
    res, circuit, _ = Synthesizer().synthesis(qasm_file="in.qasm", vectors="all", solving="smt", solver="yices2",
                                              mode=mode, gate_set=gate_set, output_qasm="out.qasm")
    assert res
    assert [gate.name for gate in circuit.operations()] == ["h"]
