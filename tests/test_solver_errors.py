"""Solver answers vs. solver failures (#4), using tests/fake_solver.py instead of real solvers."""

import itertools
import os
import signal
import sys

import pytest
from pysmt.exceptions import SolverReturnedUnknownResultError

from generator import Generator
from logger import Logger
from solvers import PortfolioSMTSolver, SMTSolver, SolverError
from synth import Synthesizer

FAKE = os.path.join(os.path.dirname(__file__), "fake_solver.py")


def fake(mode, delay=0.0, name=None, incremental=False):
    return SMTSolver(name or mode, [sys.executable, FAKE, mode, str(delay)], ["QF_LIA"], incremental_mode=incremental)


@pytest.fixture
def formula(tmp_path):
    path = tmp_path / "formula.smt2"
    path.write_text("(check-sat)\n")
    return str(path)


# file mode (used by the portfolio and by non-incremental single-solver runs)

@pytest.mark.parametrize("mode, expected", [("unsat", "unsat"), ("unknown", "unknown"), ("unsat-then-error", "unsat"),
                                            ("success+unsat", "unsat")])
def test_file_mode_answers(formula, mode, expected):
    assert fake(mode).solve(formula) == expected


@pytest.mark.parametrize("mode", ["sat", "delta-sat"])
def test_file_mode_sat_returns_model(formula, mode):
    assert "define-fun x" in fake(mode).solve(formula)


@pytest.mark.parametrize("mode, message", [("error", "boom"), ("crash", "fake solver crashed")])
def test_file_mode_failure_raises(formula, mode, message):
    with pytest.raises(SolverError, match=message):
        fake(mode).solve(formula)


def test_file_mode_command_not_found(formula, tmp_path):
    # a wrapper script whose program is missing (like SMTInterpol's script without java) exits with 127
    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text("#!/bin/sh\nmilq-nonexistent-program \"$@\"\n")
    wrapper.chmod(0o755)
    with pytest.raises(SolverError, match=r"exit code 127 \(command not found\)"):
        SMTSolver("wrapper", [str(wrapper)], ["QF_LIA"]).solve(formula)


def test_file_mode_missing_binary_raises(formula):
    with pytest.raises(SolverError, match="could not be started"):
        SMTSolver("missing", ["/nonexistent/solver"], ["QF_LIA"]).solve(formula)


# incremental mode (one solver process fed through stdin)

def check_sat(solver):
    solver.create_process()
    try:
        solver.write_incremental("(declare-fun x () Int)")
        solver.write_incremental("(check-sat)")
        return solver.solve()
    finally:
        solver.process.kill()
        solver.process.wait()


@pytest.mark.parametrize("mode, expected", [("sat", "sat"), ("unsat", "unsat"), ("unknown", "unknown"),
                                            ("delta-sat", "sat"), ("success+sat", "sat"), ("success+unsat", "unsat")])
def test_incremental_answers(mode, expected):
    assert check_sat(fake(mode, incremental=True)) == expected


@pytest.mark.parametrize("mode, message", [("error", "boom"), ("crash", "fake solver crashed")])
def test_incremental_failure_raises(mode, message):
    with pytest.raises(SolverError, match=message):
        check_sat(fake(mode, incremental=True))


def test_incremental_write_to_exited_solver_raises():
    solver = fake("exit", incremental=True)
    solver.create_process()
    solver.process.wait()  # the solver is gone before it read anything
    with pytest.raises(SolverError, match="exit code 2: fake solver exited"):
        solver.write_incremental("(declare-fun x () Int)")


# portfolio: a failing solver is skipped, the others decide

def test_portfolio_unknown_lets_others_decide(formula):
    portfolio = PortfolioSMTSolver({"unknown": fake("unknown"), "slow-sat": fake("sat", 0.5, name="slow-sat")})
    assert "define-fun x" in portfolio.solve(formula)


def test_portfolio_skips_failed_solvers(formula):
    portfolio = PortfolioSMTSolver({"error": fake("error"), "crash": fake("crash"),
                                    "missing": SMTSolver("missing", ["/nonexistent/solver"], ["QF_LIA"]),
                                    "slow-sat": fake("sat", 0.5, name="slow-sat")})
    assert "define-fun x" in portfolio.solve(formula)


