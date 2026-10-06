"""Incremental synthesis beyond the input circuit's gate count, and the max_depth limit (#5)."""

import numpy as np
import pytest

from conftest import unitary
from gates import GateSet
from synth import Synthesizer

BACKENDS = [
    pytest.param(dict(solving="smt", solver="yices2", complex_representation="FiveTuple"), id="smt-yices2-FiveTuple"),
    pytest.param(dict(solving="gurobi", solver="gurobi", complex_representation="Classic"), id="gurobi-Classic"),
]


@pytest.fixture
def cx_qasm(workdir):
    # a single CX: with only H and CZ available, the optimum (H CZ H) is longer than the input
    path = workdir / "cx.qasm"
    path.write_text("OPENQASM 2.0;\nqreg q[2];\ncx q[0], q[1];\n")
    return str(path)


def synthesize(qasm_file, gates, backend, **kwargs):
    return Synthesizer().synthesis(qasm_file=qasm_file, vectors="all", mode="incremental", gate_set=GateSet(gates),
                                   output_qasm="out.qasm", **backend, **kwargs)


@pytest.mark.parametrize("backend", BACKENDS)
def test_search_continues_beyond_input_gate_count(cx_qasm, backend):
    res, circuit, _ = synthesize(cx_qasm, ["h", "cz"], backend)
    assert res
    assert len([g for g in circuit.gates if g is not None and g.name != "id"]) == 3
    np.testing.assert_allclose(unitary("out.qasm"), unitary(cx_qasm), atol=1e-9)


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("gates, max_depth", [(["h", "cz"], 2), (["cz"], 3)], ids=["optimum-above-limit", "no-solution"])
def test_max_depth_stops_the_search(cx_qasm, backend, gates, max_depth):
    assert synthesize(cx_qasm, gates, backend, max_depth=max_depth) == (False, None, None)


def test_max_depth_must_be_positive(cx_qasm):
    with pytest.raises(ValueError):
        synthesize(cx_qasm, ["h", "cz"], BACKENDS[0].values[0], max_depth=0)
