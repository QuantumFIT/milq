import os
import sys

import numpy as np
import pytest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
BENCHMARKS = os.path.join(REPO_ROOT, "benchmarks")
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from complex.classic import Complex
from complex.fivetuple import FiveTuple
from sim import Simulator

OMEGA = np.exp(1j * np.pi / 4)


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
