"""Solver answers vs. solver failures (#4), using tests/fake_solver.py instead of real solvers."""

import os
import sys

import pytest

from generator import Generator
from solvers import PortfolioSMTSolver, SMTSolver, SolverError

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
