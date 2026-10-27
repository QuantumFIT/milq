"""Solver processes end with the synthesis that started them (#77, F35)."""

import os
import signal
import sys
import time

import pytest

from conftest import BENCHMARKS, child_processes, process_gone
from solvers import PortfolioSMTSolver, SMTSolver, SolverError
from synth import Synthesizer

FAKE = os.path.join(os.path.dirname(__file__), "fake_solver.py")
YICES = b"yices"  # yices-smt2, or yices_smt2 in the SMT-COMP builds


def incremental_fake(mode="sat"):
    return SMTSolver(mode, [sys.executable, FAKE, mode, "0"], ["QF_LIA"], incremental_mode=True)


def test_close_stops_and_reaps_the_solver():
    solver = incremental_fake()
    solver.create_process()
    process = solver.process
    solver.close()
    assert process.returncode is not None
    assert solver.process is None
    assert child_processes(b"fake_solver.py") == []
    solver.close()  # nothing left to stop


def test_close_does_not_wait_for_a_check_in_progress():
    solver = incremental_fake("hang")
    solver.create_process()
    solver.write_incremental("(check-sat)")  # never answered
    start = time.monotonic()
    solver.close()
    assert time.monotonic() - start < 5
    assert child_processes(b"fake_solver.py") == []


def test_close_after_the_solver_died_during_a_write():
    # the statement that could not be sent stays in the input buffer, and closing the input tries to send it again
    solver = incremental_fake("exit")
    solver.create_process()
    solver.process.wait()  # the solver is gone before it read anything
    with pytest.raises(SolverError):
        solver.write_incremental("(declare-fun x () Int)")
    solver.close()
    assert solver.process is None


def test_close_stops_a_solver_that_a_wrapper_runs_as_a_child(tmp_path):
    # like SMTInterpol's script, which runs java as a child instead of exec-ing it; the child ends on end of input
    child_pid_file = tmp_path / "child.pid"
    wrapper = tmp_path / "wrapper.sh"
    # in the background to learn its pid; an asynchronous command gets /dev/null as input, hence the copy in fd 3
    wrapper.write_text(f'#!/bin/sh\nexec 3<&0\n"{sys.executable}" "{FAKE}" sat 0 <&3 &\necho $! > "{child_pid_file}"\nwait\n')
    wrapper.chmod(0o755)
    solver = SMTSolver("wrapper", [str(wrapper)], ["QF_LIA"], incremental_mode=True)
    solver.create_process()
    child = None
    try:
        solver.write_incremental("(check-sat)")
        assert solver.solve() == "sat"  # the wrapper has started its child by now
        child = int(child_pid_file.read_text())
        solver.close()
        assert process_gone(child), "the solver started by the wrapper is still running"
    finally:
        if child is not None and not process_gone(child, seconds=0):
            os.kill(child, signal.SIGKILL)  # do not leave it running after a failure


def test_solver_stays_in_the_process_group_of_milq():
    # `timeout milq ...` and Ctrl-C signal the whole process group; in a group of its own, the solver would keep
    # running after MILQ is killed without a chance to call close()
    solver = incremental_fake()
    solver.create_process()
    try:
        assert os.getpgid(solver.process.pid) == os.getpgid(0)
    finally:
        solver.close()


def test_portfolio_close_stops_every_solver():
    portfolio = PortfolioSMTSolver({"a": incremental_fake(), "b": incremental_fake()})
    portfolio.create_process()
    portfolio.close()
    assert child_processes(b"fake_solver.py") == []


def synthesize(synthesizer, mode="incremental", **kwargs):
    return synthesizer.synthesis(qasm_file=os.path.join(BENCHMARKS, "ghz", "2.qasm"), vectors="all", solving="smt",
                                 solver="yices2", mode=mode, complex_representation="FiveTuple",
                                 output_qasm="out.qasm", **kwargs)


@pytest.mark.parametrize("mode", ["incremental", "pareto-incremental"])
def test_synthesis_stops_its_solver(workdir, mode):
    # every synthesis left its solver running
    for _ in range(3):
        res, _, _ = synthesize(Synthesizer(), mode, max_depth=2, pareto_timeout=60)
        assert res
    assert child_processes(YICES) == []


def test_synthesis_without_a_circuit_stops_its_solver(workdir):
    res, circuit, _ = synthesize(Synthesizer(), max_depth=1)
    assert (res, circuit) == (False, None)
    assert child_processes(YICES) == []


def test_synthesis_stops_its_solver_on_an_exception(workdir, monkeypatch):
    def fail(synthesizer, vector_pairs, output_qasm):
        assert child_processes(YICES), "the solver should run during the synthesis"
        raise RuntimeError("encoding failed")

    monkeypatch.setattr(Synthesizer, "_synth", fail)
    with pytest.raises(RuntimeError, match="encoding failed"):
        synthesize(Synthesizer())
    assert child_processes(YICES) == []


def test_close_exits_the_pysmt_solver(workdir):
    # pySMT's Solver and Portfolio are stopped with exit(); a stand-in, as a second pySMT synthesis in one process
    # fails (#90)
    class PySMTSolver:
        exits = 0

        def exit(self):
            self.exits += 1

    synthesizer = Synthesizer()
    synthesizer.gen.mode = "pysmt"
    synthesizer.gen.solver = PySMTSolver()
    synthesizer.close()
    assert synthesizer.gen.solver.exits == 1


def test_synthesizer_is_a_context_manager(workdir):
    with Synthesizer():  # nothing to stop without a synthesis
        pass
    with Synthesizer() as synthesizer:
        assert synthesize(synthesizer)[0]
    assert child_processes(YICES) == []
