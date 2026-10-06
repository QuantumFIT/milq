"""Equivalence up to global phase in incremental SMT mode, and scoped declarations (#7)."""

import numpy as np
import pytest

from conftest import unitary
from generator import Generator
from synth import Synthesizer


@pytest.fixture
def minus_identity(workdir):
    # Z X Z X = -I: equal to the empty circuit only up to global phase
    path = workdir / "minus_identity.qasm"
    path.write_text("OPENQASM 2.0;\nqreg q[1];\nz q[0];\nx q[0];\nz q[0];\nx q[0];\n")
    return str(path)


@pytest.mark.parametrize("solver", ["yices2", "cvc5"])
def test_incremental_smt_up_to_global_phase_on_all_basis_states(minus_identity, solver):
    res, circuit, _ = Synthesizer().synthesis(qasm_file=minus_identity, vectors="all", solving="smt", solver=solver,
                                              mode="incremental", complex_representation="FiveTuple",
                                              up_to_global_phase=True, output_qasm="out.qasm")
    assert res
    assert [g for g in circuit.gates if g is not None and g.name != "id"] == []
    synthesized, original = unitary("out.qasm"), unitary(minus_identity)
    phase = synthesized[0, 0] / original[0, 0]
    assert abs(abs(phase) - 1) < 1e-9
    np.testing.assert_allclose(synthesized, phase * original, atol=1e-9)


class RecordingSolver:
    def __init__(self):
        self.commands = []

    def write_incremental(self, statement):
        self.commands.append(statement)


def test_declarations_are_deduplicated_and_scoped():
    gen = Generator(mode="smtlib", logic="QF_LIA")
    gen.solver = RecordingSolver()
    gen.set_incremental_mode()
    gen.declare_bool("outer")
    gen.push()
    gen.declare_bool("inner")
    gen.declare_bool("inner")   # same scope: not declared again
    gen.declare_bool("outer")   # outer scope: still declared
    assert "inner" in gen.symbols and "outer" in gen.symbols
    gen.pop()
    assert "inner" not in gen.declared_names and "outer" in gen.declared_names
    gen.push()
    gen.declare_bool("inner")   # forgotten by the solver on pop: declared again
    declarations = [c for c in gen.solver.commands if c.startswith("(declare-fun")]
    assert declarations == ["(declare-fun outer () Bool)", "(declare-fun inner () Bool)", "(declare-fun inner () Bool)"]
