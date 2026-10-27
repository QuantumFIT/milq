"""Exit status and error messages of the milq script."""

import os
import subprocess
import sys

import pytest

from conftest import BENCHMARKS, REPO_ROOT

GHZ = os.path.join(BENCHMARKS, "ghz/2.qasm")


def milq(*args):
    return subprocess.run([sys.executable, os.path.join(REPO_ROOT, "milq"), *args], capture_output=True, text=True)


def simulator(*args):
    return subprocess.run([sys.executable, os.path.join(REPO_ROOT, "cli/simulator.py"), *args], capture_output=True, text=True)


def test_success_exits_0(workdir):
    assert milq(GHZ, "-s", "smt").returncode == 0  # -a defaults to yices2 with -s smt


def test_no_circuit_within_max_depth_exits_3(workdir):
    result = milq(GHZ, "-s", "smt", "--max-depth", "1")
    assert result.returncode == 3
    assert "synthesis failed" in result.stderr


@pytest.mark.parametrize("args", [
    ["-s", "smt", "-a", "cbc"],
    ["-s", "milp", "-a", "yices2"],
    ["-s", "gurobi", "-a", "cbc"],
    ["-s", "smt", "-m", "basic", "-d", "-1"],
    ["-s", "smt", "-d", "3"],
    ["-s", "smt", "-m", "basic", "--max-depth", "2"],
    ["-s", "smt", "--max-depth", "-1"],  # 0 is valid: only the empty circuit
    ["-s", "smt", "-f", "0.5"],
    ["-s", "smt", "-ap", "-f", "2"],
    ["-s", "smt", "-pt", "10"],
    ["-s", "smt", "-m", "pareto-incremental", "-pt", "-5"],
    ["-s", "smt", "-T", "1"],
    ["-s", "smt", "-a", "gurobi"],
    ["-s", "gurobi", "--solver-config", "solvers.toml"],
    ["-s", "smt", "-a", "no-such-solver"],  # not in the solver configuration
])
def test_invalid_options_are_usage_errors(workdir, args):
    result = milq(GHZ, *args)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_missing_input_is_an_error_without_traceback(workdir):
    result = milq("nonexistent.qasm", "-s", "smt")
    assert result.returncode == 1
    assert result.stderr.startswith("milq: error:")


@pytest.mark.parametrize("args", [["-m", "7"], ["-T", "1"], ["-v", "rus", "-T", "-1"], ["-v", "rus", "-T", "0"],
                                  ["-v", "rus", "-A", "-1"], ["-v", "rus", "-T", "x"]])
def test_invalid_simulator_options_are_usage_errors(args):
    result = simulator(GHZ, *args)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr


def test_simulator_errors_without_traceback(workdir):
    result = simulator("nonexistent.qasm")
    assert result.returncode == 1
    assert result.stderr.startswith("simulator: error:")
