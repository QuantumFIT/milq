"""binary_cost_search terminates and finds the minimal cost (#43)."""

import pytest

from synth import Synthesizer


class FakeGen:
    def __init__(self):
        self.bounds = []

    def push(self): pass
    def pop(self): pass
    def write_formula(self, _): return None
    def Int(self, n): return n
    def LE(self, _, n): return n
    def add_assertion(self, n): self.bounds.append(n)


def search(d, min_cost):
    synth = Synthesizer.__new__(Synthesizer)
    synth.d = d
    synth.gen = FakeGen()
    synth.solve_and_extract_circuit = lambda **_: (
        (True, f"c{synth.gen.bounds[-1]}", None) if synth.gen.bounds[-1] >= min_cost else (False, None, None))
    return synth.binary_cost_search([None] * (d + 1)), synth.gen.bounds


@pytest.mark.parametrize("d", [1, 2, 5])
def test_all_unsat_terminates(d):
    (res, circuit, _), bounds = search(d, min_cost=d + 2)
    assert (res, circuit) == (False, None)
    assert len(bounds) == len(set(bounds))


@pytest.mark.parametrize("d,min_cost", [(1, 0), (1, 2), (5, 0), (5, 3), (5, 6)])
def test_finds_min_cost(d, min_cost):
    (res, circuit, _), bounds = search(d, min_cost)
    assert (res, circuit) == (True, f"c{min_cost}")
    assert len(bounds) == len(set(bounds))
