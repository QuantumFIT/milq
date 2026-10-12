"""Synthesis from custom states: (input, output) pairs, or input states with the outputs simulated from a circuit (#44)."""

import os

import numpy as np
import pytest
from qiskit.circuit.library import SwapGate
from qiskit.quantum_info import Operator

from conftest import BENCHMARKS
from complex.classic import Complex
from complex.fivetuple import FiveTuple
from complex.matrix import Matrix
from complex.vector import Vector
from gates import GateSet
from synth import Synthesizer


def sqrt_swap_pairs():
    # all computational basis states and their images under sqrt(SWAP)
    unitary = Operator(SwapGate().power(0.5)).data
    pairs = []
    for i in range(4):
        inp = Vector(q=4, element_representation=Complex, k=0)
        out = Vector(q=4, element_representation=Complex, k=0)
        inp[i] = Complex(a=1.0, b=0.0)
        for j in range(4):
            out[j] = Complex(a=float(unitary[j, i].real), b=float(unitary[j, i].imag))
        pairs.append((inp, out))
    return pairs


@pytest.mark.parametrize("mode", ["basic", "incremental"])
def test_custom_vectors_sqrt_swap(workdir, mode):
    pairs = sqrt_swap_pairs()
    res, circuit, vectors = Synthesizer().synthesis(vectors="custom", vector_pairs=pairs, q=2, d=1,
                                                    gate_set=GateSet(["sqrtswap"]), solving="gurobi", solver="gurobi",
                                                    mode=mode, complex_representation="Classic", output_qasm="out.qasm")
    assert res
    assert [gate.name for gate in circuit.gates if gate is not None and gate.name != "id"] == ["sqrtswap"]
    # one output vector per pair, equal to the target
    assert len(vectors) == len(pairs)
    for vector, (_, target) in zip(vectors, pairs):
        for j in range(4):
            assert vector[j].real == pytest.approx(target[j].real, abs=1e-6)
            assert vector[j].imag == pytest.approx(target[j].imag, abs=1e-6)


BELL = os.path.join(BENCHMARKS, "ghz/2.qasm")  # h q[0]; cx q[0], q[1];
REPRESENTATIONS = {"FiveTuple": FiveTuple, "Classic": Complex}


def basis_state(index, qubits, representation):
    vector = Vector(q=2**qubits, generator=None, element_representation=representation, k=0)
    vector[index] = representation.one(None)
    return vector


def plus_zero(representation):
    # |0>|+>: q[0] in |+>, q[1] in |0>
    vector = Vector(q=4, generator=None, element_representation=representation, k=1)
    vector[0] = representation.one(None).divide_by_sqrt2(None)
    vector[1] = representation.one(None).divide_by_sqrt2(None)
    return vector


def gates(circuit):
    return [str(gate) for gate in circuit.gates if gate.name != "id"]


@pytest.mark.parametrize("solving, solver, representation", [("smt", "yices2", "FiveTuple"), ("smt", "yices2", "Classic"),
                                                             ("gurobi", "gurobi", "Classic")])
def test_input_vectors_with_a_circuit(workdir, solving, solver, representation):
    # on |0>|+>, h q[0] already gives |00>, so the cx of the Bell circuit is not needed
    res, circuit, vectors = Synthesizer().synthesis(qasm_file=BELL, vectors="custom", input_vectors=[plus_zero(REPRESENTATIONS[representation])],
                                                    solving=solving, solver=solver, complex_representation=representation,
                                                    output_qasm="out.qasm")
    assert res
    assert gates(circuit) == ["h q[0];"]
    assert len(vectors) == 1


