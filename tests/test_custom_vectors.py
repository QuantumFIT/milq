"""Synthesis from custom (input, output) state pairs instead of a QASM file."""

import numpy as np
import pytest
from qiskit.circuit.library import SwapGate
from qiskit.quantum_info import Operator

from complex.classic import Complex
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
    res, circuit, _ = Synthesizer().synthesis(vectors="custom", vector_pairs=sqrt_swap_pairs(), q=2, d=1,
                                              gate_set=GateSet(["sqrtswap"]), solving="gurobi", solver="gurobi",
                                              mode=mode, complex_representation="Classic", output_qasm="out.qasm")
    assert res
    assert [gate.name for gate in circuit.gates if gate is not None and gate.name != "id"] == ["sqrtswap"]
