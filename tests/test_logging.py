"""Logging through the stdlib `logging` module (#86) and phase timings in `timing` (#87, F41)."""

import logging
import os
import subprocess
import sys
import time

import pytest

from conftest import BENCHMARKS, REPO_ROOT
from generator import Generator
from pareto import Pareto
from synth import Synthesizer
from timing import timed, times

MILQ = os.path.join(REPO_ROOT, "milq")
GHZ2 = os.path.join(BENCHMARKS, "ghz/2.qasm")  # needs two gates, so incremental mode solves at depths 1 and 2
PHASES = ["encoding", "solving", "parsing", "updating"]


def synthesize(mode="incremental", **kwargs):
    # returns the synthesizer, which holds the run's times; the run must find a circuit
    synthesizer = Synthesizer()
    res, _, _ = synthesizer.synthesis(qasm_file=GHZ2, vectors="zero", solving="smt", solver="yices2", mode=mode,
                                      complex_representation="FiveTuple", output_qasm="out.qasm", **kwargs)
    assert res
    return synthesizer


def slow_solver(monkeypatch, seconds):
    # every solve takes at least `seconds`, so solve time leaking into another phase is visible
    check_sat = Generator.check_sat
    def slow(self, *args, **kwargs):
        time.sleep(seconds)
        return check_sat(self, *args, **kwargs)
    monkeypatch.setattr(Generator, "check_sat", slow)


def fits(run_times):
    return sum(run_times[phase] for phase in PHASES) <= run_times["full"]


# timing

def test_timed_accumulates_and_counts_a_phase_that_raises():
    times.clear()
    with timed("a"):
        time.sleep(0.01)
    with timed("a"):
        time.sleep(0.01)
    with pytest.raises(RuntimeError):
        with timed("b"):
            time.sleep(0.01)
            raise RuntimeError
    assert set(times) == {"a", "b"}
    assert times["a"] >= 0.02 and times["b"] >= 0.01


@pytest.mark.parametrize("mode", ["incremental", "basic", "binary", "topdown", "bottomup"])
def test_phases_fit_in_the_full_time(workdir, monkeypatch, mode):
    # incremental mode counted every earlier solve as encoding; the fixed-depth modes never counted encoding
    slow_solver(monkeypatch, 0.2)
    run_times = synthesize(mode).times
    assert run_times["encoding"] > 0
    assert run_times["solving"] >= 0.2
    assert fits(run_times)


def test_incremental_encoding_excludes_solve_time(workdir, monkeypatch):
    slow_solver(monkeypatch, 0.5)
    run_times = synthesize().times
    assert run_times["solving"] >= 1.0  # depths 1 and 2
    assert run_times["encoding"] < 0.5


def test_every_run_keeps_its_own_times(workdir, monkeypatch):
    # the Python API: each synthesizer holds its last run's times, a later run doesn't change them
    first = synthesize()
    first_times = dict(first.times)
    slow_solver(monkeypatch, 0.3)
    second = synthesize()
    assert first.times == first_times
    assert second.times["solving"] >= 0.6 > first.times["solving"]
    assert set(first.times) >= {"full", "parsing", "encoding", "solving", "updating"}


def test_a_second_synthesis_starts_from_zero(workdir):
    times["stale"] = 99.0
    assert "stale" not in synthesize().times
    assert "stale" not in times


def test_a_failed_synthesis_does_not_block_the_next_reset(workdir):
    with pytest.raises(ValueError):
        synthesize(fidelity_threshold=2.0)
    times["stale"] = 99.0
    synthesize()
    assert "stale" not in times


def test_pareto_worker_times_reach_the_parent():
    def work():
        with timed("solving"):
            time.sleep(0.05)
        return "done"
    times.clear()
    times["solving"] = 1.0
    assert Pareto(timeout=60).start(work) == "done"
    # the fork copied the parent's 1.0, only the worker's own time is added
    assert 1.05 <= times["solving"] < 1.5


def test_pareto_worker_times_are_kept_when_it_raises():
    def failing():
        with timed("solving"):
            time.sleep(0.05)
        raise ValueError("boom")
    times.clear()
    with pytest.raises(ValueError, match="boom"):
        Pareto(timeout=60).start(failing)
    assert times["solving"] >= 0.05