def test_input_vectors_take_q_and_gate_set_from_the_circuit(workdir):
    # the same as vectors="zero": the Bell state needs both gates
    synthesizer = Synthesizer()
    res, circuit, _ = synthesizer.synthesis(qasm_file=BELL, vectors="custom", input_vectors=[basis_state(0, 2, FiveTuple)],
                                            solving="smt", solver="yices2", output_qasm="out.qasm")
    assert res
    assert circuit.gate_count() == 2
    assert synthesizer.q == 2
    assert "cx" in synthesizer.gate_set.gates


def test_input_vectors_with_a_matrix(workdir):
    inputs = [basis_state(0, 1, Complex), basis_state(1, 1, Complex)]
    res, circuit, _ = Synthesizer().synthesis(matrix=Matrix.h(), vectors="custom", input_vectors=inputs, solving="smt",
                                              solver="yices2", complex_representation="Classic", d=1, output_qasm="out.qasm")
    assert res
    assert gates(circuit) == ["h q[0];"]
    # the caller's states are not replaced by their images
    assert [inputs[0][0].real, inputs[1][1].real] == [1, 1]


def test_input_vectors_with_end_of_circuit_measurements(workdir):
    # measuring q[0] = 0 after h; cx leaves |00>, which the empty circuit also gives on |00>
    with open("in.qasm", "w") as f:
        f.write("OPENQASM 2.0;\nqreg q[2];\ncreg c[2];\nh q[0];\ncx q[0], q[1];\nmeasure q[0] -> c[0];\n")
    synthesizer = Synthesizer()
    res, circuit, _ = synthesizer.synthesis(qasm_file="in.qasm", vectors="custom", input_vectors=[basis_state(0, 2, Complex)],
                                            solving="smt", solver="yices2", complex_representation="Classic", output_qasm="out.qasm")
    assert res
    assert synthesizer.qubits_to_measure == [0]
    assert circuit.gate_count() == 0


@pytest.mark.parametrize("kwargs, message", [
    (dict(vector_pairs=[]), "give the input states as input_vectors, not vector_pairs"),
    (dict(), "input_vectors are required"),
    (dict(input_vectors=[basis_state(0, 1, FiveTuple)]), "input vector 0 has 2 amplitudes, the circuit acts on 2 qubit"),
    (dict(input_vectors=[basis_state(0, 2, Complex)]), "input vector 0 uses Complex, the synthesis uses FiveTuple"),
])
def test_invalid_input_vectors(workdir, kwargs, message):
    with pytest.raises(ValueError, match=message):
        Synthesizer().synthesis(qasm_file=BELL, vectors="custom", solving="smt", solver="yices2", **kwargs)


@pytest.mark.parametrize("kwargs", [dict(qasm_file=BELL, vectors="all"),
                                    dict(vectors="custom", vector_pairs=sqrt_swap_pairs(), q=2, d=1, gate_set=GateSet(["sqrtswap"]))])
def test_input_vectors_need_custom_vectors_and_a_circuit(workdir, kwargs):
    with pytest.raises(ValueError, match="input_vectors can be provided only with vectors=custom and a qasm_file or matrix"):
        Synthesizer().synthesis(input_vectors=[basis_state(0, 2, FiveTuple)], solving="smt", solver="yices2", **kwargs)


@pytest.mark.parametrize("missing", ["vector_pairs", "q", "d", "gate_set"])
def test_custom_vector_pairs_need_q_d_and_gate_set(workdir, missing):
    kwargs = dict(vector_pairs=sqrt_swap_pairs(), q=2, d=1, gate_set=GateSet(["sqrtswap"]))
    kwargs[missing] = None
    with pytest.raises(ValueError, match="vector_pairs, q, d, and gate_set are required when vectors are custom"):
        Synthesizer().synthesis(vectors="custom", solving="smt", solver="yices2", **kwargs)


def test_matrix_needs_rus_or_custom_vectors(workdir):
    with pytest.raises(ValueError, match="matrix can be provided only for rus and custom mode"):
        Synthesizer().synthesis(matrix=Matrix.h(), vectors="all", solving="smt", solver="yices2", complex_representation="Classic")
