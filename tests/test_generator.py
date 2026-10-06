"""Encoding-level checks of the generator, without running a synthesis."""

import pytest
from pulp import PULP_CBC_CMD
from pysmt.shortcuts import Solver

from gates import GateSet
from generator import Generator
from logger import Logger


@pytest.mark.parametrize("mode", ["pysmt", "milp", "gurobi"])
@pytest.mark.parametrize("first, second, allowed", [
    ("t_q0", "tdg_q0", False),        # G Gdg is identity
    ("tdg_q0", "t_q0", False),        # Gdg G is identity
    ("t_q0", "t_q0", True),           # T T = S, used to be forbidden
    ("t_q0", "tdg_q1", True),         # different qubit
    ("h_q0", "h_q0", False),          # self-adjoint
    ("cx_q0_q1", "cx_q0_q1", False),  # self-adjoint on the same wires
    ("cx_q0_q1", "cx_q1_q0", True),   # different wire order is a different gate
])
def test_add_constraints_forbids_only_adjoint_pairs(tmp_path, mode, first, second, allowed):
    gen = Generator(mode=mode, logger=Logger(verbosity=0, filename=str(tmp_path / "log")))
    if mode == "pysmt":
        gen.solver = Solver(name="z3")
    elif mode == "milp":
        gen.solver = lambda: PULP_CBC_CMD(msg=False)
    gate_set = GateSet(["h", "t", "tdg", "cx"])
    for layer in (0, 1):
        gen.add_selection_variables(layer, gate_set, 2)
    gen.add_constraints(gate_set, 1, 2)
    # select the two gates
    gen.AtLeastOne(gen.symbols[f"L0_{first}"])
    gen.AtLeastOne(gen.symbols[f"L1_{second}"])
    assert gen.check_sat() == allowed