def test_nested_synthesis_in_process(workdir, monkeypatch):
    # a recovery-like synthesis run directly from the outer one's _synth, not in a pareto worker
    original = Synthesizer._synth
    nested = []
    def synth_then_recovery(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if not nested:
            nested.append(None)
            nested[0] = synthesize()
        return result
    monkeypatch.setattr(Synthesizer, "_synth", synth_then_recovery)
    slow_solver(monkeypatch, 0.1)
    outer = synthesize()
    inner = nested[0]
    # each run reports its own two solves (depths 1 and 2); the outer run's total includes the nested one's
    assert 0.2 <= inner.times["solving"] < 0.4
    assert outer.times["solving"] >= inner.times["solving"] + 0.2
    assert outer.times["full"] > inner.times["full"]
    assert fits(inner.times) and fits(outer.times)


def test_nested_synthesis_in_a_pareto_worker_keeps_the_outer_times(workdir):
    # like the RUS recovery: a second synthesis (which clears times) runs inside the outer one
    times.clear()
    times["encoding"] = 5.0
    inner_times = Pareto(timeout=60).start(lambda: synthesize().times)
    assert inner_times["encoding"] < 5.0
    assert times["encoding"] > 5.0 and times["solving"] > 0


def test_pareto_incremental_reports_solving_and_parsing(workdir):
    # both run in the forked workers, whose times were thrown away
    run_times = synthesize("pareto-incremental", pareto_timeout=60, max_depth=2).times
    assert run_times["solving"] > 0 and run_times["parsing"] > 0 and run_times["encoding"] > 0
    assert fits(run_times)


# output files

@pytest.mark.parametrize("solving, solver, mode, representation", [("smt", "yices2", "incremental", "FiveTuple"),
                                                                   ("smt", "yices2", "basic", "FiveTuple"),
                                                                   ("gurobi", None, "incremental", "Classic")])
def test_synthesis_without_output_qasm_writes_no_files(workdir, solving, solver, mode, representation):
    # the circuit and the formula go to a temporary directory, removed afterwards
    res, circuit, _ = Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving=solving, solver=solver, mode=mode,
                                              complex_representation=representation)
    assert res and circuit.gate_count() == 2
    assert os.listdir(workdir) == []


def test_synthesis_with_output_qasm_writes_the_circuit_and_formula(workdir):
    res, circuit, _ = Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving="smt", solver="yices2",
                                              mode="basic", output_qasm="out.qasm")
    assert res
    assert sorted(os.listdir(workdir)) == ["out.qasm", "out.smt2"]
    assert (workdir / "out.qasm").read_text().strip() == str(circuit).strip()


# logging

def test_synthesizer_writes_no_log_file(workdir):
    # every Synthesizer used to truncate ./synth.log, e.g. the RUS recovery one wiped the main run's log
    (workdir / "synth.log").write_text("earlier run\n")
    Synthesizer()
    Synthesizer()
    assert (workdir / "synth.log").read_text() == "earlier run\n"


def test_progress_is_logged(workdir, caplog):
    caplog.set_level(logging.INFO)
    synthesize()
    messages = [(record.name, record.getMessage()) for record in caplog.records]
    assert ("synth", "Trying depth: 1") in messages and ("synth", "Trying depth: 2") in messages
    assert ("generator", "Solver returned UNSAT") in messages and ("generator", "Solver returned SAT") in messages
    assert not (workdir / "synth.log").exists()


@pytest.mark.parametrize("level, dumped", [(logging.DEBUG, True), (logging.INFO, False)])
def test_gurobi_model_variables_are_debug_messages(workdir, caplog, level, dumped):
    caplog.set_level(level)
    Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving="gurobi", mode="incremental", complex_representation="Classic")
    variable_lines = [r for r in caplog.records if r.name == "generator" and r.levelno == logging.DEBUG]
    assert bool(variable_lines) == dumped


def test_pysmt_solver_exception_is_a_warning(caplog):
    class Crashing:
        def solve(self):
            raise RuntimeError("solver crashed")
    gen = Generator(mode="pysmt")
    gen.solver = Crashing()
    assert gen.check_sat() is False
    assert any(r.levelno == logging.WARNING and "solver crashed" in r.getMessage() for r in caplog.records)


# the CLI, with a stand-in for the synthesis: it configures logging, the library doesn't

CLI_WRAPPER = """
import logging, runpy, sys
sys.path.insert(0, {src!r})
import synth

def synthesis(self, **kwargs):
    logging.getLogger("generator").warning("cost not proven minimal")
    logging.getLogger("synth").info("progress line")
    logging.getLogger("generator").debug("model variable")
    self.times = dict.fromkeys(["full", "parsing", "encoding", "solving", "updating"], 0.0)
    return True, None, None

synth.Synthesizer.synthesis = synthesis
sys.argv = ["milq", "in.qasm"] + {flags!r}
runpy.run_path({milq!r}, run_name="__main__")
"""


