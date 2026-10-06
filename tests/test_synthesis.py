"""End-to-end synthesis with the bundled SMT solvers and (size-limited) Gurobi."""

import os

import numpy as np
import pytest

from conftest import BENCHMARKS, unitary
from synth import Synthesizer

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
                                              output_qasm="out.qasm", pareto_timeout=60)
    assert res
    assert gate_count(circuit) == 2
    # both Bell-state preparations, h + cx in either orientation, are optimal points
    points = sorted(os.listdir("pareto_front"))
    assert len(points) == 2
    assert os.path.exists("pareto_front.pdf")
    for point in points:
        np.testing.assert_allclose(unitary(os.path.join("pareto_front", point))[:, 0], unitary(qasm_file)[:, 0], atol=1e-9)
