import os
import shutil
import sys
import tempfile
import time

import numpy as np
import pytest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
BENCHMARKS = os.path.join(REPO_ROOT, "benchmarks")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from complex.classic import Complex
from complex.fivetuple import FiveTuple
from generator import Generator
from sim import Simulator
from solver_config import ENV_VARIABLE, load_solver_config
from solver_detection import detect, render
from solver_download import bin_dir
from solvers import SMTSolver

OMEGA = np.exp(1j * np.pi / 4)

# the tests use the SMT solvers installed on this computer, through the configuration ./configure-solvers would
# write for them; the user's solvers.toml is neither read nor changed
_solver_config_dir = tempfile.mkdtemp(prefix="milq-solvers-")
SOLVER_CONFIG = os.path.join(_solver_config_dir, "solvers.toml")
_detections = detect([bin_dir()])
with open(SOLVER_CONFIG, "w") as f:
    f.write(render(_detections))
SOLVERS = load_solver_config(SOLVER_CONFIG) if any(d.path for d in _detections) else {}


def pytest_configure(config):
    # in os.environ, so that the milq processes started by the tests see it too
    os.environ[ENV_VARIABLE] = SOLVER_CONFIG


def pytest_unconfigure(config):
    shutil.rmtree(_solver_config_dir, ignore_errors=True)


def pytest_report_header(config):
    return "SMT solvers: " + ", ".join(f"{name} ({solver.path})" for name, solver in SOLVERS.items())


def z3_generator(logic="QF_LIA"):
    # an SMT-LIB generator solved by z3 (installed with z3-solver); check it with z3_check
    gen = Generator(mode="smtlib", logic=logic)
    gen.solver = SMTSolver("z3", SOLVERS["z3"].command(), [logic])
    return gen


def z3_check(gen, directory):
    return gen.check_sat(gen.write_formula(os.path.join(directory, "formula.smt2")))


def to_complex(element, k, representation):
    # numeric value of a simulated amplitude
    if representation is FiveTuple:
        return (element.a + element.b * OMEGA + element.c * OMEGA**2 + element.d * OMEGA**3) / np.sqrt(2) ** k
    return element.real + 1j * element.imag


def unitary(qasm_file, representation=Complex):
    # unitary of a circuit, column i is the image of the i-th computational basis state
    pairs = Simulator(qasm_file, complex_representation=representation).simulate_circuit()
    return np.array([[to_complex(out[i], out.k, representation) for i in range(len(out))] for _, out in pairs]).T


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    # the synthesizer writes logs and formulae into the working directory
    monkeypatch.chdir(tmp_path)
    return tmp_path


def child_processes(marker):
    # processes started by this test process whose command line contains marker (bytes) and that still
    # exist (running, or exited but not reaped)
    children = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read()
        except (OSError, IndexError, ValueError):
            continue
        if ppid == os.getpid() and marker in cmdline:
            children.append(int(pid))
    return children


def process_gone(pid, seconds=3):
    # true once the process no longer runs (gone, or a zombie waiting to be reaped by init)
    deadline = time.monotonic() + seconds
    while True:
        try:
            with open(f"/proc/{pid}/stat") as f:
                if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                    return True
        except (FileNotFoundError, ProcessLookupError):  # gone, possibly while reading
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
