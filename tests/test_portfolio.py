"""Portfolio solving (#9), using tests/fake_solver.py instead of real solvers."""

import concurrent.futures
import os
import signal
import sys
import time

import pytest

from conftest import child_processes, process_gone
from solvers import PortfolioSMTSolver, SMTSolver

FAKE = os.path.join(os.path.dirname(__file__), "fake_solver.py")


def portfolio(*solvers):
    # solvers: (mode, delay) pairs
    return PortfolioSMTSolver({f"{mode}-{i}": SMTSolver(f"{mode}-{i}", [sys.executable, FAKE, mode, str(delay)], ["QF_LIA"])
                               for i, (mode, delay) in enumerate(solvers)})


def solve_within(portfolio, formula, seconds=10):
    # a regression must fail the test, not hang the test suite
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(portfolio.solve, formula).result(timeout=seconds)
    except concurrent.futures.TimeoutError:
        pytest.fail(f"portfolio did not answer within {seconds} s")
    finally:
        pool.shutdown(wait=False)


@pytest.fixture
def formula(tmp_path):
    path = tmp_path / "formula.smt2"
    path.write_text("(check-sat)\n")
    return str(path)


def test_all_unknown_returns_unknown(formula):
    assert solve_within(portfolio(("unknown", 0), ("unknown", 0.2), ("unknown", 0.4)), formula) == "unknown"


def test_unknown_does_not_stop_the_others(formula):
    assert "define-fun x" in solve_within(portfolio(("unknown", 0), ("sat", 0.5)), formula)
    assert solve_within(portfolio(("unknown", 0), ("unsat", 0.5)), formula) == "unsat"


def test_losing_solvers_are_killed_and_reaped(formula):
    start = time.monotonic()
    assert "define-fun x" in solve_within(portfolio(("sat", 0.2), ("hang", 0), ("hang", 0)), formula)
    assert time.monotonic() - start < 5
    assert child_processes(b"fake_solver.py") == []


def test_waiting_does_not_spin(formula):
    cpu = time.process_time()
    assert solve_within(portfolio(("unsat", 1.0)), formula) == "unsat"
    # the solver runs for 1 s; a polling loop would burn about that much CPU in this process
    assert time.process_time() - cpu < 0.3


def test_processes_started_by_a_losing_solver_are_killed(formula, tmp_path):
    # like the SMTInterpol script, the wrapper runs the actual solver (java there) as a child, not via exec
    child_pid_file = tmp_path / "child.pid"
    wrapper = tmp_path / "wrapper.sh"
    wrapper.write_text(f'#!/bin/sh\n"{sys.executable}" "{FAKE}" hang 0 "$@" &\necho $! > "{child_pid_file}"\nwait\n')
    wrapper.chmod(0o755)
    solvers = portfolio(("sat", 0.5))
    solvers.solvers["wrapper"] = SMTSolver("wrapper", [str(wrapper)], ["QF_LIA"])
    child = None
    try:
        assert "define-fun x" in solve_within(solvers, formula)
        child = int(child_pid_file.read_text())
        assert process_gone(child), "the solver started by the losing wrapper is still running"
    finally:
        if child is not None and not process_gone(child, seconds=0):
            os.kill(child, signal.SIGKILL)  # do not leave it running after a failure