def run_cli_wrapper(flags):
    script = CLI_WRAPPER.format(src=os.path.join(REPO_ROOT, "src"), milq=MILQ, flags=flags)
    run = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    return run


@pytest.mark.parametrize("flags", [[], ["--log"]])
def test_cli_keeps_the_log_off_the_console(workdir, flags):
    run = run_cli_wrapper(flags)
    # warnings reach the user on stderr, the progress log doesn't go to the console
    assert run.stderr == "WARNING: cost not proven minimal\n"
    assert run.stdout.startswith("synthesis successful\nFull time: ")


def test_cli_writes_no_log_by_default(workdir):
    (workdir / "synth.log").write_text("previous run\n")
    run_cli_wrapper([])
    assert (workdir / "synth.log").read_text() == "previous run\n"
    assert os.listdir(workdir) == ["synth.log"]


@pytest.mark.parametrize("flags, path, debug", [
    (["--log"], "synth.log", False),
    (["--log", "run.log"], "run.log", False),
    (["--log", "--verbose"], "synth.log", True),
])
def test_cli_log_file(workdir, flags, path, debug):
    (workdir / path).write_text("previous run\n")
    run = run_cli_wrapper(flags)
    log = (workdir / path).read_text()
    assert "previous run" not in log  # every run starts a new log
    assert "[WARNING][generator] cost not proven minimal" in log
    assert "[INFO][synth] progress line" in log
    assert ("[DEBUG][generator] model variable" in log) == debug
    assert "progress line" not in run.stdout + run.stderr


def test_cli_verbose_prints_the_log_to_stdout(workdir):
    run = run_cli_wrapper(["--verbose"])
    log, result = run.stdout.split("synthesis successful\n")
    assert "[WARNING][generator] cost not proven minimal" in log
    assert "[INFO][synth] progress line" in log
    assert "[DEBUG][generator] model variable" in log
    assert result.startswith("Full time: ")
    assert run.stderr == ""  # the warning is in the log on stdout, not printed twice
    assert os.listdir(workdir) == []


def cli(*args):
    return subprocess.run([sys.executable, MILQ, GHZ2, "-v", "zero", "-o", "out.qasm", *args],
                          capture_output=True, text=True, timeout=300)


@pytest.mark.parametrize("solver", [["-s", "smt", "-a", "yices2"], ["-s", "gurobi", "-c", "Classic"]], ids=["yices2", "gurobi"])
def test_cli_without_o_only_prints_the_circuit(workdir, solver):
    run = subprocess.run([sys.executable, MILQ, GHZ2, "-v", "zero", *solver], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    assert "\nOPENQASM 3.0;\n" in run.stdout and "cx q[" in run.stdout
    assert os.listdir(workdir) == []  # no circuit, formula or log file


@pytest.mark.parametrize("solver", [["-s", "smt", "-a", "yices2"], ["-s", "gurobi", "-c", "Classic"], ["-s", "milp", "-a", "gurobi", "-c", "Classic"]],
                         ids=["yices2", "gurobi", "pulp-gurobi"])
def test_cli_prints_the_result_times_and_circuit(workdir, solver):
    run = cli(*solver, "--log")
    assert run.returncode == 0, run.stderr
    assert run.stderr == ""
    lines = run.stdout.splitlines()
    # nothing else on stdout, e.g. Gurobi's license banner goes to the log
    assert lines[0] == "synthesis successful"
    assert [line.split(" time: ")[0] for line in lines[1:6]] == ["Full", "Parsing", "Encoding", "Solving", "Updating"]
    assert "\n".join(lines[6:]).strip() == (workdir / "out.qasm").read_text().strip()
    seconds = {line.split(" time: ")[0]: float(line.split(" time: ")[1].split()[0]) for line in lines[1:6]}
    assert seconds["Full"] > 0 and seconds["Encoding"] > 0 and seconds["Solving"] > 0
    assert seconds["Encoding"] + seconds["Solving"] + seconds["Parsing"] + seconds["Updating"] <= seconds["Full"]
    log = (workdir / "synth.log").read_text()
    assert "[INFO][synth] Trying depth: 2" in log and "[INFO][generator] Solver returned SAT" in log
    if "gurobi" in solver:
        assert "[INFO][gurobipy]" in log
