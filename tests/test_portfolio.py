"""Portfolio solving (#9), using tests/fake_solver.py instead of real solvers."""

import concurrent.futures
import os
import sys
import time

import pytest

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


def fake_solver_children():
    # fake solver processes started by this test process that still exist (running or not reaped)
    children = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read()
        except (OSError, IndexError, ValueError):
            continue
        if ppid == os.getpid() and b"fake_solver.py" in cmdline:
            children.append(int(pid))
    return children


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
    assert fake_solver_children() == []


def test_waiting_does_not_spin(formula):
    cpu = time.process_time()
    assert solve_within(portfolio(("unsat", 1.0)), formula) == "unsat"
    # the solver runs for 1 s; a polling loop would burn about that much CPU in this process
    assert time.process_time() - cpu < 0.3