def test_portfolio_unsat_after_failure(formula):
    portfolio = PortfolioSMTSolver({"crash": fake("crash"), "slow-unsat": fake("unsat", 0.5, name="slow-unsat")})
    assert portfolio.solve(formula) == "unsat"


def test_portfolio_all_failed_raises(formula):
    portfolio = PortfolioSMTSolver({"error": fake("error"), "crash": fake("crash")})
    with pytest.raises(SolverError, match="all solvers of the portfolio failed"):
        portfolio.solve(formula)


# the generator must not turn a failure into "no circuit at this depth"

def test_generator_check_sat_propagates_failure(formula):
    gen = Generator(mode="smtlib", logger=None)
    gen.solver = fake("error")
    with pytest.raises(SolverError, match="boom"):
        gen.check_sat(formula)


def test_incremental_solver_exiting_mid_model_raises():
    # used to spin at 100% CPU, waiting for the model's closing parenthesis (BUGS B3)
    def hang(signum, frame):
        raise TimeoutError("get_model did not return")
    solver = fake("partial-model", incremental=True)
    solver.create_process()
    previous = signal.signal(signal.SIGALRM, hang)
    signal.alarm(10)
    try:
        solver.write_incremental("(check-sat)")
        assert solver.solve() == "sat"
        solver.write_incremental("(get-value (x))")
        with pytest.raises(SolverError, match=r"exit code 4.*while sending the model"):
            solver.get_model()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        solver.close()


# unknown is not UNSAT (#76): a search goes on, but synthesis() never presents it as a proof

def test_generator_counts_unknown(formula):
    gen = Generator(mode="smtlib", logger=Logger())
    gen.solver = fake("unknown")
    assert gen.check_sat(formula) is False
    assert gen.unknowns == 1


class RaisingSolver:
    def __init__(self, error):
        self.error = error

    def solve(self):
        raise self.error


def test_pysmt_unknown_is_counted():
    gen = Generator(mode="pysmt", logger=Logger())
    gen.solver = RaisingSolver(SolverReturnedUnknownResultError())
    assert gen.check_sat() is False
    assert gen.unknowns == 1


def test_pysmt_failure_raises():
    # used to be logged as UNKNOWN/UNSAT and read as "no circuit" (BUGS N11)
    gen = Generator(mode="pysmt", logger=Logger())
    gen.solver = RaisingSolver(RuntimeError("parse error"))
    with pytest.raises(SolverError, match="pySMT solver failed: RuntimeError: parse error"):
        gen.check_sat()
    assert gen.unknowns == 0


def answer_unknown(monkeypatch, calls=None):
    # the real solver runs, but the answers of the given calls (all if None) are replaced by unknown
    original, count = SMTSolver.solve, itertools.count()

    def solve(self, formula_file=None):
        answer = original(self, formula_file)
        return "unknown" if calls is None or next(count) in calls else answer
    monkeypatch.setattr(SMTSolver, "solve", solve)


def synthesize(workdir, mode, **kwargs):
    qasm = workdir / "in.qasm"
    qasm.write_text('OPENQASM 3.0;\ninclude "stdgates.inc";\nqubit[1] q;\nh q[0];\nt q[0];\n')
    return Synthesizer().synthesis(qasm_file=str(qasm), vectors="all", mode=mode, solving="smt", solver="yices2",
                                   output_qasm="out.qasm", **kwargs)


def test_incremental_steps_past_unknown_and_warns(workdir, monkeypatch):
    answer_unknown(monkeypatch, calls={0})  # depth 1
    res, circuit, _ = synthesize(workdir, "incremental")
    assert res
    assert [gate.name for gate in circuit.gates] == ["h", "t"]
    log = (workdir / "synth.log").read_text()
    assert "[WARNING] : 1 solver call(s) answered unknown: the circuit is correct, but its optimality is not proven" in log


@pytest.mark.parametrize("mode, kwargs", [("basic", {}), ("incremental", {"max_depth": 2}),
                                          ("pareto-incremental", {"max_depth": 2})])
def test_unknown_is_not_reported_as_no_circuit(workdir, monkeypatch, mode, kwargs):
    # pareto solves in a forked worker, so this also checks that the count comes back from it
    answer_unknown(monkeypatch)
    with pytest.raises(SolverError, match="answered unknown: no circuit found, but none was proven not to exist"):
        synthesize(workdir, mode, **kwargs)
