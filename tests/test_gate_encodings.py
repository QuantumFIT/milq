"""Every supported gate synthesized from itself, in every backend and representation that can run it in CI.

Each gate has its own encoding in Synthesizer.encode_layer, per representation and per backend
(the MILP backends cannot propagate identities), so this checks all of them against the simulator.
"""

import numpy as np
import pytest

from conftest import unitary
from gates import GateSet, supported_gates
from synth import Synthesizer

GATES = [(gate, arity) for arity, names in enumerate(supported_gates, start=1) for gate in names if gate != "id"]
BACKENDS = [("smt", "yices2"), ("milp", "cbc"), ("gurobi", "gurobi")]


def cases():
    for gate, arity in GATES:
        for solving, solver in BACKENDS:
            for representation in ["FiveTuple", "Classic"]:
                # FiveTuple models of multi-qubit gates are too large for the license shipped with gurobipy
                if solving == "gurobi" and representation == "FiveTuple" and arity > 1:
                    continue
                yield pytest.param(gate, arity, solving, solver, representation,
                                   id=f"{gate}-{solving}-{representation}")


@pytest.mark.parametrize("gate, arity, solving, solver, representation", list(cases()))
def test_single_gate(workdir, gate, arity, solving, solver, representation):
    qubits = ", ".join(f"q[{i}]" for i in range(arity))
    with open("in.qasm", "w") as f:
        f.write(f"OPENQASM 2.0;\nqreg q[{arity}];\n{gate} {qubits};\n")
    res, circuit, _ = Synthesizer().synthesis(qasm_file="in.qasm", vectors="all", solving=solving, solver=solver,
                                              mode="basic", complex_representation=representation,
                                              gate_set=GateSet([gate]), d=1, output_qasm="out.qasm")
    assert res
    # the gate may act on other qubits (e.g. swap q[1], q[0]), so compare unitaries, not gate lists
    assert [g.name for g in circuit.gates] == [gate]
    np.testing.assert_allclose(unitary("out.qasm"), unitary("in.qasm"), atol=1e-9)
