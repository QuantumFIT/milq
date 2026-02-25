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


class Synthesizer:
    def __init__(self, gate_set : GateSet = None, solver : str = None, fidelity_threshold : int = 1.0) -> None:
        self.gen = Generator()
        if solver is not None:
            self.gen.mode = "smtlib"
        if solver == "dreal":
            self.gen.logic = "QF_NRA"

        self.parser = ModelParser()
        self.gate_set = gate_set
        self.simulator = None
        self.complex_representation = FiveTuple
        self.solver = solver
        self.fidelity_threshold = fidelity_threshold
        self.q = None
        self.d = None
        self.max_k = 0
            
    def add_solvers(self) -> None:
        # register custom solvers for pySMT portfolio solving (TODO change for relative paths, change logics to match the respective solvers)
        env = get_env()
        # z3 already in pysmt
        path = "/home/jakubhavlik/rus-synth/solvers/opensmt/opensmt"
        env.factory.add_generic_solver("opensmt", path, [QF_LIA])
        path = "/home/jakubhavlik/rus-synth/solvers/yices2/yices_smt2"
        env.factory.add_generic_solver("yices2", path, [QF_LIA, QF_NRA, QF_NIA])
        path = "/home/jakubhavlik/rus-synth/solvers/smtinterpol/smtinterpol"
        env.factory.add_generic_solver("smtinterpol", path, [QF_LIA, QF_NRA, QF_NIA])
        path = "/home/jakubhavlik/rus-synth/solvers/cvc5/cvc5"
        env.factory.add_generic_solver("cvc5", path, [QF_LIA, QF_NRA, QF_NIA])
        path = "/home/jakubhavlik/rus-synth/solvers/dreal/run_dreal.sh"
        env.factory.add_generic_solver("dreal", path, [QF_NRA])
        

    def encode_layer(self, inp : Vector, out : Vector, layer : int, inp_weight : any = None, out_weight : any = None) -> None:
        def add_implies(sel, expr):
            self.gen.add_assertion(self.gen.Implies(sel, expr))
        
        def add_k_eq(sel, out_k, inp_k):
            k_eq = self.gen.Equals(out_k, inp_k)
            self.gen.add_assertion(self.gen.Implies(sel, k_eq))
        
        def add_k_incr(sel, out_k, inp_k, increment):
            k_incr = self.gen.Equals(out_k, self.gen.Plus(inp_k, self.gen.Int(increment)))
            add_implies(sel, k_incr)

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
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'h':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        expr1 = out[pos] == ((inp[pos] + inp[other]).divide_by_sqrt2(self.gen))
                        expr2 = out[other] == ((inp[pos] + (inp[other].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                        add_implies(bool_var, expr1)
                        add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 1)
                elif gate == 's':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            expr = out[pos] == inp[pos].multiply_by_i(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sdg':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            expr = out[pos] == inp[pos].multiply_by_minus_i(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 't':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            expr = out[pos] == inp[pos].multiply_by_omega(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'tdg':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            expr = out[pos] == inp[pos].multiply_by_omega_counter(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'x':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        expr1 = out[pos] == inp[other]
                        expr2 = out[other] == inp[pos]
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                        add_implies(bool_var, expr1)
                        add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        expr1 = out[pos] == ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))
                        expr2 = out[other] == ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                        add_implies(bool_var, expr1)
                        add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 2)
                elif gate == 'sxdg':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        other = pos ^ (1 << q)
                        modified_positions.append(pos)
                        modified_positions.append(other)
                        expr1 = out[pos] == ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))
                        expr2 = out[other] == ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))
                        propagate_identities[pos].append(bool_var)
                        propagate_identities[other].append(bool_var)
                        add_implies(bool_var, expr1)
                        add_implies(bool_var, expr2)
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
                            expr1 = out[pos] == inp[other].multiply_by_i(self.gen)
                            expr2 = out[other] == inp[pos].multiply_by_minus_i(self.gen)
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
                        else:
                            expr1 = out[pos] == inp[other].multiply_by_minus_i(self.gen)
                            expr2 = out[other] == inp[pos].multiply_by_i(self.gen)
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'z':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            expr = out[pos] == inp[pos].multiply_by_minus_one(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
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
                            expr1 = out[pos] == inp[other]
                            expr2 = out[other] == inp[pos]
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
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
                            expr1 = out[pos] == inp[other]
                            expr2 = out[other] == inp[pos]
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
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
                        if not control_flag and target_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                        elif control_flag and not target_flag:
                            other = pos ^ (1 << q2)
                        elif control_flag and target_flag:
                            other = pos ^ (1 << q1)
                        if other is None: continue
                        modified_positions.append(other)
                        expr = out[other] == inp[pos]
                        propagate_identities[other].append(bool_var)
                        add_implies(bool_var, expr)
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
                            expr1 = out[pos] == (inp[pos] + inp[other]).divide_by_sqrt2(self.gen)
                            expr2 = out[other] == (inp[pos] + (inp[other].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen)
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
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
                            expr1 = out[pos] == ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))
                            expr2 = out[other] == ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
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
                                expr1 = out[pos] == inp[other].multiply_by_minus_i(self.gen)
                                expr2 = out[other] == inp[pos].multiply_by_i(self.gen)
                                propagate_identities[pos].append(bool_var)
                                propagate_identities[other].append(bool_var)
                                add_implies(bool_var, expr1)
                                add_implies(bool_var, expr2)
                            elif control_flag and target_flag:
                                expr1 = out[pos] == inp[other].multiply_by_i(self.gen)
                                expr2 = out[other] == inp[pos].multiply_by_minus_i(self.gen)
                                propagate_identities[pos].append(bool_var)
                                propagate_identities[other].append(bool_var)
                                add_implies(bool_var, expr1)
                                add_implies(bool_var, expr2)
                        
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cz':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            expr = out[pos] == inp[pos].multiply_by_minus_one(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cs':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            expr = out[pos] == inp[pos].multiply_by_i(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'csdg':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            expr = out[pos] == inp[pos].multiply_by_minus_i(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
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
                            expr1 = out[pos] == inp[other]
                            expr2 = out[other] == inp[pos]
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
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
                            expr1 = out[pos] == inp[other].multiply_by_i(self.gen)
                            expr2 = out[other] == inp[pos].multiply_by_i(self.gen)
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
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
                            expr1 = out[pos] == ((inp[pos] + inp[other]).divide_by_two(self.gen) + (inp[pos] - inp[other]).divide_by_two_i(self.gen))
                            expr2 = out[other] == (((inp[pos] + inp[other])).divide_by_two(self.gen) + (inp[other] - inp[pos]).divide_by_two_i(self.gen))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 2)
                elif gate == 'isqrtswap':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        if q1_flag != q2_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            exp1 = out[pos] == ((inp[pos] + (inp[other].multiply_by_i(self.gen))).divide_by_sqrt2(self.gen))
                            expr2 = out[other] == ((inp[pos].multiply_by_i(self.gen) + inp[other]).divide_by_sqrt2(self.gen))
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 1)
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
                            expr1 = out[pos] == inp[other]
                            expr2 = out[other] == inp[pos]
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
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
                            expr1 = out[pos] == inp[other]
                            expr2 = out[other] == inp[pos]
                            propagate_identities[pos].append(bool_var)
                            propagate_identities[other].append(bool_var)
                            add_implies(bool_var, expr1)
                            add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'ccz':
                    for pos in range(2**self.q):
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        q3_flag = (pos >> q3) & 1
                        if q1_flag and q2_flag and q3_flag:
                            expr = out[pos] == inp[pos].multiply_by_minus_one(self.gen)
                            propagate_identities[pos].append(bool_var)
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
        # propagate identities for positions that were not modified by the chosen gate
        # (notG1 and notG2 and ...) -> (out[pos] == inp[pos])
        for pos in range(2**self.q):
            if len(propagate_identities[pos]) == 0: # no gates modified this position, propagate identity
                expr = out[pos] == inp[pos]
                self.gen.add_assertion(expr)
            else:
                add_implies(self.gen.And(*[self.gen.Not(v) for v in propagate_identities[pos]]), out[pos] == inp[pos])
        
        # add gate weights
        if inp_weight is None or out_weight is None:
            return
        
        for selection_variable in selection_variables:
            bool_var = selection_variable[0]
            gate = selection_variable[1][0]
            weight = self.gate_set.get_weight(gate)
            self.gen.add_assertion(self.gen.Implies(bool_var, self.gen.Equals(out_weight, self.gen.Plus(inp_weight, self.gen.Int(weight)))))
        

    def synthesis(self, qasm_file, output_qasm="circuit.qasm"):
        self.simulator = Simulator(qasm_file, complex_representation=self.complex_representation)
        vector_pairs = self.simulator.simulate_circuit()
        stats = self.simulator.circuit_stats()
        self.gate_set = stats['gate_set']
        self.q = stats['q']
        self.d = stats['d']
        self.max_k = self.d if self.d > stats['max_k'] else stats['max_k']
        #self.gen.mode = "smtlib"
        #self.basic_synthesis(vector_pairs)
        #res = self.solve_and_extract_circuit("formula.smt2", output_qasm, solver="opensmt")
        res = self.synthesis_incremental(vector_pairs, output_qasm)
        #res = self.synthesis_weights(vector_pairs, output_qasm, mode="binary")
        #res = self.synthesis_weights(vector_pairs, output_qasm, mode="bottom_up")
        #res = self.synthesis_weights(vector_pairs, output_qasm, mode="top_down")
        return res
    
    def synthesis_zero(self, qasm_file, output_qasm="circuit.qasm"):
        self.simulator = Simulator(qasm_file, complex_representation=self.complex_representation)
        vector_pairs = self.simulator.simulate_zero()
        stats = self.simulator.circuit_stats()
        self.gate_set = stats['gate_set']
        self.q = stats['q']
        self.d = stats['d']
        self.max_k = self.d if self.d > stats['max_k'] else stats['max_k']
        #res = self.synthesis_incremental(vector_pairs, output_qasm)
        #self.gen.mode = "smtlib"
        #self.basic_synthesis(vector_pairs)
        #res = self.solve_and_extract_circuit("formula.smt2", output_qasm, solver="opensmt")

        #res = self.synthesis_weights(vector_pairs, output_qasm, mode="binary")
        res = self.synthesis_weights(vector_pairs, output_qasm, mode="bottom_up")
        #res = self.synthesis_weights(vector_pairs, output_qasm, mode="top_down")
        return res

    def synthesis_rus(self, qasm_file, output_qasm="circuit.qasm"):
        self.simulator = Simulator(qasm_file, complex_representation=self.complex_representation)
        vector_pairs = self.simulator.simulate_rus()
        stats = self.simulator.circuit_stats()
        self.gate_set = stats['gate_set']
        self.q = stats['q']
        self.d = stats['d']
        self.max_k = self.d if self.d > stats['max_k'] else stats['max_k']
        res = self.synthesis_incremental(vector_pairs, output_qasm)
        return res

    def synthesis_vectors(self, vector_pairs, q, d, output_qasm="circuit.qasm"):
        self.q = q
        self.d = d
        res = self.synthesis_incremental(vector_pairs, output_qasm)
        return res



    def basic_synthesis(self, vector_pairs, output_file="formula.smt2"):
        """
        vector_pairs: List of (input_vector, output_vector) pairs for input and its expected output.
        output_file: Filename to write the formula to
        """
        if self.gate_set is None:
            raise ValueError("gate_set is required")
        
        weights = [self.gen.declare_integer(f"W{i}") for i in range(self.d + 1)]
        self.gen.add_assertion(self.gen.Equals(weights[0], self.gen.Int(0)))
        for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
            In = Vector(q=2**self.q, name=f"In_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k, n=input_vector.n)
            for i, val in enumerate(input_vector.vec):
                self.gen.add_assertion(In[i] == val)
            
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                self.gen.add_assertion(self.gen.Equals(In.k, self.gen.format_integer(input_vector.k)))
            
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k if d == 0 else 0, n = input_vector.n) for d in range(self.d + 1)]
            else:
                inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation) for d in range(self.d + 1)]
            self.gen.add_assertion(inter[0] == In)
            
            for d in range(self.d):
                self.encode_layer(inter[d], inter[d+1], d, weights[d], weights[d+1])
                # add constraining rules - no H H, Tdg T, ...
                self.gen.add_constraints(self.gate_set, d, self.q)

            
            Target = Vector(q=2**self.q, name=f"Target_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = output_vector.k, n = output_vector.n)
            for i, val in enumerate(output_vector.vec):
                self.gen.add_assertion(Target[i] == val)
            
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                self.gen.add_assertion(self.gen.Equals(Target.k, self.gen.format_integer(output_vector.k)))


            conj_rescaled1 = None
            rescaled1 = None
            rescaled2 = None
            if self.gen.logic == "QF_NRA": 
            # FIDELITY
                fidelity = Complex(a=1.0, b=0.0, name="Fidelity", generator=self.gen)
                conjugate = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Conjugate")
                self.gen.add_assertion(conjugate == inter[self.d].conjugate(self.gen))
                self.gen.add_assertion(self.gen.Equals(conjugate.k, inter[self.d].k))
                prod, k_final = conjugate * Target
                prod_real = prod.abs2(k_final) # abs2 <==> fidelity
                self.gen.add_assertion(self.gen.Equals(self.gen.Real(fidelity.real), self.gen.Real(prod_real)))
                self.gen.add_assertion(self.gen.GE(self.gen.Real(fidelity.real), self.gen.Real(0.0)))
                self.gen.add_assertion(self.gen.LE(self.gen.Real(fidelity.real), self.gen.Real(1.0)))
                self.gen.add_assertion(self.gen.GE(self.gen.Real(fidelity.real), self.gen.Real(self.fidelity_threshold)))
            elif self.gen.logic == "QF_LIA" or self.gen.logic == "QF_NIA":
                # QF_LIA and QF_NIA branch -- enumarates all possible outcomes for 2^(floor(n/2)), allowing rescaling by constant
                # other approach enumerates all possible powers of 2, then calculates 2^(floor(abs(k1 - k2)/2)) * M * vector
                rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{inter[self.d].name}")
                rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{Target.name}")
                self.gen.add_rescaling(rescaled1, rescaled2, inter[self.d], Target, pair_idx, self.max_k)
                self.gen.add_assertion(rescaled1 == rescaled2)
        #self.gen.add_assertion(self.gen.LT(weights[self.d], self.gen.Int(1)))
        self.gen.write_smtlib(output_file)


    def synthesis_incremental(self, vector_pairs, output_qasm="circuit.qasm"):
        """
        use incremental solving to get the minimum number of gates in the resulting circuit
        uses pySMT and Cyclotomic8Dyadic
        """    
        
        if self.gate_set is None:
            raise ValueError("gate_set is required")
        self.add_solvers()
        logic = "QF_LIA"
        solvers = ["z3", "cvc5", "yices2", "opensmt"]

        with Portfolio(solvers,
                        logic=logic,
                        incremental=True,
                        generate_models=True) as portfolio:
            self.gen.solver = portfolio
            # start with gates = 1, incrementally add new layer encodings
            # check if the circuit is satisfiable            
            inter_vectors = []
            target_vectors = []
            
            for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
                # input vector generation
                In = Vector(q=2**self.q, name=f"In_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = input_vector.k, n = input_vector.n)
                for i, val in enumerate(input_vector.vec):
                    self.gen.add_assertion(In[i] == val)
        
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    self.gen.add_assertion(self.gen.Equals(In.k, self.gen.format_integer(input_vector.k)))

                # intermediate vectors generation
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k if d == 0 else 0, n = input_vector.n) for d in range(self.d + 1)]
                else:
                    inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation) for d in range(self.d + 1)]
                self.gen.add_assertion(inter[0] == In)
                inter_vectors.append(inter)
                # generate target vector and connect it to output values
                Target = Vector(q=2**self.q, name=f"Target_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = output_vector.k, n = output_vector.n)
                for i, val in enumerate(output_vector.vec):
                    self.gen.add_assertion(Target[i] == val)
                
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    self.gen.add_assertion(self.gen.Equals(Target.k, self.gen.format_integer(output_vector.k)))
                target_vectors.append(Target)
            depth = 1
            solved = False
            while depth <= self.d and not solved:
                print(f"Trying depth: {depth}")
                for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
                    inter = inter_vectors[pair_idx]
                    # encode new layer (depth-1) and connect inter[depth-1] to inter[depth]
                    self.encode_layer(inter[depth-1], inter[depth], depth-1)
                    self.gen.add_constraints(self.gate_set, depth-1, self.q)
                self.gen.solver.push()
                
                # inter[depth] == Target
                for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
                    inter = inter_vectors[pair_idx]
                    Target = target_vectors[pair_idx]
                    
                    if self.gen.logic == "QF_NRA" and (self.complex_representation == FiveTuple or self.complex_representation == nTuple):
                        rescaled1 = inter[depth].to_real()
                        rescaled2 = Target.to_real()
                        conj1_rescaled = rescaled1.conjugate(self.gen)
                        
                        fidelity = Complex(a=1.0, b=0.0, name="Fidelity", generator=self.gen)
                        prod = conj1_rescaled * rescaled2
                        self.gen.add_assertion(self.gen.Equals(fidelity.real, prod.real))
                        self.gen.add_assertion(self.gen.Equals(fidelity.imag, prod.imag))
                        self.gen.add_assertion(self.gen.GE(fidelity.real, 0.0))
                        self.gen.add_assertion(self.gen.LE(fidelity.real, 1.0))
                        self.gen.add_assertion(self.gen.GE(fidelity.real, self.fidelity_threshold))
                    elif self.gen.logic == "QF_LIA" or self.gen.logic == "QF_NIA":
                            rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{inter[depth].name}")
                            rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{Target.name}")
                            self.gen.add_rescaling(rescaled1, rescaled2, inter[depth], Target, pair_idx, self.max_k)
                            self.gen.add_assertion(rescaled1 == rescaled2)
                    else:
                        self.gen.add_assertion(inter[depth] == Target)
                result = self.gen.solver.solve()                       
                if result:
                    solved = True
                    model = self.gen.solver.get_model()
                else:
                    self.gen.solver.pop()
                    depth += 1
            
            if not solved:
                return False
            else:
                #parse_pysmt(model, self.q, self.d, output_qasm, result)
                self.parser.parse(model, self.q, self.d, output_qasm)
                return True

    def binary_cost_search(self, weights, output_qasm="circuit.qasm"):
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
        
    def incremental_bottom_up_cost_search(self, weights, output_qasm="circuit.qasm"):
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

    def incremental_top_down_cost_search(self, weights, output_qasm="circuit.qasm"):
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
        
    def synthesis_weights(self, vector_pairs, output_qasm="circuit.qasm", mode="binary"):
        """
        use binary search and portfolio solving to minimize the cost of the circuit using defined weights of the gate set
        """
        if self.gate_set is None:
            raise ValueError("gate_set is required")
        self.add_solvers()
        logic = "QF_LIA"
        solvers = ["cvc5", "yices2", "z3", "opensmt"]
        with Portfolio(solvers,
                        logic=logic,
                        incremental=True,
                        generate_models=True) as portfolio:
            self.gen.solver = portfolio
        
            weights = [self.gen.declare_integer(f"W{i}") for i in range(self.d + 1)]
            self.gen.add_assertion(self.gen.Equals(weights[0], self.gen.Int(0)))
            for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
                In = Vector(q=2**self.q, name=f"In_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k, n=input_vector.n)
                for i, val in enumerate(input_vector.vec):
                    self.gen.add_assertion(In[i] == val)
                
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    self.gen.add_assertion(self.gen.Equals(In.k, self.gen.format_integer(input_vector.k)))
                
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k if d == 0 else 0, n = input_vector.n) for d in range(self.d + 1)]
                else:
                    inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation) for d in range(self.d + 1)]
                self.gen.add_assertion(inter[0] == In)
                
                for d in range(self.d):
                    self.encode_layer(inter[d], inter[d+1], d, weights[d], weights[d+1])
                    # add constraining rules - no H H, Tdg T, ...
                    self.gen.add_constraints(self.gate_set, d, self.q)

                Target = Vector(q=2**self.q, name=f"Target_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = output_vector.k, n = output_vector.n)
                for i, val in enumerate(output_vector.vec):
                    self.gen.add_assertion(Target[i] == val)
                
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    self.gen.add_assertion(self.gen.Equals(Target.k, self.gen.format_integer(output_vector.k)))


                conj_rescaled1 = None
                rescaled1 = None
                rescaled2 = None
                if self.gen.logic == "QF_NRA": 
                # FIDELITY
                    fidelity = Complex(a=1.0, b=0.0, name="Fidelity", generator=self.gen)
                    conjugate = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Conjugate")
                    self.gen.add_assertion(conjugate == inter[self.d].conjugate(self.gen))
                    self.gen.add_assertion(f"(= {conjugate.k} {inter[self.d].k})")
                    prod, k_final = conjugate * Target
                    prod_real = prod.abs2(k_final) # abs2 <==> fidelity
                    self.gen.add_assertion(f"(= {fidelity.real} {prod_real})")
                    self.gen.add_assertion(f"(>= {fidelity.real} 0.0)")
                    self.gen.add_assertion(f"(<= {fidelity.real} 1.0)")
                    self.gen.add_assertion(f"(>= {fidelity.real} {self.fidelity_threshold})")
                elif self.gen.logic == "QF_LIA" or self.gen.logic == "QF_NIA":
                    # QF_LIA and QF_NIA branch -- enumarates all possible outcomes for 2^(floor(n/2)), allowing rescaling by constant
                    # other approach enumerates all possible powers of 2, then calculates 2^(floor(abs(k1 - k2)/2)) * M * vector
                    rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{inter[self.d].name}")
                    rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{Target.name}")
                    self.gen.add_rescaling(rescaled1, rescaled2, inter[self.d], Target, pair_idx, self.d)
                    self.gen.add_assertion(rescaled1 == rescaled2)
            
            if mode == "binary":
                return self.binary_cost_search(weights, output_qasm)
            elif mode == "bottom_up":
                return self.incremental_bottom_up_cost_search(weights, output_qasm)
            elif mode == "top_down":
                return self.incremental_top_down_cost_search(weights, output_qasm)
            else:
                raise ValueError(f"Invalid mode: {mode}")
                

    def solve_and_extract_circuit(self, smtlib_filename, output_qasm="circuit.qasm", solver=None) -> bool:
        """    
            smtlib_filename: Path to the SMT-LIB file
            output_qasm: Output filename for QASM circuit
            solver: z3, z3alpha, cvc5, opensmt, smtinterpol, yices2, dreal (experimental)
        """
        solver_to_filename = {
            "z3": "z3",
            "z3alpha": "/home/jakubhavlik/rus-synth/solvers/z3alpha/z3alpha.py",
            "cvc5": "/home/jakubhavlik/rus-synth/solvers/cvc5/starexec_run_sq",
            "opensmt": "/home/jakubhavlik/rus-synth/solvers/opensmt/opensmt",
            "smtinterpol": "/home/jakubhavlik/rus-synth/solvers/smtinterpol/smtinterpol",
            "yices2": "/home/jakubhavlik/rus-synth/solvers/yices2/yices_smt2",
            "dreal": "/opt/dreal/4.21.06.2/bin/dreal"
        }
        
        if solver is None:
            solver = self.solver

        elif smtlib_filename is None:
            raise ValueError("smtlib_filename is None")

        jobs = cpu_count()
        if jobs is None:
            jobs = 1
        args = {
            "dreal": [ "-j",  str(jobs), "--precision", "1e-6", "--produce-models"]
        }
        if solver not in solver_to_filename:
            raise ValueError(f"Invalid solver: {solver}")
        result = None
        try:
            result = subprocess.run(
                [solver_to_filename[solver], smtlib_filename] + args.get(solver, []),
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