"""
@file: synth.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: quantum circuit synthesis using SMT and MILP solving
"""

from complex.classic import Complex
from complex.vector import Vector
from complex.fivetuple import FiveTuple
from complex.matrix import Matrix
from generator import Generator, quiet_gurobi_env
from parser import ModelParser
import os
import copy
import tempfile
import subprocess
from sim import Simulator
from pysmt.logics import QF_NRA, QF_LIA, QF_NIA, QF_LRA
from pysmt.shortcuts import Portfolio, Symbol, Real, And, Equals, Plus, GT, LT, get_env, Int, Or, Not, Implies, GE, LE, Ite, Minus, Div, Times, write_smtlib, Solver
from pysmt.typing import REAL, INT
from pareto import Pareto
from gates import GateSet, check_supported, Circuit, k_increments, max_k_increment
from pulp import *
from gurobipy import GRB
from solvers import PortfolioSMTSolver, SMTSolver, SolverError
from solver_config import LOGICS, SolverConfigError, config_path, load_solver_config
import time
import logging
from timing import run, timed, times
import numpy as np

log = logging.getLogger(__name__)

def integral_k(k):
    # a FiveTuple vector is divided by sqrt(2)^k, k has to be an integer (4.0 is accepted)
    if k is None or int(k) != k:
        raise ValueError(f"k of a FiveTuple vector must be an integer, got {k!r}")
    return int(k)

def rus_recovery_pairs(output_vectors, vector_pairs, measured_qubits):
    # (input, output) pairs for the RUS recovery operation: it maps the state after a failed
    # attempt (measured qubits projected to 1) back to the original input state
    pairs = []
    for pair_idx, state in enumerate(output_vectors):
        measured_state = state.measure(measured_qubits, 1)
        input_state = vector_pairs[pair_idx][0]
        pairs.append((measured_state.to_precision(1e-8), input_state.to_precision(1e-8)))
    return pairs

