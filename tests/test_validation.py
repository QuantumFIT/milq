"""Argument validation of Synthesizer.synthesis."""

import os

import pytest

from conftest import BENCHMARKS
from synth import Synthesizer

GHZ = os.path.join(BENCHMARKS, "ghz/2.qasm")


def synthesize(**kwargs):
    arguments = dict(qasm_file=GHZ, vectors="all", solving="smt", solver="yices2", mode="incremental")
    arguments.update(kwargs)
    return Synthesizer().synthesis(**arguments)


def test_qasm_file_and_matrix_are_exclusive(workdir):
    with pytest.raises(ValueError, match="qasm_file and matrix cannot be provided at the same time"):
        synthesize(vectors="rus", matrix=object())


def test_divide_and_conquer_is_rejected(workdir):
    with pytest.raises(ValueError, match="mode can be only"):
        synthesize(mode="divide-and-conquer")


def test_mode_message_lists_all_modes(workdir):
    with pytest.raises(ValueError, match="pareto-incremental"):
        synthesize(mode="unknown")


def test_unknown_vectors_are_rejected(workdir):
    with pytest.raises(ValueError, match="vectors can be only"):
        synthesize(vectors="unknown")


def test_some_input_is_required(workdir):
    with pytest.raises(ValueError, match="qasm_file, matrix, or vector_pairs is required"):
        synthesize(qasm_file=None)
