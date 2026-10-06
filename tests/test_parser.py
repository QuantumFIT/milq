"""Parsing of SMT solver models (get-model and get-value responses)."""

import numpy as np
import pytest

from conftest import to_complex
from complex.classic import Complex
from logger import Logger
from parser import ModelParser
from sim import Simulator
from synth import Synthesizer

# responses recorded from the solvers for r1 = -1/2, r2 = -1/3, r3 = 7/2, r4 = 2, b = true
REAL_RESPONSES = {
    "yices2": """sat
((define-fun r1 () Real (/ (- 1) 2))
 (define-fun r2 () Real (/ (- 1) 3))
 (define-fun r3 () Real (/ 7 2))
 (define-fun r4 () Real 2.0)
 (define-fun b () Bool true))
((r1 (/ (- 1) 2))
 (r2 (/ (- 1) 3))
 (r3 (/ 7 2))
 (r4 2.0)
 (b true))
""",
    "cvc5": """sat
(
(define-fun r1 () Real (/ (- 1) 2))
(define-fun r2 () Real (/ (- 1) 3))
(define-fun r3 () Real (/ 7 2))
(define-fun r4 () Real 2.0)
(define-fun b () Bool true)
)
((r1 (/ (- 1) 2)) (r2 (/ (- 1) 3)) (r3 (/ 7 2)) (r4 2.0) (b true))
""",
    "opensmt": """sat
(
  (define-fun r1 () Real
    (/ (- 1) 2))
  (define-fun r2 () Real
    (/ (- 1) 3))
  (define-fun r3 () Real
    (/ 7 2))
  (define-fun r4 () Real
    2)
  (define-fun b () Bool
    true)
)
((r1 (/ (- 1) 2))(r2 (/ (- 1) 3))(r3 (/ 7 2))(r4 2)(b true))
""",
    "z3": """sat
(
  (define-fun r4 () Real
    2.0)
  (define-fun b () Bool
    true)
  (define-fun r1 () Real
    (- (/ 1.0 2.0)))
  (define-fun r3 () Real
    (/ 7.0 2.0))
  (define-fun r2 () Real
    (- (/ 1.0 3.0)))
)
((r1 (- (/ 1.0 2.0)))
 (r2 (- (/ 1.0 3.0)))
 (r3 (/ 7.0 2.0))
 (r4 2.0)
 (b true))
""",
}

# the same for integers r1 = -3, r2 = -7, r3 = 4, r4 = 2 (yices2; cvc5 and OpenSMT print the same terms)
INT_RESPONSE = """sat
((define-fun r1 () Int (- 3))
 (define-fun r2 () Int (- 7))
 (define-fun r3 () Int 4)
 (define-fun r4 () Int 2)
 (define-fun b () Bool true))
((r1 (- 3))
 (r2 (- 7))
 (r3 4)
 (r4 2)
 (b true))
"""


def parse(text):
    return ModelParser(Logger()).parse_model_to_items(text)


@pytest.mark.parametrize("solver", REAL_RESPONSES)
def test_negative_reals(solver):
    items = parse(REAL_RESPONSES[solver])
    expected = {"r1": -0.5, "r2": -1 / 3, "r3": 3.5, "r4": 2.0, "b": True}
    # both the get-model and the get-value response are parsed
    assert len(items) == 10
    for name, value in items:
        assert value == pytest.approx(expected[name])


def test_negative_integers():
    items = parse(INT_RESPONSE)
    assert len(items) == 10
    assert set(items) == {("r1", -3), ("r2", -7), ("r3", 4), ("r4", 2), ("b", True)}
    assert all(isinstance(value, int) for _, value in items)


def test_dreal_intervals_take_lower_bound():
    model = """delta-sat with delta = 0.001
(model
  (define-fun x () Real [-0.5, -0.49])
)
((y (interval (closed (- 1)) (open 2))))
"""
    assert parse(model) == [("x", -0.5), ("y", -1)]


def test_unparsable_terms_are_skipped():
    assert parse("sat\n((define-fun x () Real (root-obj (+ (^ x 2) (- 2)) 2)) (define-fun y () Int 3))") == [("y", 3)]


def test_negative_amplitude_end_to_end(workdir):
    # x; z maps |0> to -|1>, so the parsed output vector must contain -1
    qasm = workdir / "minus_one.qasm"
    qasm.write_text("OPENQASM 2.0;\nqreg q[1];\nx q[0];\nz q[0];\n")
    res, _, vectors = Synthesizer().synthesis(qasm_file=str(qasm), vectors="zero", solving="smt", solver="yices2",
                                              mode="incremental", complex_representation="Classic",
                                              output_qasm="out.qasm")
    assert res
    expected = Simulator(str(qasm), complex_representation=Complex).simulate_zero()[0][1]
    np.testing.assert_allclose([to_complex(e, 0, Complex) for e in vectors[0]],
                               [to_complex(e, 0, Complex) for e in expected], atol=1e-9)
