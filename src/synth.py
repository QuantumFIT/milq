"""
@file: synth.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: quantum circuit synthesis using SMT and MILP solving
"""

from complex.classic import Complex
from complex.vector import Vector
from complex.fivetuple import FiveTuple
from complex.ntuple import nTuple
from complex.matrix import Matrix
from generator import Generator
from parser import ModelParser
import os
import subprocess
from sim import Simulator
from pysmt.logics import QF_NRA, QF_LIA, QF_NIA, QF_LRA
from pysmt.shortcuts import Portfolio, Symbol, Real, And, Equals, Plus, GT, LT, get_env, Int, Or, Not, Implies, GE, LE, Ite, Minus, Div, Times, write_smtlib, Solver
from pysmt.typing import REAL, INT
from pareto import Pareto
from gates import GateSet, supported_gates, check_supported, Circuit
from pulp import *
from gurobipy import GRB
from solvers import PortfolioSMTSolver, SMTSolver
import time
from logger import Logger
import numpy as np

class Synthesizer:
    def __init__(self) -> None:
        self.logger = Logger(verbosity=1, filename="synth.log")
        self.gen = Generator(logger=self.logger)
        self.parser = ModelParser(logger=self.logger)
        self.gate_set = GateSet()
        self.simulator = None
        self.complex_representation = None
        self.solver = None
        self.fidelity_threshold = 1.0
        self.bound = 1
        self.k_bound = (0, 1)
        self.layer_bigM = 1
        self.q = None
        self.d = None
        self.max_k = 0
        self.encoding_method = None
        self.curr_depth = 0
        self.v = 0
        self.vec_mode = None
        self.pareto_front = None
        self.up_to_global_phase = False
        self.targets = 1
        self.ancillas = 0
        self.vector_mode = None
        self.solvers = {}
        self.qubits_to_measure = None
        self.post_measurement = False
        self.approx = False
        self.basis = "cb"
        self.ref_dot = None
        self.stats = {}
        # times taken
        self.stats['parsing'] = 0
        self.stats['encoding'] = 0
        self.stats['solving'] = 0
        
    def __exit__(self) -> None:
        if self.gen.mode == "pysmt":
            self.gen.solver.exit() # portfolio is still alive
            
    def add_solvers(self, incremental_mode : bool = False) -> None:
        # register custom solvers for pySMT portfolio solving
        repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        qf_lia = QF_LIA if self.gen.mode == "pysmt" else "QF_LIA"
        qf_nra = QF_NRA if self.gen.mode == "pysmt" else "QF_NRA"
        qf_nia = QF_NIA if self.gen.mode == "pysmt" else "QF_NIA"
        qf_lra = QF_LRA if self.gen.mode == "pysmt" else "QF_LRA"
        path = [os.path.join(repo_root, "solvers", "opensmt", "opensmt")]
        self.add_one_solver(name="opensmt", args=path, logics=[qf_lia, qf_lra], incremental_mode=incremental_mode)
        
        path = ["z3"]
        smtlib_flags = ["-in"] if incremental_mode else None
        self.add_one_solver(name="z3", args=path, logics=[qf_lia, qf_nra, qf_nia], smtlib_flags=smtlib_flags, incremental_mode=incremental_mode)
        
        smtlib_flags = ["--incremental"] if incremental_mode else None
        path = [os.path.join(repo_root, "solvers", "yices2", "yices_smt2")]
        self.add_one_solver(name="yices2", args=path, logics=[qf_lia, qf_nra, qf_nia, qf_lra],smtlib_flags=smtlib_flags, incremental_mode=incremental_mode)
        
        path = [os.path.join(repo_root, "solvers", "smtinterpol", "smtinterpol")]
        self.add_one_solver(name="smtinterpol", args=path, logics=[qf_lia, qf_nra, qf_nia], incremental_mode=incremental_mode)
        
        smtlib_flags = ["--produce-models"]
        smtlib_flags.append("--incremental") if incremental_mode else None
        path = [os.path.join(repo_root, "solvers", "cvc5", "cvc5")]
        self.add_one_solver(name="cvc5", args=path, logics=[qf_lia, qf_nra, qf_nia], smtlib_flags=smtlib_flags, incremental_mode=incremental_mode)
        
        smtlib_flags = ["--precision", "1e-9", "--produce-models"]
        smtlib_flags.append("--in") if incremental_mode else None
        path = ['/opt/dreal/4.21.06.2/bin/dreal']
        self.add_one_solver(name="dreal", args=path, logics=[qf_nra], smtlib_flags=smtlib_flags, incremental_mode=incremental_mode)
    
    def add_one_solver(self, name: str, args: list[str], logics: list[str], smtlib_flags: list[str] = [], incremental_mode: bool = False) -> None:
        if name == "z3" and self.gen.mode == "pysmt": 
            return
        if self.gen.mode == "pysmt":
            env = get_env()
            env.factory.add_generic_solver(name=name, args=args, logics=logics)
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

        # add constraints for only one gate per layer
        self.gen.ExactlyOne(*bool_variables)
    
        size = 2**self.q
        size = size if self.basis == 'cb' else size * size
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
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'h':
                    modified_positions = []
                    if self.basis == "cb":
                        for pos in range(size):
                            if pos in modified_positions: continue
                            other = pos ^ (1 << q)
                            modified_positions.append(pos)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, ((inp[pos] + inp[other]).divide_by_sqrt2(self.gen))))
                            saved_operations[other].append((bool_var, ((inp[pos] + (inp[other].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen))))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_incr(bool_var, out.k, inp.k, 1)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for H gate")
                elif gate == 's':
                    if self.basis == "cb":  
                        for pos in range(size):
                            one_flag = (pos >> q) & 1
                            if one_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_i(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for S gate")
                elif gate == 'sdg':
                    if self.basis == "cb":
                        for pos in range(size):
                            one_flag = (pos >> q) & 1
                            if one_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_i(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for SDG gate")
                elif gate == 't':
                    if self.basis == "cb":
                        for pos in range(size):
                            one_flag = (pos >> q) & 1
                            if one_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_omega(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for T gate")
                elif gate == 'tdg':
                    if self.basis == "cb":
                        for pos in range(size):
                            one_flag = (pos >> q) & 1
                            if one_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_omega_counter(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for TDG gate")
                elif gate == 'x':
                    modified_positions = []
                    if self.basis == "cb":
                        for pos in range(size):
                            if pos in modified_positions: continue
                            other = pos ^ (1 << q)
                            modified_positions.append(pos)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, inp[other]))
                            saved_operations[other].append((bool_var, inp[pos]))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for X gate")
                elif gate == 'sx':
                    modified_positions = []
                    if self.basis == "cb":
                        for pos in range(size):
                            if pos in modified_positions: continue
                            other = pos ^ (1 << q)
                            modified_positions.append(pos)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))))
                            saved_operations[other].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_incr(bool_var, out.k, inp.k, 2)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for SX gate")
                elif gate == 'sxdg':
                    modified_positions = []
                    if self.basis == "cb":
                        for pos in range(size):
                            if pos in modified_positions: continue
                            other = pos ^ (1 << q)
                            modified_positions.append(pos)
                            modified_positions.append(other)
                            saved_operations[pos].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))))
                            saved_operations[other].append((bool_var, ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_incr(bool_var, out.k, inp.k, 2)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for SXDG gate")
                elif gate == 'y':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for Y gate")
                elif gate == 'z':
                    if self.basis == "cb":
                        for pos in range(size):
                            one_flag = (pos >> q) & 1
                            if one_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_one(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for Z gate")
            elif len(rest) == 3: # two qubit
                q1 = rest[1]
                q2 = rest[2]
                if gate == 'cx':
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CX gate") 
                elif gate == 'xcx':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for XCX gate")
                elif gate == 'dcx':
                    if self.basis == "cb":
                        for pos in range(size):
                            # dcx = cx(q1, q2) cx(q2, q1) permutes |a, b> -> |b, a xor b> (a 3-cycle)
                            control_flag = (pos >> q1) & 1
                            target_flag = (pos >> q2) & 1
                            image = (pos & ~((1 << q1) | (1 << q2))) | (target_flag << q1) | ((control_flag ^ target_flag) << q2)
                            if image == pos and not cannot_propagate: continue
                            saved_operations[image].append((bool_var, inp[pos]))
                            propagate_identities[image].append(bool_var)
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for DCX gate")
                elif gate == 'ch':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_incr(bool_var, out.k, inp.k, 1)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CH gate")
                elif gate == 'csx':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_incr(bool_var, out.k, inp.k, 2)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CSX gate")
                elif gate == 'cy':
                    modified_positions = []
                    if self.basis == "cb":
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
                        
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CY gate")
                elif gate == 'cz':
                    if self.basis == "cb":
                        for pos in range(2**self.q):
                            control_flag = (pos >> q1) & 1
                            target_flag = (pos >> q2) & 1
                            if control_flag and target_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_one(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CZ gate")
                elif gate == 'cs':
                    if self.basis == "cb":  
                        for pos in range(size):
                            control_flag = (pos >> q1) & 1
                            target_flag = (pos >> q2) & 1
                            if control_flag and target_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_i(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CS gate")
                elif gate == 'csdg':
                    if self.basis == "cb":
                        for pos in range(size):
                            control_flag = (pos >> q1) & 1
                            target_flag = (pos >> q2) & 1
                            if control_flag and target_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_i(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CSDG gate")
                elif gate == 'swap':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for SWAP gate")
                elif gate == 'iswap':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for ISWAP gate")
                elif gate == 'sqrtswap':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_incr(bool_var, out.k, inp.k, 2)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for SQRTSWAP gate")
            elif len(rest) == 4: # three qubit
                q1 = rest[1]
                q2 = rest[2]
                q3 = rest[3]
                if gate == 'ccx':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CCX gate")
                elif gate == 'cswap':
                    modified_positions = []
                    if self.basis == "cb":
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
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CSwap gate")
                elif gate == 'ccz':
                    if self.basis == "cb":
                        for pos in range(size):
                            q1_flag = (pos >> q1) & 1
                            q2_flag = (pos >> q2) & 1
                            q3_flag = (pos >> q3) & 1
                            if q1_flag and q2_flag and q3_flag:
                                saved_operations[pos].append((bool_var, inp[pos].multiply_by_minus_one(self.gen)))
                                propagate_identities[pos].append(bool_var)
                            elif cannot_propagate:
                                saved_operations[pos].append((bool_var, inp[pos]))
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            add_k_eq(bool_var, out.k, inp.k)
                    elif self.basis == "pauli":
                        raise NotImplementedError("Pauli basis not supported for CCZ gate")
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
            # average gate fidelity
            if self.gen.mode == "milp":
                raise NotImplementedError("approximate equivalence not supported for milp mode (non-linear)")
            if self.post_measurement:
                raise NotImplementedError("post-measurement is not supported for approximate equivalence")
            
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
                        vec = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Multiplied_by_global_phase_{vec2.name}", bound=2**self.max_k)
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
                    rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{vec1.name}", bound=2**self.max_k)
                    rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{vec2.name}", bound=2**self.max_k)
                    if self.gen.mode == "milp" or self.gen.mode == "gurobi":
                        self.gen.add_milp_rescaling(rescaled1, rescaled2, vec1, vec_target, pair_idx, self.max_k)
                    else:
                        self.gen.add_rescaling(rescaled1, rescaled2, vec1, vec_target, pair_idx, self.max_k)
                    for i in range(2**self.q):
                        self.gen.add_assertion(self.gen.Equals(rescaled1[i], rescaled2[i]))
                    
    def rus_cost(self, circuit, recovery_circuit, vectors) -> tuple[int, float]:
        # Cost(circuit) / P[success]
        try:
            print(f"Calculating RUS circuit cost")
            target_zero = vectors[0][0]
            target_one = vectors[0][1]
            prob = target_zero.abs2() + target_one.abs2()
            cost = circuit.cost
            recovery_cost = recovery_circuit.cost
            sum = 0
            for i in range(len(vectors[0])):
                sum += vectors[0][i].abs2()
                
            prob_success = prob / sum
            print(f"Probability of success: {prob_success}")
            print(f"Circuit T count: {cost}")
            print(f"Recovery circuit T count: {recovery_cost}")
            print(f"Cost: {(cost + recovery_cost) / prob_success}")
            return cost + recovery_cost, prob_success
        except Exception as e:
            return np.inf, 0.0
        
    def circuit_cost(self, circuit) -> tuple[int, int]:
        # x is circuit depth, y is the cost
        return circuit.gate_count(), circuit.get_cost()

    def set_initial_values(self):
        for i, (gate, qubits) in enumerate(self.simulator.stats['input_circuit']):
            bool_var_str = f"L{i}_{gate}"
            for qubit in qubits:
                bool_var_str += f"_q{qubit}"
            bool_var = self.gen.declare_bool(bool_var_str)
            bool_var.setInitialValue(1)
    
    def synthesis(self, qasm_file=None, matrix=None, vectors=None, vector_pairs=None, solving="gurobi", solver=None, mode="incremental", output_qasm="circuit.qasm", 
                complex_representation="FiveTuple", gate_set=None, q=None, d=None, fidelity_threshold=1.0, targets=1, ancillas=1, 
                up_to_global_phase=False, basis="cb", approx=False, no_measurement=False) -> tuple[bool, Circuit, list[Vector]]:
        """
            qasm_file -> file to synthesize
            vectors -> specify what set of input vectors to use (zero -> only |0>^n state, all -> all cbs, rus -> |0>, |1>, |+> on target, |0> on ancillas, custom -> has to specify vector_pairs, q, d, gate_set)
            vector_pairs -> list of pairs (input_vector, output_vector) for input and its expected output.
            solving -> specify if smt (has to specify solver), pysmt, milp, gurobipy
            solver -> specify specific solver or portfolio of solvers
            mode -> specify solving method (basic -> create whole formula and get the best model, incremental -> incrementally generate the formula, binary, topdown, bottomup -> searches to optimize cost function)
            output_qasm -> file to write the output circuit to
            complex_representation -> specify the complex representation ["FiveTuple", "nTuple", "Classic"]
            gate_set -> specify the gate set to use using the GateSet class, otherwise, the gate set is taken from the input qasm file
            q -> number of qubits of the output circuit (has to correspond to the vector_pairs size)
            d -> number of allowed gates in the output circuit
            fidelity_threshold -> solver=dreal and mode=smtlib uses QF_NRA and fidelity instead of exact equivalence
            targets -> number of target qubits (used for RUS -- targets are always the lowest indices)
            ancillas -> number of ancilla qubits (used for RUS -- ancillas are always the highest indices)
            up_to_global_phase -> if True, the synthesis will be done up to global phase (if the mode supports it)
            basis -> basis to use for the synthesis ["pauli", "cb"] - pauli basis (density matrices) or computational basis (vectors)
            approx -> if True, the synthesis will be done approximately (if the mode supports it)
            no_measurement -> if True, the output qubits will not be measured (ignores end-of-circuit measurement in the input circuit)
        """
        start_time = time.time()
        if vectors is None:
            raise ValueError("provide vectors to select vector-mode")
        if vectors in ["zero", "all", "rus", "jamiolkowski"] and vector_pairs is not None:
            raise ValueError("vector_pairs cannot be provided when vectors are specified")
        if vectors == "custom" and (vector_pairs is None or q is None or d is None or gate_set is None):
            raise ValueError("vector_pairs, q, d, and gate_set are required when vectors are custom")
        if qasm_file is None and matrix is None and vector_pairs is None:
            raise ValueError("input qasm_file or matrix is required")
        if qasm_file is not None and matrix is not None and vector_pairs is not None:
            raise ValueError("qasm_file and matrix cannot be provided at the same time")
        
        if matrix is not None and vectors != "rus":
            raise ValueError("matrix can be provided only for rus mode")
        if solving in ["smt", "milp", "pysmt"] and solver is None:
            raise ValueError("a solver is required for basic smt and milp solving")
        if mode not in ["basic", "incremental", "binary", "topdown", "bottomup", "pareto-incremental", 'divide-and-conquer']:
            raise ValueError("mode can be only basic, incremental, binary, topdown, or bottomup")
        if complex_representation not in ["FiveTuple", "nTuple", "Classic"]:
            raise ValueError("complex_representation can be only FiveTuple, nTuple, or Classic")
        if complex_representation == "FiveTuple":
            self.complex_representation = FiveTuple
        elif complex_representation == "nTuple":
            self.complex_representation = nTuple
        elif complex_representation == "Classic":
            self.gen.logic = "QF_NRA"
            self.complex_representation = Complex
        if complex_representation == "FiveTuple" and approx:
            self.gen.logic = "QF_NRA"
        if fidelity_threshold > 1.0 or fidelity_threshold < 0.0:
            raise ValueError("fidelity_threshold must be in [0.0, 1.0]")

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

        if vectors in ["zero", "all", "rus", "jamiolkowski"]:
            # set circuit statistics to prepare synthesis
            self.simulator = Simulator(qasm_file, matrix, complex_representation=self.complex_representation, basis=basis, no_measurement=no_measurement)
            self.gate_set = gate_set
            if vectors == "zero":
                vector_pairs = self.simulator.simulate_zero()
            elif vectors == "all":
                vector_pairs = self.simulator.simulate_circuit()
            elif vectors == "rus":
                # simulate based on number of ancilas and targets!
                vector_pairs = self.simulator.simulate_rus(targets, ancillas)
            elif vectors == "jamiolkowski":
                self.gen.jamiolkowski = True
                vector_pairs = self.simulator.simulate_jamiolkowski()
            
            stats = self.simulator.circuit_stats()
            if self.gate_set is None:
                self.gate_set = stats['gate_set']
                self.gate_set = GateSet.union(self.gate_set, GateSet(preset="Clifford+T"))
            if vectors == "rus":
                self.gate_set = GateSet.union(self.gate_set, GateSet(preset="Clifford+T"))
                self.gate_set.set_t_optimal()
            if self.q is None:
                self.q = stats['q']
            if self.d is None:
                self.d = stats['d']
            if self.qubits_to_measure is None:
                self.qubits_to_measure = stats['measured_qubits']
                self.post_measurement = len(self.qubits_to_measure) > 0
            self.max_k = 2*self.d if self.d > stats['max_k'] else 2*stats['max_k']
        else:
            self.q = q
            self.d = d
            self.max_k = 2*self.d
            self.gate_set = gate_set
            self.qubits_to_measure = []
        self.v = len(vector_pairs)
        self.curr_depth = self.d
        max = 0
        for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
            tmp = input_vector.max_value()
            if tmp > max:
                max = tmp
        self.bound = max
        if len(self.qubits_to_measure) > 0 and self.complex_representation != Complex:
            raise ValueError("end circuit qubit measurement is only supported for a+bj complex representation")
        
        incremental_mode = False
        # set generator mode and solver
        if solving == "smt":
            if solver not in ["z3", "cvc5", "yices2", "opensmt", "smtinterpol", "dreal", "portfolio"]:
                raise ValueError(f"Invalid solver: {solver}")
            self.gen.mode = "smtlib"
            incremental_mode = True if (mode == "incremental" or mode == "pareto-incremental") and solver != "portfolio" else False
            self.add_solvers(incremental_mode=incremental_mode)
            if solver == "dreal":
                self.gen.logic = "QF_NRA"
            
            new_dict = {}
            for name, s in self.solvers.items():
                if self.gen.logic in s.logics:
                    new_dict[name] = s
            if solver == "portfolio":
                self.gen.solver = PortfolioSMTSolver(new_dict, logic=self.gen.logic)
            else:
                self.gen.solver = new_dict[solver]
                if incremental_mode:
                    self.gen.solver.create_process()
                    self.gen.set_incremental_mode()

        elif solving == "pysmt":
            if solver not in ["z3", "cvc5", "yices2", "opensmt", "smtinterpol", "dreal", "portfolio"]:
                raise ValueError(f"Invalid solver: {solver}")
            self.gen.mode = "pysmt"
            incremental_mode = True if mode == "incremental" or mode == "pareto-incremental" else False
            self.add_solvers(incremental_mode=incremental_mode)
            if solver == "portfolio":
                if self.gen.logic != "QF_NRA":
                    solvers = ["z3", "cvc5", "yices2", "opensmt", "smtinterpol"]
                else:
                    self.logger.log("WARNING", "pySMT parser does not support some outputs from solvers that support NRA even though LIA works just fine.")
                    solvers = ["z3", "cvc5","yices2", "smtinterpol"]
                self.gen.solver = Portfolio(solvers, logic=self.gen.logic, incremental=incremental_mode, generate_models=True)
            else:
                self.gen.solver = Solver(name=solver, logic=self.gen.logic, incremental=incremental_mode, generate_models=True)
        elif solving == "milp":
            if solver not in ["gurobi", "cbc"]:
                raise ValueError(f"Invalid solver: {solver}")
            self.gen.mode = "milp"
            solver_to_class = {
                "gurobi": GUROBI,
                "cbc": PULP_CBC_CMD,
            }
            self.gen.solver = solver_to_class[solver](msg=False, FeasibilityTol=1e-9, MIPGap=1e-9)
        elif solving == "gurobi":
            self.gen.mode = "gurobi"
            self.gen.solver = solver
        
        self.gen.declare_helpers()
        self.gen.q = self.q
        if d is not None:
            self.d = d
        self.gen.d = self.d
        self.gen.num_of_vectors = len(vector_pairs)
        # start synthesis
        if self.encoding_method == "divide-and-conquer":
            res, circuit, vectors = self.divide_and_conquer(vector_pairs, output_qasm)
        else:
            res, circuit, vectors = self._synth(vector_pairs, output_qasm)
        
        if solving == "pysmt":
            self.gen.solver.exit()
        self.logger.log("INFO", f"Circuit: {circuit}")
        for pair_idx, (vector) in enumerate(vectors):
            self.logger.log("INFO", f"Vector {pair_idx}: {vector}")
        self.logger.log("INFO", f"Result: {res}")
        self.logger.update_time("full", time.time() - start_time)
        return res, circuit, vectors
    
    
    
    def _synth(self, vector_pairs, output_qasm="circuit.qasm") -> bool:
        # encode weights
        encoding_start = time.time()
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
        bounds = [1] * (self.d + 1)
        if self.complex_representation != Complex:
            for d in range(self.d + 1):
                bounds[d] = bounds[d-1] * 2
            self.bound = bounds[self.d]
        
        for pair_idx, (input_state, output_state) in enumerate(vector_pairs):
            # input vector
            max_value_in_input = input_state.max_value()
            class_to_use = Vector if self.basis == "cb" else Matrix
            In = class_to_use(q=2**self.q, name=f"In_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k=input_state.k, n=input_state.n, bound=max_value_in_input, k_bound = input_state.k)
            for i, val in enumerate(input_state):
                if self.gen.mode == "smtlib":
                    for j in range(len(input_state[i])):
                        self.gen.add_assertion(self.gen.Equals(In[i][j], self.gen.Real(val[j])))
                else:
                    self.gen.add_assertion(self.gen.Equals(In[i], val))
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                self.gen.add_assertion(self.gen.Equals(In.k, self.gen.format_integer(input_state.k)))
            
            # encode intermediate vectors, bind the first one to the input vector
            inter = [None] * (self.d + 1)
            for d in range(self.d + 1):
                Inter = None
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    Inter = class_to_use(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, k=input_state.k if d == 0 else 0, n = input_state.n, bound = bounds[d], k_bound = 2 * (d+1))
                else:
                    Inter = class_to_use(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, bound = bounds[d], k_bound = 2 * (d+1))
                
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
            Target = class_to_use(q=2**self.q, name=f"Target_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = output_state.k, n = output_state.n, bound=max_value_in_target, k_bound = output_state.k)
            for i, val in enumerate(output_state):
                if self.gen.mode == "smtlib":
                    for j in range(len(output_state[i])):
                        self.gen.add_assertion(self.gen.Equals(Target[i][j], self.gen.Real(val[j])))
                else:
                    self.gen.add_assertion(Target[i] == val)
            
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
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
                selection_variables, bool_variables = self.gen.add_selection_variables(d, self.gate_set, self.q)
                for pair_idx in range(len(vector_pairs)):
                    self.encode_layer(inter_states[pair_idx][d], inter_states[pair_idx][d+1], d, weights[d], weights[d+1], selection_variables, bool_variables)
                # add constraining rules - no H H, Tdg T, ...
                self.gen.add_constraints(self.gate_set, d, self.q)
            
            self.encode_equivalence(inter_states, target_states, self.d)
            # fully encoded (except for the weight bound), save the formula
            self.gen.add_objective(weights[self.d])
            formula_file = self.gen.write_formula(output_qasm)
            
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
            encoding_end = time.time()
            self.stats['encoding'] += encoding_end - encoding_start
            self.logger.update_time("encoding", encoding_end - encoding_start)
            encoding_start = time.time()
            if self.encoding_method == "pareto-incremental":
                self.pareto_front = Pareto(max_x=self.d, max_y=1.0)
            self.curr_depth = 1
            while not res:
                self.logger.log("INFO", f"Trying depth: {self.curr_depth}")
                self.logger.log("INFO", f"Encoding new layer")
                self.gen.d = self.curr_depth
                # encode new layer (depth-1) and connect inter[depth-1] to inter[depth]
                selection_variables, bool_variables = self.gen.add_selection_variables(self.curr_depth-1, self.gate_set, self.q)
                if self.complex_representation == Complex:
                    if self.layer_bigM == 1:
                        self.layer_bigM = 4
                    self.layer_bigM = self.layer_bigM
                else:
                    self.layer_bigM = self.layer_bigM * 2
                for pair_idx in range(len(vector_pairs)):
                    if self.curr_depth > self.d: # new vector needs to be added
                        state = None
                        if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            state = class_to_use(q=2**self.q, name=f"I_{pair_idx}_{self.curr_depth}", generator=self.gen, element_representation=self.complex_representation, k=0, n = input_state.n, bound = self.bound, k_bound = 2 * (self.curr_depth+1))
                        else:
                            state = class_to_use(q=2**self.q, name=f"I_{pair_idx}_{self.curr_depth}", generator=self.gen, element_representation=self.complex_representation, bound = self.bound, k_bound = 2 * (self.curr_depth+1))
                        weight_bound = weight_bound + max_weight
                        weights.append(self.gen.declare_integer(f"W{self.curr_depth}", lb=0, ub=weight_bound))
                        inter_states[pair_idx].append(state)
     
                    # encode the layer
                    self.encode_layer(inter_states[pair_idx][self.curr_depth-1], inter_states[pair_idx][self.curr_depth], self.curr_depth-1, weights[self.curr_depth-1], weights[self.curr_depth], selection_variables, bool_variables)
                
                self.logger.log("INFO", f"Encoded layer {self.curr_depth-1}")

                    # constraints do not have any effect on incremental synthesis
                    #self.gen.add_constraints(self.gate_set, self.curr_depth-1, self.q)
                if self.complex_representation != Complex:
                    self.bound = self.bound * 2
                    
                self.logger.log("INFO", f"Pushing depth {self.curr_depth}")
                self.gen.push()
                self.logger.log("INFO", f"Pushed depth {self.curr_depth}")
                
                if self.encoding_method == "pareto-incremental":
                    self.logger.log("INFO", f"Encoding equivalence for depth {self.curr_depth}")
                    self.encode_equivalence(inter_states, target_states, self.curr_depth)
                    self.logger.log("INFO", f"Encoded equivalence for depth {self.curr_depth}")
                    self.logger.log("INFO", f"Writing formula for depth {self.curr_depth}")
                    formula_file = self.gen.write_formula(output_qasm)
                    self.logger.log("INFO", f"Formula written for depth {self.curr_depth}")

                    # enumerate models for this depth
                    sat = True
                    self.logger.log("INFO", f"Enumerating models for depth {self.curr_depth}")
                    while sat:
                        result, circuit, vectors = self.pareto_front.start(
                            lambda: self.solve_and_extract_circuit(
                                formula_file=formula_file,
                                output_qasm=output_qasm,
                                write_to_file=True,
                                draw_circuit=False,
                            )
                        )
                        if self.pareto_front.timeout_met():
                            self.pareto_front.cleanup()
                            return True, None, None
                        if not result:
                            sat = False # last model found
                        else:
                            # compute the cost, if RUS, also synthesize the recovery operation
                            cost_x, cost_y = 0.0, 0.0
                            if self.vector_mode == "rus":
                                # synthesize recovery operation
                                measured_states = []
                                for state in states:
                                    measured_states.append(state.measure(self.qubits_to_measure, 1)) # measure ancilla to 1, indicating failure
                                    
                                states_recovery = []
                                for pair_idx in range(len(vector_pairs)):
                                    # create input state from the post-measurement state
                                    states_recovery.append((measured_states[pair_idx].to_precision(1e-8), inter_states[pair_idx][0].to_precision(1e-8)))
                                try:
                                    print(states_recovery)
                                    synthesizer = Synthesizer()
                                    gate_set = GateSet.union(self.gate_set, GateSet(preset="Clifford+T"))
                                    gate_set.set_t_optimal()
                                    res_recovery, recovery_circuit, recovery_vectors = self.pareto_front.start(
                                        lambda: synthesizer.synthesis(
                                            vector_pairs=states_recovery,
                                            vectors="custom",
                                            q=self.q,
                                            d=self.d,
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
                                        self.pareto_front.cleanup()
                                        return True, None, None
                                    if not res_recovery:
                                        recovery_circuit = Circuit(gates=[], q=self.q, d=self.d)
                                        recovery_circuit.cost = np.inf
                                except Exception as e:
                                    recovery_circuit = Circuit(gates=[], q=self.q, d=self.d)
                                    recovery_circuit.cost = np.inf
                                    
                                cost_x, cost_y = self.rus_cost(circuit, recovery_circuit, vectors)
                            else:
                                cost_x, cost_y = self.circuit_cost(circuit)
                            # add the point to the pareto front and filter the model
                            self.pareto_front.add_point(cost_x, cost_y, self.curr_depth, circuit, recovery_circuit)
                            self.gen.filter_model(circuit.bool_variables, self.curr_depth)
                    self.gen.pop()
                    self.curr_depth += 1
                            
                else:
                    self.logger.log("INFO", f"Encoding equivalence for depth {self.curr_depth}")
                    self.encode_equivalence(inter_states, target_states, self.curr_depth)
                    self.logger.log("INFO", f"Encoded equivalence for depth {self.curr_depth}")

                    # without objective
                    self.logger.log("INFO", f"Writing formula for depth {self.curr_depth}")
                    formula_file = self.gen.write_formula(output_qasm)
                    self.logger.log("INFO", f"Formula written for depth {self.curr_depth}")
                    encoding_end = time.time()
                    self.logger.update_time("encoding", encoding_end - encoding_start)
                    result, circuit, vectors = self.solve_and_extract_circuit(formula_file=formula_file, output_qasm=output_qasm, write_to_file=True)
                    if result:
                        res = True
                    else:
                        # remove rescaled_... variables from the problem
                        self.logger.log("INFO", f"Popping depth {self.curr_depth}")
                        self.gen.pop()
                        self.logger.log("INFO", f"Popped depth {self.curr_depth}")
                        self.curr_depth += 1
            if self.encoding_method == "pareto-incremental":
                self.pareto_front.cleanup()
        else:
            raise ValueError(f"Invalid encoding method: {self.encoding_method}")

        if circuit is not None:
            circuit.add_measurement(self.qubits_to_measure)
        return res, circuit, vectors

    def binary_cost_search(self, weights, formula_file="formula.smt2", output_qasm="circuit.qasm"):
        solved = []
        unsolved = []
        lower_bound = 0
        upper_bound = self.d+1
        best_circuit = None
        best_vectors = None
        while True:
            middle = lower_bound + (upper_bound - lower_bound) // 2
            if lower_bound + 1 >= upper_bound:
                # found the optimal depth -- upper bound is the best solution
                if lower_bound not in solved and lower_bound not in unsolved:
                    middle = lower_bound # dont know anything about the result
                elif lower_bound not in solved and upper_bound not in solved:
                    middle = upper_bound # know that the result is unsat
                else:
                    break
            self.gen.push()
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
        while i < self.d+2:
            self.gen.push()
            self.gen.add_assertion(self.gen.LE(weights[self.d], self.gen.Int(i)))
            formula_file = self.gen.write_formula(output_qasm)
                 
            result, circuit, vectors = self.solve_and_extract_circuit(formula_file=formula_file, output_qasm=output_qasm, write_to_file=True)                
            if result:
                return result, circuit, vectors
            self.gen.pop()
            i += 1

        return False, None, None

    def incremental_top_down_cost_search(self, weights, formula_file="formula.smt2", output_qasm="circuit.qasm"):
        i = self.d+1
        best_circuit = None
        best_vectors = None
        while i >= 0:
            self.gen.push()
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

    def solve_and_extract_circuit(self, formula_file="formula.smt2", output_qasm="circuit.qasm", write_to_file = True, draw_circuit = False) -> bool:
        """    
            formula_file: Path to the formula file
            output_qasm: Output filename for QASM circuit
            solver: z3, z3alpha, cvc5, opensmt, smtinterpol, yices2, dreal (experimental)
        """
        solving_start = time.time()
        self.logger.log("INFO", f"Solving formula")
        result = self.gen.check_sat(formula_file)
        self.logger.log("INFO", f"Solving finished")
        solving_end = time.time()
        self.logger.update_time("solving", solving_end - solving_start)
        if result:
            parsing_start = time.time()
            self.logger.log("INFO", f"Parsing model")
            model = self.gen.get_model()
            res = self.parser.parse(model, self.q, self.curr_depth, output_qasm, self.complex_representation, write_to_file=write_to_file, draw_circuit=draw_circuit, v=self.v)
            parsing_end = time.time()
            self.logger.update_time("parsing", parsing_end - parsing_start)
            self.logger.log("INFO", f"Parsing finished")
            return res
        else:
            return False, None, None