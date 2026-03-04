"""
@file: synth.py
@author: Jakub Havlík
@date: 24.02.2026
@brief: quantum circuit synthesis using SMT and MILP solving
"""

from complex.classic import Complex
from complex.vector import Vector
from complex.fivetuple import FiveTuple
from complex.ntuple import nTuple
from generator import Generator
from parser import ModelParser
import subprocess
from sim import Simulator
from multiprocessing import cpu_count
from pysmt.logics import QF_NRA, QF_LIA, QF_NIA
from pysmt.shortcuts import Portfolio, Symbol, Real, And, Equals, Plus, GT, LT, get_env, Int, Or, Not, Implies, GE, LE, Ite, Minus, Div, Times, write_smtlib
from pysmt.typing import REAL, INT
from pysmt.solvers.solver import Solver
from gates import GateSet, supported_gates, check_supported
from pulp import *


class Synthesizer:
    def __init__(self) -> None:
        self.gen = Generator()
        self.parser = ModelParser()
        self.gate_set = GateSet()
        self.simulator = None
        self.complex_representation = None
        self.solver = None
        self.fidelity_threshold = 1.0
        self.bound = (-1, 1)
        self.k_bound = (0, 1)
        self.q = None
        self.d = None
        self.max_k = 0
        self.encoding_method = None
        
    def __exit__(self) -> None:
        if self.gen.mode == "pysmt":
            self.gen.solver.exit() # portfolio is still alive
            
    def add_solvers(self) -> None:
        # register custom solvers for pySMT portfolio solving (TODO change for relative paths, change logics to match the respective solvers)
        env = get_env()
        # z3 already in pysmt
        path = ["/home/jakubhavlik/rus-synth/solvers/opensmt/opensmt"]
        env.factory.add_generic_solver(name="opensmt", args=path, logics=[QF_LIA])
        path = ["/home/jakubhavlik/rus-synth/solvers/yices2/yices_smt2"]
        env.factory.add_generic_solver(name="yices2", args=path, logics=[QF_LIA, QF_NRA, QF_NIA])
        path = ["/home/jakubhavlik/rus-synth/solvers/smtinterpol/smtinterpol"]
        env.factory.add_generic_solver(name="smtinterpol", args=path, logics=[QF_LIA, QF_NRA, QF_NIA])
        path = ["/home/jakubhavlik/rus-synth/solvers/cvc5/cvc5"]
        env.factory.add_generic_solver(name="cvc5", args=path, logics=[QF_LIA, QF_NRA, QF_NIA])
        path = ["/home/jakubhavlik/rus-synth/solvers/dreal/run_dreal.sh"]
        env.factory.add_generic_solver(name="dreal", args=path, logics=[QF_NRA])
        

    def encode_layer(self, inp : Vector, out : Vector, layer : int, inp_weight : any = None, out_weight : any = None) -> None:
        updates_k_value = []
        def add_implies(sel, expr):
            self.gen.add_assertion(self.gen.Implies(sel, expr))
        
        def add_k_eq(sel, out_k, inp_k):
            if self.gen.mode == "milp":
                return
            k_eq = self.gen.Equals(out_k, inp_k)
            self.gen.add_assertion(self.gen.Implies(sel, k_eq))
        
        def add_k_incr(sel, out_k, inp_k, increment):
            if self.gen.mode == "milp":
                updates_k_value.append((sel, self.gen.Int(increment)))
                return
            k_incr = self.gen.Equals(out_k, self.gen.Plus(inp_k, self.gen.Int(increment)))
            add_implies(sel, k_incr)
        
        def add_constrained_equals(sel, expr1, expr2):
            if self.gen.mode == "milp":
                self.complex_representation.constrained_equals(sel, expr1, expr2)
            else:
                self.gen.add_assertion(self.gen.Implies(sel, (expr1 == expr2)))

        if not check_supported(self.gate_set):
            raise ValueError("gate set contains an unsupported gate")

        selection_variables = []
        bool_variables = []
        self.gate_set.add_gate(gate="id", weight=0, qubits=1) #implicit identity gate
        variables = [(gate, q) for q in range(self.q) for gate in self.gate_set.get_gates(1)]
        for var in variables:
            v = self.gen.declare_bool(f"L{layer}_{var[0]}_q{var[1]}")
            selection_variable = (v, var)
            selection_variables.append(selection_variable)
            bool_variables.append(v)
        
        variables = [(gate, q1, q2) for q1 in range(self.q) for q2 in range(self.q) for gate in self.gate_set.get_gates(2) if q1 != q2]
        for var in variables:
            v = self.gen.declare_bool(f"L{layer}_{var[0]}_q{var[1]}_q{var[2]}")
            selection_variable = (v, var)
            selection_variables.append(selection_variable)
            bool_variables.append(v)
        
        variables = [(gate, q1, q2, q3) for q1 in range(self.q) for q2 in range(self.q) for q3 in range(self.q) if q1 != q2 and q1 != q3 and q2 != q3 for gate in self.gate_set.get_gates(3)]
        for var in variables:
            v = self.gen.declare_bool(f"L{layer}_{var[0]}_q{var[1]}_q{var[2]}_q{var[3]}")
            selection_variable = (v, var)
            selection_variables.append(selection_variable)
            bool_variables.append(v)
        
        # add constraints for only one gate per layer
        if self.gen.mode == "milp":
            self.gen.add_assertion(lpSum([bool_variable for bool_variable in bool_variables]) == 1)
        else:
            self.gen.add_assertion(self.gen.Or(*bool_variables))
            for v in bool_variables:
                others = [v2 for v2 in bool_variables if v2 != v]
                self.gen.add_assertion(self.gen.Implies(v, self.gen.And(*[self.gen.Not(v2) for v2 in others])))

        propagate_identities = []
        for pos in range(2**self.q):
            propagate_identities.append([])

        for selection_variable in selection_variables:
            bool_var = selection_variable[0]
            rest = selection_variable[1]
            gate = rest[0]
            if len(rest) == 2: # single qubit
                q = rest[1]
                if gate == 'id':
                    if self.gen.mode == "milp":
                        for pos in range(2**self.q):
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'h':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        add_constrained_equals(bool_var, out[pos], ((inp[pos] + inp[other]).divide_by_sqrt2(self.gen)))
                        add_constrained_equals(bool_var, out[other], ((inp[pos] + (inp[other].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen)))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 1)
                elif gate == 's':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sdg':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_minus_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 't':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_omega(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'tdg':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_omega_counter(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'x':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        add_constrained_equals(bool_var, out[pos], inp[other])
                        add_constrained_equals(bool_var, out[other], inp[pos])
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        add_constrained_equals(bool_var, out[pos], ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen)))
                        add_constrained_equals(bool_var, out[other], ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen)))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 2)
                elif gate == 'sxdg':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        add_constrained_equals(bool_var, out[pos], ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen)))
                        add_constrained_equals(bool_var, out[other], ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen)))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 2)
                elif gate == 'y':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        other = pos ^ (1 << q)
                        modified_positions.append(other)
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            add_constrained_equals(bool_var, out[pos], inp[other].multiply_by_i(self.gen))
                            add_constrained_equals(bool_var, out[other], inp[pos].multiply_by_minus_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        else:
                            add_constrained_equals(bool_var, out[pos], inp[other].multiply_by_minus_i(self.gen))
                            add_constrained_equals(bool_var, out[other], inp[pos].multiply_by_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'z':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_minus_one(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
            elif len(rest) == 3: # two qubit
                q1 = rest[1]
                q2 = rest[2]
                if gate == 'cx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        control_flag = (pos >> q1) & 1
                        if control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            add_constrained_equals(bool_var, out[pos], inp[other])
                            add_constrained_equals(bool_var, out[other], inp[pos])
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                            modified_positions.append(pos)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'xcx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if not control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            add_constrained_equals(bool_var, out[pos], inp[other])
                            add_constrained_equals(bool_var, out[other], inp[pos])
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'dcx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        other = None
                        if (not control_flag and not target_flag) and self.gen.mode == "milp":
                            other = pos
                        elif not control_flag and target_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                        elif control_flag and not target_flag:
                            other = pos ^ (1 << q2)
                        elif control_flag and target_flag:
                            other = pos ^ (1 << q1)
                        if other is None: continue
                        modified_positions.append(other)
                        add_constrained_equals(bool_var, out[other], inp[pos])
                        propagate_identities[other].append(bool_var)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'ch':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            add_constrained_equals(bool_var, out[pos], (inp[pos] + inp[other]).divide_by_sqrt2(self.gen))
                            add_constrained_equals(bool_var, out[other], (inp[pos] + (inp[other].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 1)
                elif gate == 'csx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if control_flag:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            add_constrained_equals(bool_var, out[pos], ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen)))
                            add_constrained_equals(bool_var, out[other], ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 2)
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
                                add_constrained_equals(bool_var, out[pos], inp[other].multiply_by_minus_i(self.gen))
                                add_constrained_equals(bool_var, out[other], inp[pos].multiply_by_i(self.gen))
                                propagate_identities[pos].append(bool_var)
                                propagate_identities[other].append(bool_var)
                            else:
                                add_constrained_equals(bool_var, out[pos], inp[other].multiply_by_i(self.gen))
                                add_constrained_equals(bool_var, out[other], inp[pos].multiply_by_minus_i(self.gen))
                                propagate_identities[pos].append(bool_var)
                                propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                        
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cz':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_minus_one(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cs':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'csdg':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_minus_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'swap':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        if q1_flag != q2_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            add_constrained_equals(bool_var, out[pos], inp[other])
                            add_constrained_equals(bool_var, out[other], inp[pos])
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'iswap':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        if q1_flag != q2_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            add_constrained_equals(bool_var, out[pos], inp[other].multiply_by_i(self.gen))
                            add_constrained_equals(bool_var, out[other], inp[pos].multiply_by_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sqrtswap':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        if q1_flag != q2_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            add_constrained_equals(bool_var, out[pos], ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen)))
                            add_constrained_equals(bool_var, out[other], ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen)))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        else:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_two(self.gen))
                            propagate_identities[pos].append(bool_var)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 2)
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
                            add_constrained_equals(bool_var, out[pos], inp[other])
                            add_constrained_equals(bool_var, out[other], inp[pos])
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cswap':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        q3_flag = (pos >> q3) & 1
                        if q1_flag and (q2_flag != q3_flag):
                            other = pos ^ ((1 << q2) | (1 << q3))
                            modified_positions.append(other)
                            add_constrained_equals(bool_var, out[pos], inp[other])
                            add_constrained_equals(bool_var, out[other], inp[pos])
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'ccz':
                    for pos in range(2**self.q):
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        q3_flag = (pos >> q3) & 1
                        if q1_flag and q2_flag and q3_flag:
                            add_constrained_equals(bool_var, out[pos], inp[pos].multiply_by_minus_one(self.gen))
                            propagate_identities[pos].append(bool_var)
                        elif self.gen.mode == "milp":
                            add_constrained_equals(bool_var, out[pos], inp[pos])
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
        # propagate identities for positions that were not modified by the chosen gate
        # (notG1 and notG2 and ...) -> (out[pos] == inp[pos])
        for pos in range(2**self.q):
            if self.gen.mode == "milp": # TODO: milp does not support propagation
                break
            if len(propagate_identities[pos]) == 0: # no gates modified this position, propagate identity
                expr = out[pos] == inp[pos]
                self.gen.add_assertion(expr)
            else:
                add_implies(self.gen.And(*[self.gen.Not(v) for v in propagate_identities[pos]]), out[pos] == inp[pos])
        
        # propagate the k update
        if self.gen.mode == "milp":
            self.gen.add_assertion(self.gen.Equals(out.k, self.gen.Plus(inp.k, lpSum([v[1] * v[0] for v in updates_k_value]))))

        # add gate weights
        if inp_weight is None or out_weight is None:
            return
        
        for selection_variable in selection_variables:
            if self.gen.mode == "milp": # rather than implications, add it directly as a sum
                break
            bool_var = selection_variable[0]
            gate = selection_variable[1][0]
            weight = self.gate_set.get_weight(gate)
            self.gen.add_assertion(self.gen.Implies(bool_var, self.gen.Equals(out_weight, self.gen.Plus(inp_weight, self.gen.Int(weight)))))
        
        if self.gen.mode == "milp":
            self.gen.add_assertion(self.gen.Equals(out_weight, self.gen.Plus(inp_weight, lpSum([self.gate_set.get_weight(v[1][0]) * v[0] for v in selection_variables]))))

    def encode_equivalence(self, vec1, vec2, pair_idx):
        conj_rescaled1 = None
        rescaled1 = None
        rescaled2 = None
        if self.gen.logic == "QF_NRA": 
        # FIDELITY
            fidelity = Complex(a=1.0, b=0.0, name="Fidelity", generator=self.gen)
            conjugate = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Conjugate")
            self.gen.add_assertion(conjugate == vec1.conjugate(self.gen))
            self.gen.add_assertion(self.gen.Equals(conjugate.k, vec1.k))
            prod, k_final = conjugate * vec2
            prod_real = prod.abs2(k_final) # abs2 <==> fidelity
            self.gen.add_assertion(self.gen.Equals(self.gen.Real(fidelity.real), self.gen.Real(prod_real)))
            self.gen.add_assertion(self.gen.GE(self.gen.Real(fidelity.real), self.gen.Real(0.0)))
            self.gen.add_assertion(self.gen.LE(self.gen.Real(fidelity.real), self.gen.Real(1.0)))
            self.gen.add_assertion(self.gen.GE(self.gen.Real(fidelity.real), self.gen.Real(self.fidelity_threshold)))
        elif self.gen.mode == "milp":
            rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{vec1.name}")
            rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{vec2.name}")
            self.gen.add_milp_rescaling(rescaled1, rescaled2, vec1, vec2, pair_idx, self.max_k)
            for i in range(2**self.q):
                self.gen.add_assertion(self.gen.Equals(rescaled1[i], rescaled2[i]))
        elif self.gen.logic == "QF_LIA" or self.gen.logic == "QF_NIA":
            # QF_LIA and QF_NIA branch -- enumarates all possible outcomes for 2^(floor(n/2)), allowing rescaling by constant
            # other approach enumerates all possible powers of 2, then calculates 2^(floor(abs(k1 - k2)/2)) * M * vector
            rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{vec1.name}")
            rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{vec2.name}")
            self.gen.add_rescaling(rescaled1, rescaled2, vec1, vec2, pair_idx, self.max_k)
            self.gen.add_assertion(rescaled1 == rescaled2)
        


    def set_initial_values(self):
        for i, (gate, qubits) in enumerate(self.simulator.stats['input_circuit']):
            bool_var_str = f"L{i}_{gate}"
            for qubit in qubits:
                bool_var_str += f"_q{qubit}"
            bool_var = self.gen.declare_bool(bool_var_str)
            bool_var.setInitialValue(1)
    
    def synthesis(self, qasm_file=None, vectors=None, vector_pairs=None, solving="portfolio", solver=None, mode="incremental", output_qasm="circuit.qasm", 
                  complex_representation="FiveTuple", gate_set=None, q=None, d=None, fidelity_threshold=1.0) -> bool:
        """
            qasm_file -> file to synthesize
            vectors -> specify what set of input vectors to use (zero -> only |0>^n state, all -> all cbs, rus -> |0>, |1>, |+> on target, |0> on ancillas, custom -> has to specify vector_pairs, q, d, gate_set)
            vector_pairs -> list of pairs (input_vector, output_vector) for input and its expected output.
            solving -> specify if smt (has to specify solver), portfolio (of smt solvers), milp (specify milp solver TODO: now only gurobi)
            mode -> specify solving method (basic -> create whole formula and get the best model, incremental -> incrementally generate the formula, binary, topdown, bottomup -> searches to optimize cost function)
            output_qasm -> file to write the output circuit to
            complex_representation -> specify the complex representation ["FiveTuple", "nTuple", "Classic"]
            gate_set -> specify the gate set to use using the GateSet class, otherwise, the gate set is taken from the input qasm file
            q -> number of qubits of the output circuit (has to correspond to the vector_pairs size)
            d -> number of allowed gates in the output circuit
            fidelity_threshold -> solver=dreal and mode=smtlib uses QF_NRA and fidelity instead of exact equivalence
        """
        if qasm_file is None:
            raise ValueError("input qasm_file is required")
        
        if vectors is None:
            raise ValueError("provide vectors to select vector-mode")
        if vectors in ["zero", "all", "rus"] and vector_pairs is not None:
            raise ValueError("vector_pairs cannot be provided when vectors are specified")
        if vectors == "custom" and (vector_pairs is None or q is None or d is None or gate_set is None):
            raise ValueError("vector_pairs, q, d, and gate_set are required when vectors are custom")
        if solving in ["smt", "milp"] and solver is None:
            raise ValueError("a solver is required for basic smt and milp solving")
        if solving == "portfolio" and solver is not None:
            raise ValueError("portfolio uses a set of predefined solvers [opensmt, z3, z3alpha, cvc5, yices2, smtinterpol]")
        if mode not in ["basic", "incremental", "binary", "topdown", "bottomup"]:
            raise ValueError("mode can be only basic, incremental, binary, topdown, or bottomup")
        if mode in ["binary", "topdown", "bottomup"] and solving != "portfolio": # TODO
            raise ValueError("mode binary, topdown, bottomup requires portfolio solving")
        if complex_representation not in ["FiveTuple", "nTuple", "Classic"]:
            raise ValueError("complex_representation can be only FiveTuple, nTuple, or Classic")
        if complex_representation == "FiveTuple":
            self.complex_representation = FiveTuple
        elif complex_representation == "nTuple":
            self.complex_representation = nTuple
        elif complex_representation == "Classic":
            self.complex_representation = Classic
        
        # set circuit statistics to prepare synthesis
        self.simulator = Simulator(qasm_file, complex_representation=self.complex_representation)
        if vectors in ["zero", "all", "rus"]:
            if vectors == "zero":
                vector_pairs = self.simulator.simulate_zero()
            elif vectors == "all":
                print("Simulating all cbs")
                vector_pairs = self.simulator.simulate_circuit()
            elif vectors == "rus":
                vector_pairs = self.simulator.simulate_rus()
            
            stats = self.simulator.circuit_stats()
            print(stats)
            if gate_set is None:
                gate_set = stats['gate_set']
            self.gate_set = gate_set
            self.q = stats['q']
            self.d = stats['d']
            self.max_k = 2*self.d if 2*self.d > stats['max_k'] else stats['max_k']
        else:
            self.q = q
            self.d = d
            self.max_k = 2*self.d
            self.gate_set = gate_set
        
        # set generator mode and solver
        if solving == "smt":
            if solver not in ["z3", "cvc5", "yices2", "opensmt", "smtinterpol", "dreal"]:
                raise ValueError(f"Invalid solver: {solver}")
            if solver == "dreal":
                self.gen.logic = "QF_NRA"
                self.fidelity_threshold = fidelity_threshold
            else:
                self.gen.logic = "QF_LIA"
            self.gen.solver = solver
            self.gen.mode = "smtlib"
        elif solving == "portfolio":
            self.gen.mode = "pysmt"
            self.add_solvers()
            solvers = ["z3", "cvc5", "yices2", "opensmt", "smtinterpol"]
            self.gen.solver = Portfolio(solvers, logic=self.gen.logic, incremental=True, generate_models=True)
        elif solving == "milp":
            self.gen.mode = "milp"
            self.gen.solver = solver
        
        # start synthesis
        res = False
        self.encoding_method = mode
        return self._synth(vector_pairs, output_qasm)
        if mode == "basic":
            res = self.basic_synthesis(vector_pairs, output_qasm)
        elif mode == "incremental":
            res = self.synthesis_incremental(vector_pairs, output_qasm)
        elif mode in ["binary", "topdown", "bottomup"]:
            res = self.synthesis_weights(vector_pairs, output_qasm, mode=mode)
        
        if solving == "portfolio":
            self.gen.solver.exit()
        return res
    
    def _synth(self, vector_pairs, output_qasm="circuit.qasm") -> bool:
        
        # encode weights
        weights = []
        weight_bound = 0
        max_weight = self.gate_set.max_weight()
        for i in range(self.d + 1):
            weight_bound = weight_bound + max_weight
            weights.append(self.gen.declare_integer(f"W{i}", lb=0, ub=weight_bound))
        # initial cost of the circuit is 0
        self.gen.add_assertion(self.gen.Equals(weights[0], self.gen.Int(0)))
        
        # encode vectors
        inter_vectors = []
        target_vectors = []
        for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
            # input vector
            In = Vector(q=2**self.q, name=f"In_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k, n=input_vector.n)
            for i, val in enumerate(input_vector.vec):
                self.gen.add_assertion(In[i] == val)
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                self.gen.add_assertion(self.gen.Equals(In.k, self.gen.format_integer(input_vector.k)))
            
            # encode intermediate vectors, bind the first one to the input vector
            inter = [None] * (self.d + 1)
            for d in range(self.d + 1):
                vec = None
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    vec = Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k if d == 0 else 0, n = input_vector.n)
                else:
                    vec = Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation)
                
                if d == 0:
                    if self.gen.mode == "milp":
                        for i in range(2**self.q):
                            self.gen.add_assertion(self.gen.Equals(vec[i], In[i]))
                        self.gen.add_assertion(self.gen.Equals(vec.k, In.k))
                    else:
                        self.gen.add_assertion(vec == In)
                inter[d] = vec
            
            inter_vectors.append(inter)
                
            # encode target vectors
            Target = Vector(q=2**self.q, name=f"Target_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = output_vector.k, n = output_vector.n)
            for i, val in enumerate(output_vector.vec):
                self.gen.add_assertion(Target[i] == val)
            
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                self.gen.add_assertion(self.gen.Equals(Target.k, self.gen.format_integer(output_vector.k)))
            
            target_vectors.append(Target)
        
        res = False # output result
        # based on chosen method, encode layers and equivalence
        if self.encoding_method == "basic" or self.encoding_method in ["binary", "topdown", "bottomup"]:
            # encode whole circuit
            for d in range(self.d):
                for pair_idx in range(len(vector_pairs)):
                    self.encode_layer(inter_vectors[pair_idx][d], inter_vectors[pair_idx][d+1], d, weights[d], weights[d+1])
                # add constraining rules - no H H, Tdg T, ...
                self.gen.add_constraints(self.gate_set, d, self.q)
            
            for pair_idx in range(len(vector_pairs)):
                self.encode_equivalence(inter_vectors[pair_idx][self.d], target_vectors[pair_idx], pair_idx)
            # fully encoded (except for the weight bound), save the formula
            if self.gen.mode == "milp":
                self.gen.add_objective(weights[self.d])
                self.set_initial_values()
                formula_file = output_qasm.split(".")[0] + ".lp"
                self.gen.lp_problem.writeLP(formula_file)
            else:
                formula_file = output_qasm.split(".")[0] + ".smt2"
                self.gen.write_smtlib(formula_file)
            
            if self.encoding_method == "basic":
                res = self.solve_and_extract_circuit(output_qasm=output_qasm, formula_file=formula_file)
            elif self.encoding_method == "binary":
                res = self.binary_cost_search(weights, output_qasm=output_qasm, formula_file=formula_file)
            elif self.encoding_method == "topdown":
                res = self.incremental_top_down_cost_search(weights, output_qasm=output_qasm, formula_file=formula_file)
            elif self.encoding_method == "bottomup":
                res = self.incremental_bottom_up_cost_search(weights, output_qasm=output_qasm, formula_file=formula_file)
        
        elif self.encoding_method == "incremental":
            # incrementally generate circuit and equivalence
            depth = 1
            while depth <= self.d and not res:
                print(f"Trying depth: {depth}")
                for pair_idx in range(len(vector_pairs)):
                    # encode new layer (depth-1) and connect inter[depth-1] to inter[depth]
                    self.encode_layer(inter_vectors[pair_idx][depth-1], inter_vectors[pair_idx][depth], depth-1, weights[depth-1], weights[depth])
                    self.gen.add_constraints(self.gate_set, depth-1, self.q)
                self.gen.push()
                for pair_idx in range(len(vector_pairs)):
                    self.encode_equivalence(inter_vectors[pair_idx][depth], target_vectors[pair_idx], pair_idx)
            
                if self.gen.mode == "milp":
                    self.gen.add_objective(weights[depth])
                    formula_file = output_qasm.split(".")[0] + ".lp"
                    self.gen.lp_problem.writeLP(formula_file)
                else:
                    formula_file = output_qasm.split(".")[0] + ".smt2"
                    self.gen.write_smtlib(formula_file)                
                result = self.solve_and_extract_circuit(formula_file=formula_file, output_qasm=output_qasm)
                if result:
                    res = True
                else:
                    self.gen.pop()
                    depth += 1
        else:
            raise ValueError(f"Invalid encoding method: {self.encoding_method}")
        
        if self.gen.mode == "pysmt":
            self.gen.solver.exit()
        return res

    def binary_cost_search(self, weights, formula_file="formula.smt2", output_qasm="circuit.qasm"):
        solved = []
        unsolved = []
        lower_bound = 0
        upper_bound = self.d+1
        best_model = None
        while True:
            print(f"Lower bound: {lower_bound}, Upper bound: {upper_bound}")
            print(f"Solved: {solved}, Unsolved: {unsolved}")
            middle = lower_bound + (upper_bound - lower_bound) // 2
            if lower_bound + 1 >= upper_bound:
                # found the optimal depth -- upper bound is the best solution
                if lower_bound not in solved and lower_bound not in unsolved:
                    middle = lower_bound # dont know anything about the result
                elif lower_bound not in solved and upper_bound not in solved:
                    middle = upper_bound # know that the result is unsat
                else:
                    break
            self.gen.solver.push()
            self.gen.add_assertion(self.gen.LT(weights[self.d], self.gen.Int(middle)))
            result = self.gen.solver.solve()                       
            if result:
                upper_bound = middle
                # save the best circuit so far
                best_model = self.gen.solver.get_model()
                solved.append(middle)
            else:
                lower_bound = middle
                unsolved.append(middle)
            self.gen.solver.pop()

        if best_model is not None:
            self.parser.parse(best_model, self.q, self.d, output_qasm)
            return True
        else:
            return False
        
    def incremental_bottom_up_cost_search(self, weights, formula_file="formula.smt2", output_qasm="circuit.qasm"):
        i = 0
        while i < self.d+2:
            self.gen.solver.push()
            self.gen.add_assertion(self.gen.LT(weights[self.d], self.gen.Int(i)))
            result = self.gen.solver.solve()
            if result:
                self.parser.parse(self.gen.solver.get_model(), self.q, self.d, output_qasm)
                return True
            self.gen.solver.pop()
            i += 1

        return False

    def incremental_top_down_cost_search(self, weights, formula_file="formula.smt2", output_qasm="circuit.qasm"):
        i = self.d+1
        best_model = None
        while i > 0:
            print(f"Trying cost: {i}")
            self.gen.solver.push()
            self.gen.add_assertion(self.gen.LT(weights[self.d], self.gen.Int(i)))
            result = self.gen.solver.solve()
            if result:
                best_model = self.gen.solver.get_model()
            else:
                # first unsolvable, return best model
                if best_model is not None:
                    self.parser.parse(best_model, self.q, self.d, output_qasm)
                    return True
                else:
                    return False
            self.gen.solver.pop()
            i -= 1

        return False

    def solve_and_extract_circuit(self, formula_file="formula.smt2", output_qasm="circuit.qasm", solver=None) -> bool:
        """    
            formula_file: Path to the formula file
            output_qasm: Output filename for QASM circuit
            solver: z3, z3alpha, cvc5, opensmt, smtinterpol, yices2, dreal (experimental)
        """
        result = None
        if self.gen.mode == "milp":
            if solver is None:
                solver = "gurobi"
            solver_to_class = {
                "gurobi": GUROBI,
                "cbc": PULP_CBC_CMD,
            }
            solver = solver_to_class[solver](msg=False)
            solver.solve(self.gen.lp_problem)
            if LpStatus[self.gen.lp_problem.status].lower() == "optimal":
                print(f"Solver status: {LpStatus[self.gen.lp_problem.status]}")
                return self.parser.parse(self.gen, self.q, self.d, output_qasm)
            elif LpStatus[self.gen.lp_problem.status].lower() == "infeasible":
                return False
            else:
                raise ValueError(f"Solver status: {LpStatus[self.gen.lp_problem.status]}")

        elif self.gen.mode == "smtlib":
            solver_to_filename = {
                "z3": "z3",
                "z3alpha": "/home/jakubhavlik/rus-synth/solvers/z3alpha/z3alpha.py",
                "cvc5": "/home/jakubhavlik/rus-synth/solvers/cvc5/starexec_run_sq",
                "opensmt": "/home/jakubhavlik/rus-synth/solvers/opensmt/opensmt",
                "smtinterpol": "/home/jakubhavlik/rus-synth/solvers/smtinterpol/smtinterpol",
                "yices2": "/home/jakubhavlik/rus-synth/solvers/yices2/yices_smt2",
                "dreal": "/opt/dreal/4.21.06.2/bin/dreal"
            }
            
            if solver is None and self.gen.solver is not None:
                solver = self.gen.solver
            else:
                raise ValueError("solver is not set")

            jobs = cpu_count()
            if jobs is None:
                jobs = 1
            args = {
                "dreal": [ "-j",  str(jobs), "--precision", "1e-6", "--produce-models"]
            }
            if solver not in solver_to_filename:
                raise ValueError(f"Invalid solver: {solver}")
            try:
                result = subprocess.run(
                    [solver_to_filename[solver], formula_file] + args.get(solver, []),
                    capture_output=True,
                    text=True,
                )
            except Exception as e:
                raise ValueError(f"Error: {e}")
                return False
            if result is None:
                return False
            self.parser.parse(result.stdout, self.q, self.d, output_qasm)
            return True
        elif self.gen.mode == "pysmt":
            result = self.gen.solver.solve()
            if result:
                model = self.gen.solver.get_model()
                self.parser.parse(model, self.q, self.d, output_qasm)
                return True
            else:
                return False