"""MILP/Gurobi solver statuses are mapped to SAT/UNSAT/error correctly (#8)."""

import os

import gurobipy as gp
import numpy as np
import pytest
from gurobipy import GRB
from pulp import GUROBI, PULP_CBC_CMD, LpMinimize, LpProblem, LpSolutionNoSolutionFound, LpStatusNotSolved, LpVariable

from complex.classic import Complex
from complex.vector import Vector
from conftest import BENCHMARKS, unitary
from gates import GateSet
from generator import Generator
from logger import Logger
from synth import Synthesizer


def gurobi_generator(model):
    gen = Generator(mode="gurobi", logger=Logger())
    model.Params.OutputFlag = 0
    gen.lp_problem = model
    return gen


def test_gurobi_infeasible_is_unsat():
    model = gp.Model()
    x = model.addVar(vtype=GRB.BINARY)
    model.addConstr(x >= 2)
    assert gurobi_generator(model).check_sat() is False


def test_gurobi_inf_or_unbd_is_unsat():
    # presolve cannot tell infeasible from unbounded here; MILQ's objectives are bounded
    model = gp.Model()
    x = model.addVar(vtype=GRB.INTEGER)
    y = model.addVar(lb=-GRB.INFINITY)
    model.addConstr(x >= 2)
    model.addConstr(x <= 1)
    model.setObjective(-y, GRB.MINIMIZE)
    gen = gurobi_generator(model)
    assert gen.check_sat() is False
    assert model.Status == GRB.INF_OR_UNBD


def knapsack():
    model = gp.Model()
    xs = model.addVars(30, vtype=GRB.BINARY)
    model.addConstr(gp.quicksum(xs.values()) == 15)
    model.setObjective(gp.quicksum((i % 7 + 1) * xs[i] for i in range(30)), GRB.MAXIMIZE)
    return model, xs


def test_gurobi_limit_without_solution_raises():
    model, _ = knapsack()
    model.Params.TimeLimit = 0
    with pytest.raises(RuntimeError, match="TIME_LIMIT"):
        gurobi_generator(model).check_sat()


def test_gurobi_limit_with_solution_is_sat():
    model, xs = knapsack()
    for i in range(30):
        xs[i].Start = 1 if i < 15 else 0  # feasible but not optimal
    model.Params.SolutionLimit = 1
    gen = gurobi_generator(model)
    assert gen.check_sat() is True
    assert model.Status == GRB.SOLUTION_LIMIT


@pytest.mark.parametrize("make_solver", [lambda: PULP_CBC_CMD(msg=False), lambda: GUROBI(msg=False)], ids=["cbc", "gurobi"])
@pytest.mark.parametrize("feasible", [True, False])
def test_pulp_status(make_solver, feasible):
    gen = Generator(mode="milp", logger=Logger())
    gen.solver = make_solver
    gen.lp_problem = LpProblem("status", LpMinimize)
    x = LpVariable("x", lowBound=0, upBound=1, cat="Integer")
    gen.lp_problem += x
    gen.lp_problem += x >= (1 if feasible else 2)
    assert gen.check_sat() is feasible


def plus_state_pairs():
    # |0> -> |+>, which no single X gate (or identity) produces
    pairs = []
    vin = Vector(q=2, element_representation=Complex, k=0)
    vin[0] = Complex(a=1.0, b=0.0)
    vout = Vector(q=2, element_representation=Complex, k=0)
    vout[0] = Complex(a=float(np.sqrt(0.5)), b=0.0)
    vout[1] = Complex(a=float(np.sqrt(0.5)), b=0.0)
    pairs.append((vin, vout))
    return pairs


@pytest.mark.parametrize("solving, solver", [("gurobi", "gurobi"), ("milp", "gurobi"), ("milp", "cbc")])
def test_unsynthesizable_target_returns_false(workdir, solving, solver):
    res, circuit, _ = Synthesizer().synthesis(vectors="custom", vector_pairs=plus_state_pairs(), q=1, d=1,
                                              gate_set=GateSet(["x"]), solving=solving, solver=solver,
                                              mode="basic", complex_representation="Classic")
    assert res is False
    assert circuit is None


@pytest.mark.parametrize("representation", ["Classic", "FiveTuple"])
def test_cbc_synthesizes_ghz(workdir, representation):
    qasm_file = os.path.join(BENCHMARKS, "ghz/2.qasm")
    res, circuit, _ = Synthesizer().synthesis(qasm_file=qasm_file, vectors="zero", solving="milp", solver="cbc",
                                              mode="incremental", complex_representation=representation,
                                              output_qasm="out.qasm")
    assert res
    assert len([g for g in circuit.gates if g is not None and g.name != "id"]) == 2
    np.testing.assert_allclose(unitary("out.qasm")[:, 0], unitary(qasm_file)[:, 0], atol=1e-9)


def test_gurobi_solving_rejects_other_solver(workdir):
    with pytest.raises(ValueError, match="gurobi"):
        Synthesizer().synthesis(qasm_file=os.path.join(BENCHMARKS, "ghz/2.qasm"), vectors="zero",
                                solving="gurobi", solver="cbc")


def test_gurobi_status_name():
    from generator import _gurobi_status_name
    assert _gurobi_status_name(GRB.TIME_LIMIT) == "TIME_LIMIT"
    assert _gurobi_status_name(12345) == "12345"  # unknown code falls back to the number


class StoppedSolver:
    # stands in for a PuLP solver that stops (e.g. on a limit) before finding any solution
    def actualSolve(self, lp, **kwargs):
        lp.assignStatus(LpStatusNotSolved, LpSolutionNoSolutionFound)
        return LpStatusNotSolved


def test_pulp_without_solution_raises():
    gen = Generator(mode="milp", logger=Logger())
    gen.solver = StoppedSolver
    gen.lp_problem = LpProblem("stopped", LpMinimize)
    x = LpVariable("x", lowBound=0, upBound=1, cat="Integer")
    gen.lp_problem += x
    with pytest.raises(RuntimeError, match="Not Solved"):
        gen.check_sat()