class Synthesizer:
    def __init__(self) -> None:
        self.gen = Generator()
        self.parser = ModelParser()
        self.gate_set = GateSet()
        self.simulator = None
        self.complex_representation = None
        self.solver = None
        self.fidelity_threshold = 1.0
        self.bound = 1
        self.k_bound = (0, 1)
        self.layer_bigM = 1
        self.q = None  # qubits of the encoded states
        self.circuit_q = None  # qubits the synthesized circuit acts on, the first circuit_q of the q
        self.d = None
        self.max_k = 0
        self.pair_k = []
        self.k_increment = 0
        self.encoding_method = None
        self.curr_depth = 0
        self.v = 0
        self.vec_mode = None
        self.pareto_front = None
        self.pareto_timeout = 10*60*60
        self.up_to_global_phase = False
        self.targets = 1
        self.ancillas = 0
        self.vector_mode = None
        self.solvers = {}
        self.solver_config = {}
        self.qubits_to_measure = None
        self.post_measurement = False
        # written to the synthesized circuit: (qubit, classical bit) and the classical declarations of the input
        self.output_measurements = []
        self.classical_declarations = []
        self.approx = False
        self.max_depth = None
        self.basis = "cb"
        self.ref_dot = None
        # seconds per phase of this synthesizer's last synthesis() run
        self.times = {}
        
    def __enter__(self) -> "Synthesizer":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def close(self) -> None:
        # stops the solver processes of the last synthesis; synthesis() calls it too when it ends, however it ends
        solver = self.gen.solver
        if isinstance(solver, (SMTSolver, PortfolioSMTSolver)):
            solver.close()
        elif self.gen.mode == "pysmt" and hasattr(solver, "exit"):  # pySMT's Solver or Portfolio
            solver.exit()
            
    def _load_solver_config(self, solver: str, path: str | None) -> None:
        self.solver_config = load_solver_config(path)
        if solver not in [*self.solver_config, "portfolio"]:
            raise SolverConfigError(f"Invalid solver: {solver}; {config_path(path)} configures "
                                    f"{', '.join(self.solver_config)} (or use portfolio)")

    def add_solvers(self, incremental_mode : bool = False) -> None:
        # register the solvers from the solver configuration (solvers.toml)
        if self.gen.mode == "pysmt":
            logics = {"QF_LIA": QF_LIA, "QF_LRA": QF_LRA, "QF_NIA": QF_NIA, "QF_NRA": QF_NRA}
        else:
            logics = {logic: logic for logic in LOGICS}
        for name, config in self.solver_config.items():
            # pySMT drives its generic solvers through stdin by itself
            args = config.command(incremental_mode and self.gen.mode != "pysmt")
            self.add_one_solver(name=name, args=args, logics=[logics[logic] for logic in config.logics],
                                incremental_mode=incremental_mode)
    
    def add_one_solver(self, name: str, args: list[str], logics: list[str], smtlib_flags: list[str] = [], incremental_mode: bool = False) -> None:
        if name == "z3" and self.gen.mode == "pysmt": 
            return
        if self.gen.mode == "pysmt":
            factory = get_env().factory
            # pySMT keeps solvers registered for the whole process, e.g. by an earlier synthesis
            if factory.is_generic_solver(name):
                if factory.get_generic_solver_info(name) != (args, logics):
                    raise SolverConfigError(f"pySMT already has a solver {name} with another command or logics; "
                                            "use one solver configuration per process")
                return
            factory.add_generic_solver(name=name, args=args, logics=logics)
        else:
            self.solvers[name] = SMTSolver(name, args, logics, smtlib_flags, incremental_mode)

    def encode_layer(self, inp : Vector, out : Vector, layer : int, inp_weight : any = None, out_weight : any = None, selection_variables : list = None, bool_variables : list = None) -> None:
        updates_k_value = []        
        def add_k_eq(sel, out_k, inp_k):
            if self.gen.mode == "milp" or self.gen.mode == "gurobi":
                return
            k_eq = self.gen.Equals(out_k, inp_k)
            self.gen.add_assertion(self.gen.Implies(sel, k_eq))
        
        def add_k_incr(sel, out_k, inp_k, increment):
            if self.gen.mode == "milp" or self.gen.mode == "gurobi":
                updates_k_value.append((sel, self.gen.Int(increment)))
                return
            k_incr = self.gen.Equals(out_k, self.gen.Plus(inp_k, self.gen.Int(increment)))
            self.gen.add_assertion(self.gen.Implies(sel, k_incr))

        if not check_supported(self.gate_set):
            raise ValueError("gate set contains an unsupported gate")
    
        size = 2**self.q
        propagate_identities = []
        cannot_propagate = self.gen.mode == "milp" or self.gen.mode == "gurobi"
        # list of lists (for each index), each list contains pairs of (bool_var, operation)
        saved_operations = []
        for pos in range(size):
            propagate_identities.append([])
            saved_operations.append([])

        for selection_variable in selection_variables:
            bool_var = selection_variable[0]
            rest = selection_variable[1]
            gate = rest[0]
            if len(rest) == 2: # single qubit
                q = rest[1]
                if gate == 'id':
                    if cannot_propagate:
                        for pos in range(size):
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'h':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        saved_operations[pos].append((bool_var, ((inp[pos] + inp[other]).divide_by_sqrt2(self.gen))))
                        saved_operations[other].append((bool_var, ((inp[pos] + (inp[other].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen))))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple:
                        add_k_incr(bool_var, out.k, inp.k, k_increments[gate])
                elif gate == 's':
                    for pos in range(size):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sdg':
                    for pos in range(size):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 't':
                    for pos in range(size):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_omega(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'tdg':
                    for pos in range(size):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_omega_counter(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'x':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        saved_operations[pos].append((bool_var, inp[other]))
                        saved_operations[other].append((bool_var, inp[pos]))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sx':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        saved_operations[pos].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))))
                        saved_operations[other].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple:
                        add_k_incr(bool_var, out.k, inp.k, k_increments[gate])
                elif gate == 'sxdg':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        saved_operations[pos].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))))
                        saved_operations[other].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple:
                        add_k_incr(bool_var, out.k, inp.k, k_increments[gate])
                elif gate == 'y':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        other = pos ^ (1 << q)
                        modified_positions.append(other)
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            saved_operations[pos].append((bool_var, inp[other].multiply_by_i(self.gen)))
                            saved_operations[other].append((bool_var, inp[pos].multiply_by_minus_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        else:
                            saved_operations[pos].append((bool_var, inp[other].multiply_by_minus_i(self.gen)))
                            saved_operations[other].append((bool_var, inp[pos].multiply_by_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'z':
                    for pos in range(size):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_one(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
            elif len(rest) == 3: # two qubit
                q1 = rest[1]
                q2 = rest[2]
                if gate == 'cx':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, inp[other]))
                            saved_operations[other].append((bool_var, inp[pos]))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'xcx':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if not control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, inp[other]))
                            saved_operations[other].append((bool_var, inp[pos]))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'dcx':
                    for pos in range(size):
                        # dcx = cx(q1, q2) cx(q2, q1) permutes |a, b> -> |b, a xor b> (a 3-cycle)
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        image = (pos & ~((1 << q1) | (1 << q2))) | (target_flag << q1) | ((control_flag ^ target_flag) << q2)
                        if image == pos and not cannot_propagate: continue
                        saved_operations[image].append((bool_var, inp[pos]))
                        propagate_identities[image].append(bool_var)
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'ch':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, (inp[pos] + inp[other]).divide_by_sqrt2(self.gen)))
                            saved_operations[other].append((bool_var, (inp[pos] + (inp[other].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen)))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.complex_representation == FiveTuple:
                            # k increases by 1 for the whole vector, compensate the untouched amplitudes
                            saved_operations[pos].append((bool_var, inp[pos].increase_k(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_incr(bool_var, out.k, inp.k, k_increments[gate])
                elif gate == 'csx':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))))
                            saved_operations[other].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.complex_representation == FiveTuple:
                            # k increases by 2 for the whole vector, compensate the untouched amplitudes
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_two(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_incr(bool_var, out.k, inp.k, k_increments[gate])
                elif gate == 'cy':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            if control_flag and not target_flag:
                                saved_operations[pos].append((bool_var, inp[other].multiply_by_minus_i(self.gen)))
                                saved_operations[other].append((bool_var, inp[pos].multiply_by_i(self.gen)))
                                propagate_identities[pos].append(bool_var)
                                propagate_identities[other].append(bool_var)
                            else:
                                saved_operations[pos].append((bool_var, inp[other].multiply_by_i(self.gen)))
                                saved_operations[other].append((bool_var, inp[pos].multiply_by_minus_i(self.gen)))
                                propagate_identities[pos].append(bool_var)
                                propagate_identities[other].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                        
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cz':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_one(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cs':
                    for pos in range(size):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'csdg':
                    for pos in range(size):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'swap':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        if q1_flag != q2_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, inp[other]))
                            saved_operations[other].append((bool_var, inp[pos]))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'iswap':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        if q1_flag != q2_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, inp[other].multiply_by_i(self.gen)))
                            saved_operations[other].append((bool_var, inp[pos].multiply_by_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sqrtswap':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        if q1_flag != q2_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))))
                            saved_operations[other].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.complex_representation == FiveTuple:
                            # k increases by 2 for the whole vector, compensate the untouched amplitudes
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_two(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_incr(bool_var, out.k, inp.k, k_increments[gate])
            elif len(rest) == 4: # three qubit
                q1 = rest[1]
                q2 = rest[2]
                q3 = rest[3]
                if gate == 'ccx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        if q1_flag and q2_flag:
                            other = pos ^ (1 << q3)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, inp[other]))
                            saved_operations[other].append((bool_var, inp[pos]))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cswap':
                    modified_positions = []
                    for pos in range(size):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        q3_flag = (pos >> q3) & 1
                        if q1_flag and (q2_flag != q3_flag):
                            other = pos ^ ((1 << q2) | (1 << q3))
                            modified_positions.append(other)
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            saved_operations[pos].append((bool_var, inp[other]))
                            saved_operations[other].append((bool_var, inp[pos]))
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'ccz':
                    for pos in range(size):
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        q3_flag = (pos >> q3) & 1
                        if q1_flag and q2_flag and q3_flag:
                            saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_one(self.gen)))
                            propagate_identities[pos].append(bool_var)
                        elif cannot_propagate:
                            saved_operations[pos].append((bool_var, inp[pos]))
                    if self.complex_representation == FiveTuple:
                        add_k_eq(bool_var, out.k, inp.k)
        # propagate identities for positions that were not modified by the chosen gate
        # (notG1 and notG2 and ...) -> (out[pos] == inp[pos])
        for pos in range(size):
            if cannot_propagate: # pure milp does not support propagation
                break
            if len(propagate_identities[pos]) == 0: # no gates modified this position, propagate identity
                expr = out[pos] == inp[pos]
                self.gen.add_assertion(expr)
            else:
                and_expr = self.gen.LAnd(*[self.gen.Not(v) for v in propagate_identities[pos]])
                if self.gen.mode == "gurobi":
                    bool_indicator = self.gen.declare_bool(f"bool_indicator_{self.gen.stats['bools']}")
                    self.gen.add_assertion(self.gen.Equals(bool_indicator, and_expr))
                else:
                    bool_indicator = and_expr
                for coeff in range(len(out[pos])):
                    self.gen.add_assertion(self.gen.Implies(bool_indicator, self.gen.Equals(out[pos][coeff], inp[pos][coeff])))
                
        #for pos in range(size):
        #    if self.gen.mode == "gurobi":
        #        if len(saved_operations[pos]) == 0:
        #            continue
        #        for i in range(len(out[pos])):
        #            # linearize out[pos][i] = Sum (bool_var * operation[i])
        #            # take only those whose bool var is not in propagate_identities[pos]
        #            terms = [self.gen.Times(bool_var, operation[i]) for bool_var, operation in saved_operations[pos]]
        #            self.gen.add_assertion(out[pos][i] == self.gen.Sum(terms))
        #    else:
        #        for bool_var, operation in saved_operations[pos]:
        #            self.gen.ConstrainedEquals(bool_var, out[pos], operation, self.layer_bigM)
        for pos in range(size):
            for bool_var, operation in saved_operations[pos]:
                self.gen.ConstrainedEquals(bool_var, out[pos], operation, self.layer_bigM)
            
        # propagate the k update
        if (self.gen.mode == "milp" or self.gen.mode == "gurobi") and self.complex_representation != Complex:
            self.gen.add_assertion(self.gen.Equals(out.k, self.gen.Plus(inp.k, self.gen.Sum([v[1] * v[0] for v in updates_k_value]))))

        # add gate weights
        if inp_weight is None or out_weight is None:
            return
        
        for selection_variable in selection_variables:
            if self.gen.mode == "milp" or self.gen.mode == "gurobi": # rather than implications, add it directly as a sum
                break
            bool_var = selection_variable[0]
            gate = selection_variable[1][0]
            weight = self.gate_set.get_weight(gate)
            self.gen.add_assertion(self.gen.Implies(bool_var, self.gen.Equals(out_weight, self.gen.Plus(inp_weight, self.gen.Int(weight)))))
        
        if self.gen.mode == "milp" or self.gen.mode == "gurobi":
            self.gen.add_assertion(self.gen.Equals(out_weight, self.gen.Plus(inp_weight, self.gen.Sum([self.gate_set.get_weight(v[1][0]) * v[0] for v in selection_variables]))))

    def encode_equivalence(self, vectors1, vectors2, depth, already_measured : bool = False):
        if self.approx:
            # APPROXIMATE EQUIVALENCE
            # average gate fidelity (synthesis() rejects milp and post-measurement)
            fidelity_upper_bound = 1.1 # 1.0 was problematic since fidelity could be 1.00002 etc
            fidelity = self.gen.declare_real(f"fidelity", lb=0.0, ub=fidelity_upper_bound)
            d2 = len(vectors1) ** 2
            bound = 1.0 if self.complex_representation == Complex else 2**self.max_k
            dotsum = self.complex_representation(name=f"sum_dots", generator=self.gen, bound=bound)
            dots_abs2 = self.complex_representation(name=f"dots_abs2", generator=self.gen, bound=bound)
            dot_products = []
            k = None
            for pair_idx in range(len(vectors1)):
                vec1 = vectors1[pair_idx][depth]
                vec2 = vectors2[pair_idx]
                dot_product, k = Vector.dot(vec1, vec2)
                dot_products.append(dot_product)
            sum_dots = dot_products[0]
            for i in range(1, len(dot_products)):
                sum_dots = self.gen.Plus(sum_dots, dot_products[i])
            self.gen.add_assertion(self.gen.Equals(dotsum, sum_dots))
            
            self.gen.add_assertion(self.gen.Equals(dots_abs2, self.gen.Times(dotsum, dotsum.conjugate(self.gen))))
            if self.complex_representation == Complex:
                self.gen.add_assertion(self.gen.Equals(fidelity, dots_abs2.divide_by_real(d2).real))
            elif self.complex_representation == FiveTuple:
                # fivetuple branch
                two_to_len_vectors = int(np.log2(len(vectors1)))
                max_k = self.max_k*2 + 4 * two_to_len_vectors
                k = self.gen.Plus(self.gen.Times(k, self.gen.Int(2)), self.gen.Int(4*two_to_len_vectors))
                self.gen.add_assertion(self.gen.Equals(fidelity, dots_abs2.to_real(k, max_k=max_k).real))
                
            self.gen.add_assertion(self.gen.GE(fidelity, self.gen.Real(0)))
            self.gen.add_assertion(self.gen.LE(fidelity, self.gen.Real(fidelity_upper_bound)))
            self.gen.add_assertion(self.gen.GE(fidelity, self.gen.Real(self.fidelity_threshold)))
    
        else:
            # EXACT EQUIVALENCE
            for pair_idx in range(len(vectors1)):
                vec1 = vectors1[pair_idx][depth]
                vec2 = vectors2[pair_idx]
                if self.complex_representation == Complex:
                    norm = None
                    global_phase = None
                    # post measurement (real non-zero norm)
                    if self.post_measurement:
                        if not already_measured:
                            vec1 = vec1.measure(self.qubits_to_measure, 0)
                        norm = self.gen.declare_real(f"norm_{pair_idx}", lb=0.0, ub=1.0)
                        self.gen.add_norm(norm, vec1)
                        measured_vec = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Divided_by_norm_{vec1.name}", bound=1.0)
                        for i in range(2**self.q):
                            self.gen.add_assertion(self.gen.Equals(measured_vec[i], vec1[i].divide_by_real(norm)))
                        vec1 = measured_vec
                    # global phase
                    vec_target = vec2
                    if self.up_to_global_phase:
                        if self.gen.mode == "milp":
                            raise NotImplementedError("global phase encoding not supported for milp mode (non-linearity)")
                        vec = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Multiplied_by_global_phase_{vec2.name}", bound=1.0)
                        global_phase = self.complex_representation(name=f"global_phase", generator=self.gen, bound=1.0)
                        self.gen.add_global_phase(global_phase)
                        for i in range(2**self.q):
                            self.gen.add_assertion(self.gen.Equals(vec[i], self.gen.Times(vec_target[i], global_phase)))
                        vec_target = vec
                        
                    if self.gen.mode == "milp" or self.gen.mode == "gurobi":
                        for i in range(2**self.q):
                            self.gen.add_assertion(self.gen.Equals(vec1[i], vec_target[i]))
                    else:
                        eps = self.gen.Real(1e-9)
                        for i in range(2**self.q):
                            for j in range(len(vec1[i])):
                                self.gen.add_assertion(self.gen.LE(self.gen.Minus(vec1[i][j], vec_target[i][j]), eps))
                                self.gen.add_assertion(self.gen.LE(self.gen.Minus(vec_target[i][j], vec1[i][j]), eps))
                else:
                    # not allowed for integer arithmetics
                    if self.post_measurement:
                        raise ValueError("post-measurement only supported for classic a+bj representation")
                    
                    vec_target = vec2
                    # global phase encoding
                    if self.up_to_global_phase:
                        # change vec2 to vec2 * e, global phase is only omega^m, m in {0, ... 7} -- phase shift 
                        # only for Clifford+T circuits
                        selectors = []
                        for i in range(8):
                            selectors.append(self.gen.declare_bool(f"global_phase_sel_{i}"))
                        self.gen.ExactlyOne(*selectors)
                        vec = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Multiplied_by_global_phase_{vec2.name}", bound=vec2.bound)
                        vec_copy = vec2.copy()
                        for i in range(8):
                            # add selection shift
                            for j in range(len(vec2)):
                                if self.gen.mode == "milp":
                                    bigM = self.layer_bigM
                                    self.complex_representation.constrained_equals(selectors[i], self.layer_bigM, vec[j], vec_copy[j])
                                else:
                                    for k in range(len(vec2[j])):
                                        self.gen.add_assertion(self.gen.Implies(selectors[i], self.gen.Equals(vec[j][k], vec_copy[j][k])))
                            # then shift for next iteration
                            for j in range(len(vec2)):
                                vec_copy[j] = vec_copy[j].multiply_by_omega(self.gen)
                        self.gen.add_assertion(self.gen.Equals(vec.k, vec_copy.k))
                        vec_target = vec

                    # fivetuple rescaling
                    # after `depth` layers, k lies in [k_in, k_in + self.k_increment*depth], which bounds |k - k_target|
                    # (self.max_k is fixed from the input and too small past its depth)
                    k_in, k_target = self.pair_k[pair_idx]
                    max_gap = max(k_in + self.k_increment * depth - k_target, k_target - k_in)
                    # the rescaling multiplies by at most 2^(max_gap // 2), and an odd gap adds two components
                    value_bound = max(vec1.bound, vec_target.bound)
                    rescaled_bound = 2 * value_bound * 2**(max_gap // 2)
                    rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{vec1.name}", bound=rescaled_bound)
                    # vec2 is the target, the same at every depth: without the depth in the name, MILP would get back the
                    # first depth's PuLP variables, with that depth's (smallest) bound
                    rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{vec2.name}_{depth}", bound=rescaled_bound)
                    if self.gen.mode == "milp" or self.gen.mode == "gurobi":
                        self.gen.add_milp_rescaling(rescaled1, rescaled2, vec1, vec_target, pair_idx, max_gap, value_bound + rescaled_bound)
                    else:
                        self.gen.add_rescaling(rescaled1, rescaled2, vec1, vec_target, pair_idx, max_gap // 2 + 1)
                    for i in range(2**self.q):
                        self.gen.add_assertion(self.gen.Equals(rescaled1[i], rescaled2[i]))
                    
    def rus_cost(self, circuit, recovery_circuit, vectors) -> tuple[int, float]:
        # x is the T count of the circuit and its recovery (None: no recovery needed), y the probability
        # of success, i.e. of measuring every measured qubit to 0 (for the first input state)
        vector = vectors[0]
        probabilities = [e.abs2() if vector.element_representation == Complex else e.abs2(vector.k) for e in vector.vec]
        success = sum(p for i, p in enumerate(probabilities) if not any(i >> q & 1 for q in self.qubits_to_measure))
        prob_success = float(success / sum(probabilities))
        recovery_cost = recovery_circuit.cost if recovery_circuit is not None else 0
        log.info("RUS circuit T count: %s, recovery T count: %s, probability of success: %s", circuit.cost, recovery_cost, prob_success)
        return circuit.cost + recovery_cost, prob_success
        
    def circuit_cost(self, circuit) -> tuple[int, int]:
        # x is the number of gates, y the cost given by the gate weights (e.g. the T-count with T-optimal weights)
        return circuit.gate_count(), circuit.get_cost()

    def set_initial_values(self):
        for i, (gate, qubits) in enumerate(self.simulator.stats['input_circuit']):
            bool_var_str = f"L{i}_{gate}"
            for qubit in qubits:
                bool_var_str += f"_q{qubit}"
            bool_var = self.gen.declare_bool(bool_var_str)
            bool_var.setInitialValue(1)
    
    @run()
    def synthesis(self, qasm_file=None, matrix=None, vectors=None, vector_pairs=None, solving="gurobi", solver=None, mode="incremental", output_qasm=None, 
                complex_representation="FiveTuple", gate_set=None, q=None, d=None, fidelity_threshold=1.0, targets=1, ancillas=1, 
                up_to_global_phase=False, basis="cb", approx=False, no_measurement=False, max_depth=None, pareto_timeout=10*60*60,
                input_vectors=None, solver_config=None) -> tuple[bool, Circuit, list[Vector]]:
        """
            qasm_file -> file to synthesize
            vectors -> specify what set of input vectors to use (zero -> only |0>^n state, all -> all cbs, rus -> |0>, |1>, |+> on target, |0> on ancillas,
                       custom -> input_vectors with qasm_file or matrix, or else vector_pairs, q, d, gate_set)
            vector_pairs -> list of pairs (input_vector, output_vector) for input and its expected output.
            input_vectors -> with vectors=custom and a qasm_file or matrix: the input states; the expected outputs are simulated from the circuit
            solving -> smt, pysmt, milp (these need a solver) or gurobi
            solver -> specify specific solver or portfolio of solvers
            solver_config -> SMT solver configuration file (default: $MILQ_SOLVER_CONFIG, else solvers.toml in the repository root)
            mode -> specify solving method (basic -> create whole formula and get the best model, incremental -> incrementally generate the formula, binary, topdown, bottomup -> searches to optimize cost function)
            output_qasm -> file to write the output circuit to (and the last formula, with .smt2 or .lp); None writes no files
            complex_representation -> specify the complex representation ["FiveTuple", "Classic"]
            gate_set -> specify the gate set to use using the GateSet class, otherwise, the gate set is taken from the input qasm file
            q -> number of qubits of the output circuit (has to correspond to the vector_pairs size)
            d -> number of allowed gates in the output circuit
            fidelity_threshold -> with approx: the minimum average fidelity in [0.0, 1.0]
            targets -> number of target qubits (used for RUS -- targets are always the lowest indices)
            ancillas -> number of ancilla qubits (used for RUS -- ancillas are always the highest indices)
            up_to_global_phase -> if True, the synthesis will be done up to global phase (if the mode supports it)
            basis -> basis of the encoding, only "cb" (the computational basis: states are vectors)
            approx -> if True, the synthesis will be done approximately (if the mode supports it)
            no_measurement -> if True, the output qubits will not be measured (ignores end-of-circuit measurement in the input circuit)
            max_depth -> incremental modes only: give up (return False) when no circuit with at most max_depth gates exists; None = no limit
            pareto_timeout -> overall time limit in seconds for mode=pareto-incremental
        """
        start_time = time.perf_counter()
        # empty, unless this run is nested in another one in this process
        times_before = dict(times)
        if vectors is None:
            raise ValueError("provide vectors to select vector-mode")
        if vectors not in ["zero", "all", "rus", "jamiolkowski", "custom"]:
            raise ValueError("vectors can be only zero, all, rus, jamiolkowski, or custom")
        if vectors in ["zero", "all", "rus", "jamiolkowski"] and vector_pairs is not None:
            raise ValueError("vector_pairs cannot be provided when vectors are specified")
        from_circuit = qasm_file is not None or matrix is not None
        if vectors == "custom" and from_circuit:
            # the outputs are simulated from the circuit, so only the inputs are given
            if vector_pairs is not None:
                raise ValueError("with a qasm_file or matrix, give the input states as input_vectors, not vector_pairs")
            if not input_vectors:
                raise ValueError("input_vectors are required when vectors are custom and a qasm_file or matrix is given")
        elif vectors == "custom" and (vector_pairs is None or q is None or d is None or gate_set is None):
            raise ValueError("vector_pairs, q, d, and gate_set are required when vectors are custom")
        if input_vectors is not None and not (vectors == "custom" and from_circuit):
            raise ValueError("input_vectors can be provided only with vectors=custom and a qasm_file or matrix")
        if qasm_file is None and matrix is None and vector_pairs is None:
            raise ValueError("input qasm_file, matrix, or vector_pairs is required")
        if qasm_file is not None and matrix is not None:
            raise ValueError("qasm_file and matrix cannot be provided at the same time")
        
        if matrix is not None and vectors not in ["rus", "custom"]:
            raise ValueError("matrix can be provided only for rus and custom mode")
        if matrix is not None and d is None and mode not in ["incremental", "pareto-incremental"]:
            # the fixed-depth modes take d from the input's gate count, and a matrix has none
            raise ValueError("d is required for a matrix input in basic, binary, topdown and bottomup mode")
        if solving not in ["smt", "pysmt", "milp", "gurobi"]:
            raise ValueError("solving can be only smt, pysmt, milp, or gurobi")
        if solving in ["smt", "milp", "pysmt"] and solver is None:
            raise ValueError("a solver is required for basic smt and milp solving")
        if mode not in ["basic", "incremental", "binary", "topdown", "bottomup", "pareto-incremental"]:
            raise ValueError("mode can be only basic, incremental, binary, topdown, bottomup, or pareto-incremental")
        if complex_representation not in ["FiveTuple", "Classic"]:
            raise ValueError("complex_representation can be only FiveTuple or Classic")
        if complex_representation == "FiveTuple":
            self.complex_representation = FiveTuple
        elif complex_representation == "Classic":
            self.gen.logic = "QF_NRA"
            self.complex_representation = Complex
        if complex_representation == "FiveTuple" and approx:
            self.gen.logic = "QF_NRA"
        if basis != "cb":
            raise ValueError("basis can be only cb (the computational basis)")
        if fidelity_threshold > 1.0 or fidelity_threshold < 0.0:
            raise ValueError("fidelity_threshold must be in [0.0, 1.0]")
        if fidelity_threshold != 1.0 and not approx:
            raise ValueError("fidelity_threshold applies only with approx=True")
        if approx and solving == "milp":
            raise NotImplementedError("approximate equivalence not supported for milp mode (non-linear)")
        if gate_set is not None and not isinstance(gate_set, GateSet):
            gate_set = GateSet(gate_set)  # a list of gate names
        if max_depth is not None and max_depth < 0:
            raise ValueError("max_depth cannot be negative")

        self.vec_mode = vectors
        self.q = q
        self.d = d
        self.up_to_global_phase = up_to_global_phase
        self.encoding_method = mode
        self.vector_mode = vectors
        self.targets = targets
        self.ancillas = ancillas
        self.basis = basis
        self.approx = approx
        self.fidelity_threshold = fidelity_threshold
        self.max_depth = max_depth
        self.pareto_timeout = pareto_timeout

        if vectors in ["zero", "all", "rus", "jamiolkowski"] or (vectors == "custom" and from_circuit):
            # set circuit statistics to prepare synthesis
            self.simulator = Simulator(qasm_file, matrix, complex_representation=self.complex_representation, basis=basis, no_measurement=no_measurement)
            # a copy: the encoding adds id, and the caller's gate set stays as it is
            self.gate_set = copy.deepcopy(gate_set)
            if vectors == "zero":
                vector_pairs = self.simulator.simulate_zero()
            elif vectors == "all":
                vector_pairs = self.simulator.simulate_circuit()
            elif vectors == "rus":
                # simulate based on number of ancilas and targets!
                vector_pairs = self.simulator.simulate_rus(targets, ancillas)
            elif vectors == "jamiolkowski":
                vector_pairs = self.simulator.simulate_jamiolkowski()
            else:  # custom, with a circuit
                vector_pairs = self.simulator.simulate_custom(input_vectors)
            
            stats = self.simulator.circuit_stats()
            if self.gate_set is None:
                # the input's gates and Clifford+T; for RUS, the cost is the T-count. A given gate set is used as it is
                self.gate_set = GateSet.union(stats['gate_set'], GateSet(preset="Clifford+T"))
                if vectors == "rus":
                    self.gate_set.set_t_optimal()
            if self.q is None:
                self.q = stats['q']
            if self.d is None:
                self.d = stats['d']
            if self.qubits_to_measure is None:
                self.qubits_to_measure = stats['measured_qubits']
                self.post_measurement = len(self.qubits_to_measure) > 0
                # with -nm, the input's measurements are not simulated and not written either
                if self.post_measurement:
                    self.output_measurements = stats['measurements']
                    self.classical_declarations = stats['classical_declarations']
            self.max_k = 2*self.d if self.d > stats['max_k'] else 2*stats['max_k']
        else:
            # nothing simulated these pairs, so check them as simulate_custom checks its input states
            if not vector_pairs:
                raise ValueError("vector_pairs must not be empty")
            for i, pair in enumerate(vector_pairs):
                for vector in pair:
                    if len(vector) != 2**q:
                        raise ValueError(f"vector pair {i} has a vector of {len(vector)} amplitudes, q={q} qubit(s) need {2**q}")
                    if vector.element_representation != self.complex_representation:
                        raise ValueError(f"vector pair {i} uses {vector.element_representation.__name__}, "
                                         f"the synthesis uses {self.complex_representation.__name__}")
            self.q = q
            self.d = d
            self.max_k = 2*self.d
            self.gate_set = copy.deepcopy(gate_set)
            self.qubits_to_measure = []
        # the identity lets a layer stay empty, in every mode; pareto-incremental leaves it out of its layers
        # (add_selection_variables, include_identity=False). A weight given for it is kept
        if "id" not in self.gate_set:
            self.gate_set.add_gate("id", weight=0, qubits=1)
        self.circuit_q = self.q // 2 if vectors == "jamiolkowski" else self.q
        self.v = len(vector_pairs)
        if self.complex_representation != Complex:
            for state in (state for pair in vector_pairs for state in pair):
                state.k = integral_k(state.k)
        self.curr_depth = self.d
        max = 0
        for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
            tmp = input_vector.max_value()
            if tmp > max:
                max = tmp
        self.bound = max
        if len(self.qubits_to_measure) > 0 and self.complex_representation != Complex:
            raise ValueError("end circuit qubit measurement is only supported for a+bj complex representation")
        if len(self.qubits_to_measure) > 0 and approx:
            raise NotImplementedError("post-measurement is not supported for approximate equivalence")
        
        incremental_mode = False
        # set generator mode and solver
        if solving == "smt":
            self._load_solver_config(solver, solver_config)
            self.gen.mode = "smtlib"
            incremental_mode = True if (mode == "incremental" or mode == "pareto-incremental") and solver != "portfolio" else False
            self.add_solvers(incremental_mode=incremental_mode)

            new_dict = {}
            for name, s in self.solvers.items():
                if self.gen.logic in s.logics and self.solver_config[name].portfolio:
                    new_dict[name] = s
            if solver == "portfolio":
                if not new_dict:
                    raise SolverConfigError(f"{config_path(solver_config)}: no portfolio solver supports {self.gen.logic}")
                self.gen.solver = PortfolioSMTSolver(new_dict, logic=self.gen.logic)
            else:
                if self.gen.logic not in self.solvers[solver].logics:
                    raise SolverConfigError(f"{solver} does not support {self.gen.logic} (logics in {config_path(solver_config)}: "
                                            f"{', '.join(self.solvers[solver].logics)})")
                self.gen.solver = self.solvers[solver]

        elif solving == "pysmt":
            self._load_solver_config(solver, solver_config)
            self.gen.mode = "pysmt"
            incremental_mode = True if mode == "incremental" or mode == "pareto-incremental" else False
            self.add_solvers(incremental_mode=incremental_mode)
            if solver == "portfolio":
                if self.gen.logic != "QF_NRA":
                    solvers = ["z3", "cvc5", "yices2", "opensmt", "smtinterpol"]
                else:
                    log.warning("pySMT parser does not support some outputs from solvers that support NRA even though LIA works just fine.")
                    solvers = ["z3", "cvc5", "yices2"]
                # z3 is pySMT's own (z3-solver), the others have to be configured
                solvers = [name for name in solvers if name == "z3" or (name in self.solver_config and self.solver_config[name].portfolio
                                                                        and self.gen.logic in self.solver_config[name].logics)]
                self.gen.solver = Portfolio(solvers, logic=self.gen.logic, incremental=incremental_mode, generate_models=True)
            else:
                self.gen.solver = Solver(name=solver, logic=self.gen.logic, incremental=incremental_mode, generate_models=True)
        elif solving == "milp":
            if solver not in ["gurobi", "cbc"]:
                raise ValueError(f"Invalid solver: {solver}")
            self.gen.mode = "milp"
            # a factory, not a solver object: PuLP's GUROBI keeps one Gurobi model and adds the
            # whole problem to it again on every solve(), so each solve needs a fresh solver
            if solver == "gurobi":
                env = quiet_gurobi_env()
                self.gen.solver = lambda: GUROBI(msg=False, env=env, FeasibilityTol=1e-9, MIPGap=1e-9)
            else:
                # CBC ships with PuLP; gapRel=0 proves optimality like MIPGap above
                self.gen.solver = lambda: PULP_CBC_CMD(msg=False, gapRel=0)
        elif solving == "gurobi":
            if solver not in [None, "gurobi"]:
                raise ValueError(f"Invalid solver for gurobi solving: {solver}")
            self.gen.mode = "gurobi"
            self.gen.solver = solver
        
        scratch = tempfile.TemporaryDirectory() if output_qasm is None else None
        if scratch is not None:
            output_qasm = os.path.join(scratch.name, "circuit.qasm")
        # the solver processes live until the synthesis ends, also when it ends with an exception
        try:
            if solving == "smt" and incremental_mode:
                self.gen.solver.create_process()
                self.gen.set_incremental_mode()
            self.gen.declare_helpers()
            self.gen.q = self.q
            if d is not None:
                self.d = d
            self.gen.d = self.d
            self.gen.num_of_vectors = len(vector_pairs)
            # start synthesis
            res, circuit, vectors = self._synth(vector_pairs, output_qasm)
        finally:
            self.close()
            if scratch is not None:
                scratch.cleanup()

        if self.gen.unknowns:
            unproven = f"{self.gen.unknowns} solver call(s) answered unknown"
            if not res:
                raise SolverError(f"{unproven}: no circuit found, but none was proven not to exist")
            what = "the front may be incomplete" if self.encoding_method == "pareto-incremental" else "its optimality is not proven"
            log.warning("%s: the circuit is correct, but %s", unproven, what)
        log.info("Circuit: %s", circuit)
        for pair_idx, (vector) in enumerate(vectors or []):
            log.info("Vector %d: %s", pair_idx, vector)
        log.info("Result: %s", res)
        full = time.perf_counter() - start_time
        # assigned, not added: a nested synthesis (in this process or a pareto worker) sets its own "full"
        times["full"] = full
        # this run's own share; the five phases are always there
        self.times = {phase: 0.0 for phase in ["full", "parsing", "encoding", "solving", "updating"]}
        self.times.update({name: seconds - times_before.get(name, 0.0) for name, seconds in times.items()})
        self.times["full"] = full
        return res, circuit, vectors
    
    
    
    def _synth(self, vector_pairs, output_qasm="circuit.qasm") -> bool:
        # encode weights
        # every encoding interval is closed before a solve and reopened after it
        encoding_start = time.perf_counter()
        weights = []
        weight_bound = 0
        max_weight = self.gate_set.max_weight()
        for i in range(self.d + 1):
            weight_bound = weight_bound + max_weight
            weights.append(self.gen.declare_integer(f"W{i}", lb=0, ub=weight_bound))
        # initial cost of the circuit is 0
        self.gen.add_assertion(self.gen.Equals(weights[0], self.gen.Int(0)))
        
        # encode vector bounds
        inter_states = []
        target_states = []
        # k of every (input, target) pair and its largest increase per layer, used to bound the FiveTuple k
        if self.complex_representation != Complex:
            self.pair_k = [(input_state.k, output_state.k) for input_state, output_state in vector_pairs]
            self.k_increment = max_k_increment(self.gate_set)
        bounds = [1] * (self.d + 1)
        if self.complex_representation != Complex:
            for d in range(self.d + 1):
                bounds[d] = bounds[d-1] * 2
            self.bound = bounds[self.d]
        
        for pair_idx, (input_state, output_state) in enumerate(vector_pairs):
            # input vector
            max_value_in_input = input_state.max_value()
            In = Vector(q=2**self.q, name=f"In_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k=input_state.k, n=input_state.n, bound=max_value_in_input, k_bound = input_state.k)
            for i, val in enumerate(input_state):
                if self.gen.mode == "smtlib":
                    for j in range(len(input_state[i])):
                        self.gen.add_assertion(self.gen.Equals(In[i][j], self.gen.Real(val[j])))
                else:
                    self.gen.add_assertion(self.gen.Equals(In[i], val))
            if self.complex_representation == FiveTuple:
                self.gen.add_assertion(self.gen.Equals(In.k, self.gen.format_integer(input_state.k)))
            
            # encode intermediate vectors, bind the first one to the input vector
            inter = [None] * (self.d + 1)
            for d in range(self.d + 1):
                Inter = None
                if self.complex_representation == FiveTuple:
                    Inter = Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, k=input_state.k if d == 0 else 0, n = input_state.n, bound = bounds[d], k_bound = input_state.k + self.k_increment * d)
                else:
                    Inter = Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, bound = bounds[d], k_bound = 2 * (d+1))
                
                if d == 0:
                    if self.gen.mode == "milp" or self.gen.mode == "gurobi":
                        for i in range(len(Inter)):
                            self.gen.add_assertion(self.gen.Equals(Inter[i], In[i]))
                        self.gen.add_assertion(self.gen.Equals(Inter.k, In.k))
                    else:
                        self.gen.add_assertion(self.gen.Equals(Inter, In))
                inter[d] = Inter
            
            inter_states.append(inter)
                
            # encode target vectors
            max_value_in_target = output_state.max_value()
            Target = Vector(q=2**self.q, name=f"Target_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = output_state.k, n = output_state.n, bound=max_value_in_target, k_bound = output_state.k)
            for i, val in enumerate(output_state):
                if self.gen.mode == "smtlib":
                    for j in range(len(output_state[i])):
                        self.gen.add_assertion(self.gen.Equals(Target[i][j], self.gen.Real(val[j])))
                else:
                    self.gen.add_assertion(Target[i] == val)
            
            if self.complex_representation == FiveTuple:
                self.gen.add_assertion(self.gen.Equals(Target.k, self.gen.format_integer(output_state.k)))
            
            target_states.append(Target)
        
        res = False # output result
        # based on chosen method, encode layers and equivalence
        if self.encoding_method == "basic" or self.encoding_method in ["binary", "topdown", "bottomup"]:
            # encode whole circuit
            for d in range(self.d):
                if self.complex_representation == Complex:
                    if self.layer_bigM == 1:
                        self.layer_bigM = 4
                    self.layer_bigM = self.layer_bigM
                else:
                    self.layer_bigM = self.layer_bigM * 2
                selection_variables, bool_variables = self.gen.add_selection_variables(d, self.gate_set, self.circuit_q)
                for pair_idx in range(len(vector_pairs)):
                    self.encode_layer(inter_states[pair_idx][d], inter_states[pair_idx][d+1], d, weights[d], weights[d+1], selection_variables, bool_variables)
                # add constraining rules - no H H, Tdg T, ...
                self.gen.add_constraints(self.gate_set, d, self.circuit_q)
            
            self.encode_equivalence(inter_states, target_states, self.d)
            # fully encoded (except for the weight bound), save the formula
            self.gen.add_objective(weights[self.d])
            formula_file = self.gen.write_formula(output_qasm)
            times["encoding"] += time.perf_counter() - encoding_start
            
            if self.encoding_method == "basic":
                res, circuit, vectors = self.solve_and_extract_circuit(output_qasm=output_qasm, formula_file=formula_file, write_to_file=True)
            elif self.encoding_method == "binary":
                res, circuit, vectors = self.binary_cost_search(weights, output_qasm=output_qasm, formula_file=formula_file)
            elif self.encoding_method == "topdown":
                res, circuit, vectors = self.incremental_top_down_cost_search(weights, output_qasm=output_qasm, formula_file=formula_file)
            elif self.encoding_method == "bottomup":
                res, circuit, vectors = self.incremental_bottom_up_cost_search(weights, output_qasm=output_qasm, formula_file=formula_file)
        
        elif self.encoding_method == "incremental" or self.encoding_method == "pareto-incremental":
            # incrementally generate circuit and equivalence
            times["encoding"] += time.perf_counter() - encoding_start
            if self.encoding_method == "pareto-incremental":
                if self.vector_mode == "rus":
                    self.pareto_front = Pareto(timeout=self.pareto_timeout, maximize_y=True,
                                               x_label="T-count (circuit + recovery)", y_label="Probability of success")
                else:
                    self.pareto_front = Pareto(timeout=self.pareto_timeout, maximize_y=False,
                                               x_label="Gate count", y_label="Cost (gate weights)")
            self.curr_depth = 0
            circuit, vectors = None, None
            while not res:
                encoding_start = time.perf_counter()
                if self.max_depth is not None and self.curr_depth > self.max_depth:
                    log.info("No circuit with at most %d gates %s", self.max_depth, "found" if self.gen.unknowns else "exists")
                    break
                log.info("Trying depth: %d", self.curr_depth)
                self.gen.d = self.curr_depth
                # depth 0 has no layer: the empty circuit is checked first, as basic and binary do
                if self.curr_depth > 0:
                    log.info("Encoding new layer")
                    # encode new layer (depth-1) and connect inter[depth-1] to inter[depth]
                    # pareto-incremental enumerates every circuit once, at the depth equal to its gate count: with empty
                    # (id) layers, each circuit would come back with ids in every position, on every qubit, at every depth
                    selection_variables, bool_variables = self.gen.add_selection_variables(self.curr_depth-1, self.gate_set, self.circuit_q,
                                                                                           include_identity=self.encoding_method != "pareto-incremental")
                    if self.complex_representation == Complex:
                        if self.layer_bigM == 1:
                            self.layer_bigM = 4
                        self.layer_bigM = self.layer_bigM
                    else:
                        self.layer_bigM = self.layer_bigM * 2
                    if self.curr_depth > self.d:
                        # beyond the preallocated depth: one new weight for the layer, one new state per pair
                        weight_bound = weight_bound + max_weight
                        weights.append(self.gen.declare_integer(f"W{self.curr_depth}", lb=0, ub=weight_bound))
                    for pair_idx in range(len(vector_pairs)):
                        if self.curr_depth > self.d:
                            if self.complex_representation == FiveTuple:
                                state = Vector(q=2**self.q, name=f"I_{pair_idx}_{self.curr_depth}", generator=self.gen, element_representation=self.complex_representation, k=0, n = vector_pairs[pair_idx][0].n, bound = self.bound, k_bound = vector_pairs[pair_idx][0].k + self.k_increment * self.curr_depth)
                            else:
                                state = Vector(q=2**self.q, name=f"I_{pair_idx}_{self.curr_depth}", generator=self.gen, element_representation=self.complex_representation, bound = self.bound, k_bound = 2 * (self.curr_depth+1))
                            inter_states[pair_idx].append(state)

                        # encode the layer
                        self.encode_layer(inter_states[pair_idx][self.curr_depth-1], inter_states[pair_idx][self.curr_depth], self.curr_depth-1, weights[self.curr_depth-1], weights[self.curr_depth], selection_variables, bool_variables)
                
                    log.info("Encoded layer %d", self.curr_depth-1)

                        # constraints do not have any effect on incremental synthesis
                        #self.gen.add_constraints(self.gate_set, self.curr_depth-1, self.circuit_q)
                    if self.complex_representation != Complex:
                        self.bound = self.bound * 2
                    
                log.info("Pushing depth %d", self.curr_depth)
                self.gen.push()
                log.info("Pushed depth %d", self.curr_depth)
                
                if self.encoding_method == "pareto-incremental":
                    log.info("Encoding equivalence for depth %d", self.curr_depth)
                    self.encode_equivalence(inter_states, target_states, self.curr_depth)
                    log.info("Encoded equivalence for depth %d", self.curr_depth)

                    times["encoding"] += time.perf_counter() - encoding_start

                    # enumerate models for this depth
                    sat = True
                    log.info("Enumerating models for depth %d", self.curr_depth)
                    while sat:
                        # rewritten for every model, the previous ones are filtered out by then
                        with timed("encoding"):
                            formula_file = self.gen.write_formula(output_qasm)
                        # the worker is a forked process: its count of unknown answers comes back with the result
                        outcome = self.pareto_front.start(
                            lambda: (self.solve_and_extract_circuit(
                                formula_file=formula_file,
                                output_qasm=output_qasm,
                                write_to_file=False,  # every point goes to pareto_front/, the best one to output_qasm
                                draw_circuit=False,
                            ), self.gen.unknowns)
                        )
                        if self.pareto_front.timeout_met():
                            break
                        (result, circuit, vectors), self.gen.unknowns = outcome
                        if not result:
                            sat = False # last model found
                        else:
                            # compute the cost, if RUS, also synthesize the recovery operation
                            cost_x, cost_y = 0.0, 0.0
                            recovery_circuit = None
                            if self.vector_mode == "rus":
                                cost_x, cost_y = self.rus_cost(circuit, None, vectors)
                                # a circuit that always succeeds needs no recovery (the state after a failure is zero)
                                if cost_y < 1 - 1e-8:
                                    # synthesize the recovery operation: it maps the state after a failed
                                    # attempt (ancilla measured to 1) back to the input state
                                    states_recovery = rus_recovery_pairs(vectors, vector_pairs, self.qubits_to_measure)
                                    synthesizer = Synthesizer()
                                    gate_set = self.gate_set
                                    # errors (e.g. a failing solver) are raised again by start() and stop the run
                                    res_recovery, recovery_circuit, recovery_vectors = self.pareto_front.start(
                                        lambda: synthesizer.synthesis(
                                            vector_pairs=states_recovery,
                                            vectors="custom",
                                            q=self.q,
                                            d=self.d,
                                            # a recovery longer than the input circuit is not worth it; without
                                            # a bound, a missing recovery would use up the whole time limit
                                            max_depth=self.d,
                                            gate_set=gate_set,
                                            output_qasm=os.path.splitext(output_qasm)[0] + "_recovery.qasm",
                                            solving="gurobi",
                                            solver="gurobi",
                                            mode="incremental",
                                            complex_representation="Classic",
                                            targets=self.targets,
                                            ancillas=self.ancillas,
                                            up_to_global_phase=True,
                                        )
                                    )
                                    if self.pareto_front.timeout_met():
                                        break
                                    if not res_recovery:  # no recovery circuit exists
                                        recovery_circuit = Circuit(gates=[], q=self.q, d=self.d)
                                        recovery_circuit.cost = np.inf
                                    cost_x, cost_y = self.rus_cost(circuit, recovery_circuit, vectors)
                            else:
                                cost_x, cost_y = self.circuit_cost(circuit)
                            # add the point to the pareto front and filter the model
                            self.pareto_front.add_point(cost_x, cost_y, self.curr_depth, circuit, recovery_circuit)
                            if self.curr_depth == 0:
                                break  # the empty circuit is the only one, and it has no gates to filter
                            with timed("encoding"):
                                self.gen.filter_model(circuit.bool_variables, self.curr_depth)
                    self.gen.pop()
                    self.restart_after_empty_circuit()
                    self.curr_depth += 1
                    if self.pareto_front.timeout_met():
                        break
                            
                else:
                    log.info("Encoding equivalence for depth %d", self.curr_depth)
                    self.encode_equivalence(inter_states, target_states, self.curr_depth)
                    log.info("Encoded equivalence for depth %d", self.curr_depth)

                    # without objective
                    log.info("Writing formula for depth %d", self.curr_depth)
                    formula_file = self.gen.write_formula(output_qasm)
                    log.info("Formula written for depth %d", self.curr_depth)
                    times["encoding"] += time.perf_counter() - encoding_start
                    result, circuit, vectors = self.solve_and_extract_circuit(formula_file=formula_file, output_qasm=output_qasm, write_to_file=True)
                    if result:
                        res = True
                    else:
                        # remove rescaled_... variables from the problem
                        log.info("Popping depth %d", self.curr_depth)
                        self.gen.pop()
                        log.info("Popped depth %d", self.curr_depth)
                        self.restart_after_empty_circuit()
                        self.curr_depth += 1
            if self.encoding_method == "pareto-incremental":
                self.pareto_front.cleanup()
                res, circuit, vectors = self.pareto_front.best()
                # the recovery synthesis wrote the recovery of every model here: keep only the best point's
                recovery_qasm = os.path.splitext(output_qasm)[0] + "_recovery.qasm"
                recovery_circuit = None
                if res:
                    circuit.write_to_file(output_qasm)
                    recovery_circuit = next(point[4] for point in self.pareto_front.front if point[3] is circuit)
                if recovery_circuit is not None:
                    recovery_circuit.write_to_file(recovery_qasm)
                elif os.path.exists(recovery_qasm):
                    os.remove(recovery_qasm)
        else:
            raise ValueError(f"Invalid encoding method: {self.encoding_method}")

        return res, circuit, vectors

    def max_cost(self):
        return (self.d + 1) * self.gate_set.max_weight()

    def binary_cost_search(self, weights, formula_file="formula.smt2", output_qasm="circuit.qasm"):
        solved = []
        unsolved = []
        lower_bound = 0
        upper_bound = self.max_cost()
        best_circuit = None
        best_vectors = None
        while True:
            middle = lower_bound + (upper_bound - lower_bound) // 2
            if lower_bound + 1 >= upper_bound:
                # found the optimal depth -- upper bound is the best solution
                if lower_bound not in solved and lower_bound not in unsolved:
                    middle = lower_bound # dont know anything about the result
                elif upper_bound not in solved and upper_bound not in unsolved:
                    middle = upper_bound # lower bound is unsat, upper bound untested
                else:
                    break
            self.gen.push()
            with timed("encoding"):
                self.gen.add_assertion(self.gen.LE(weights[self.d], self.gen.Int(middle)))
                formula_file = self.gen.write_formula(output_qasm)          
            result, circuit, vectors = self.solve_and_extract_circuit(formula_file=formula_file, output_qasm=output_qasm, write_to_file=True)                
            if result:
                upper_bound = middle
                # save the best circuit so far
                best_circuit = circuit
                best_vectors = vectors
                solved.append(middle)
            else:
                lower_bound = middle
                unsolved.append(middle)
            self.gen.pop()

        if best_circuit is not None:
            return True, best_circuit, best_vectors
        else:
            return False, None, None
        
    def incremental_bottom_up_cost_search(self, weights, formula_file="formula.smt2", output_qasm="circuit.qasm"):
        i = 0
        while i <= self.max_cost():
            self.gen.push()
            with timed("encoding"):
                self.gen.add_assertion(self.gen.LE(weights[self.d], self.gen.Int(i)))
                formula_file = self.gen.write_formula(output_qasm)
                 
            result, circuit, vectors = self.solve_and_extract_circuit(formula_file=formula_file, output_qasm=output_qasm, write_to_file=True)                
            if result:
                return result, circuit, vectors
            self.gen.pop()
            i += 1

        return False, None, None

    def incremental_top_down_cost_search(self, weights, formula_file="formula.smt2", output_qasm="circuit.qasm"):
        i = self.max_cost()
        best_circuit = None
        best_vectors = None
        while i >= 0:
            self.gen.push()
            with timed("encoding"):
                self.gen.add_assertion(self.gen.LE(weights[self.d], self.gen.Int(i)))
                formula_file = self.gen.write_formula(output_qasm)
            result, circuit, vectors = self.solve_and_extract_circuit(formula_file=formula_file, output_qasm=output_qasm, write_to_file=True)
            self.gen.pop()
            if not result:
                # first unsolvable, the previous model is the best
                break
            best_circuit = circuit
            best_vectors = vectors
            i -= 1

        if best_circuit is not None:
            return True, best_circuit, best_vectors
        return False, None, None

    def restart_after_empty_circuit(self) -> None:
        # the deeper circuits are searched by a solver process that has not seen the depth-0 check: with it, yices2
        # took minutes instead of a second for depth 2 of an approximate GHZ synthesis (QF_NRA)
        if self.curr_depth == 0 and self.gen.mode == "smtlib" and self.gen.incremental_mode:
            log.info("Restarting the solver after the empty circuit")
            self.gen.restart_incremental()

    def solve_and_extract_circuit(self, formula_file="formula.smt2", output_qasm="circuit.qasm", write_to_file = True, draw_circuit = False) -> bool:
        """    
            formula_file: Path to the formula file
            output_qasm: Output filename for QASM circuit
        """
        log.info("Solving formula")
        with timed("solving"):
            result = self.gen.check_sat(formula_file)
        log.info("Solving finished")
        if result:
            log.info("Parsing model")
            with timed("parsing"):
                model = self.gen.get_model()
                res = self.parser.parse(model, self.q, self.curr_depth, output_qasm, self.complex_representation, write_to_file=False, draw_circuit=False, v=self.v,
                                        circuit_qubits=self.circuit_q)
            log.info("Parsing finished")
            if isinstance(res, tuple) and res[0]:
                circuit = res[1]
                # every layer selects exactly one gate (possibly id), so an empty layer means the model is incomplete
                empty_layers = [d for d, gate in enumerate(circuit.gates) if gate is None]
                if empty_layers:
                    raise RuntimeError(f"the solver model selects no gate in layer(s) {empty_layers}; it is incomplete or was not parsed correctly")
                # before writing: the output file needs the input circuit's end-of-circuit measurements too, into the
                # same classical bits
                circuit.add_measurements(self.output_measurements, self.classical_declarations)
                if write_to_file:
                    circuit.write_to_file(output_qasm)
                if draw_circuit:
                    circuit.draw(output_file=os.path.splitext(output_qasm)[0] + ".png")
            return res
        else:
            return False, None, None