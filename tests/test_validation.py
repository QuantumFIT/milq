"""Argument validation of Synthesizer.synthesis."""

import os

import pytest

from complex.classic import Complex
from complex.fivetuple import FiveTuple
from complex.vector import Vector
from conftest import BENCHMARKS
from gates import GateSet
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


@pytest.mark.parametrize("basis", ["pauli", "CB"])
def test_only_the_computational_basis(workdir, basis):
    # #79, F48: "CB" used to encode no gate and fail later with an unrelated solver error
    with pytest.raises(ValueError, match="basis can be only cb"):
        synthesize(basis=basis)


# other arguments (#79, F49)
def test_unknown_solving_is_rejected(workdir):
    # used to keep the Generator's default mode and fail later with an AttributeError
    with pytest.raises(ValueError, match="solving can be only"):
        synthesize(solving="SMT")


def test_gate_set_can_be_a_list(workdir):
    res, circuit, _ = synthesize(gate_set=["h", "cx"])
    assert res and circuit.gate_count() == 2


def test_fidelity_threshold_needs_approx(workdir):
    with pytest.raises(ValueError, match="fidelity_threshold applies only with approx"):
        synthesize(fidelity_threshold=0.5)


def test_approx_with_measurement_is_rejected_before_encoding(workdir):
    qasm = workdir / "measured.qasm"
    qasm.write_text("OPENQASM 2.0;\nqreg q[1];\ncreg c[1];\nh q[0];\nmeasure q[0] -> c[0];\n")
    with pytest.raises(NotImplementedError, match="post-measurement is not supported for approximate"):
        synthesize(qasm_file=str(qasm), complex_representation="Classic", approx=True, fidelity_threshold=0.9)


# matrix input in the fixed-depth modes (#79, F51)
@pytest.mark.parametrize("mode", ["basic", "binary", "topdown", "bottomup"])
def test_matrix_needs_d_in_fixed_depth_modes(workdir, mode):
    # a matrix has no gate count, so these modes used to encode 0 layers and fail without saying why
    with pytest.raises(ValueError, match="d is required for a matrix input"):
        synthesize(qasm_file=None, matrix=object(), vectors="custom", input_vectors=[object()], mode=mode)


# custom vector_pairs (#79, F31)
def basis_state(q, index, representation=FiveTuple):
    vector = Vector(q=2**q, element_representation=representation, k=0)
    vector[index] = representation.one(None)
    return vector


def custom(vector_pairs, q=2):
    return synthesize(qasm_file=None, vectors="custom", vector_pairs=vector_pairs, q=q, d=1, gate_set=GateSet(["x"]))


def test_custom_vector_pairs_must_not_be_empty(workdir):
    with pytest.raises(ValueError, match="vector_pairs must not be empty"):
        custom([])


@pytest.mark.parametrize("q", [1, 3])
def test_custom_vectors_must_match_q(workdir, q):
    # 2-qubit states: with q=3 the extra amplitudes were left free, with q=1 an IndexError
    with pytest.raises(ValueError, match=f"q={q} qubit"):
        custom([(basis_state(2, 0), basis_state(2, 1))], q=q)


def test_custom_vectors_must_use_the_synthesis_representation(workdir):
    with pytest.raises(ValueError, match="uses Complex, the synthesis uses FiveTuple"):
        custom([(basis_state(2, 0, Complex), basis_state(2, 1, Complex))])


@pytest.mark.parametrize("solver", ["smtinterpol", "opensmt"])
def test_solver_without_nra_is_rejected_for_classic(workdir, solver):
    with pytest.raises(ValueError, match=f"{solver} does not support QF_NRA"):
        synthesize(solver=solver, complex_representation="Classic")
