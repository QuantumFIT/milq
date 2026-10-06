"""Unit tests for the pieces of the pareto-incremental mode that need no full Gurobi license."""

import os

import numpy as np
import pytest
from pysmt.shortcuts import Solver

import pareto
from complex.classic import Complex
from complex.vector import Vector
from conftest import BENCHMARKS
from generator import Generator
from pareto import Pareto
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
