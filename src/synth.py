"""
@file: synth.py
@author: Jakub Havlík
@date: 24.02.2026
@brief: quantum circuit synthesis using SMT and MILP solving
"""

from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic as FiveTuple, nTuple
from smtlib_generator import SMTLibGenerator, PortfolioSolver
from parser import parse_z3, parse_z3alpha, parse_cvc5, parse_opensmt, parse_smtinterpol, parse_yices2, parse_dreal, parse_pysmt
import subprocess
from sim import Simulator
from multiprocessing import cpu_count
from pysmt.logics import QF_NRA, QF_LIA, QF_NIA
from pysmt.shortcuts import Portfolio, Symbol, Real, And, Equals, Plus, GT, LT, get_env, Int, Or, Not, Implies, GE, LE, Ite, Minus, Div, Times
from pysmt.typing import REAL, INT
from pysmt.solvers.solver import Solver
from gates import GateSet, supported_gates, check_supported


class Synthesizer:
    def __init__(self, gen = None, gate_set : GateSet =None, solver : str = None, fidelity_threshold : int = 1.0) -> None:
        if gen is None:
            raise ValueError("gen is required")
        if gate_set is None:
            raise ValueError("gate_set is required")
        if solver is None:
            raise ValueError("solver is required")
        self.gen = gen
        self.gate_set = gate_set
        self.simulator = None
        self.complex_representation = FiveTuple
        self.solver = solver
        self.fidelity_threshold = fidelity_threshold
        self.q = None
        self.d = None
        if solver == "dreal":
            self.gen.rescaling = True
            
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
        

    def encode_layer(self, inp : Vector, out : Vector, layer : int) -> None:
        if self.complex_representation == Complex:
            inv_sqrt2 = self.complex_representation.inv_sqrt2(self.gen)
            minus1    = self.complex_representation.minus_one(self.gen)
            i_phase   = self.complex_representation.i_phase(self.gen)
            t_phase   = self.complex_representation.t_phase(self.gen)
            one_half  = self.complex_representation.one_half(self.gen)
            i_half    = self.complex_representation.i_half(self.gen)
        
        def add_implies(sel, expr):
            if isinstance(self.gen, PortfolioSolver):
                self.gen.add_assertion(Implies(sel, expr))
            else:
                self.gen.add_assertion(f"(=> {sel} {expr})")
        
        def add_k_eq(sel, out_k, inp_k):
            if isinstance(self.gen, PortfolioSolver):
                k_eq = Equals(out_k, inp_k)
                self.gen.add_assertion(Implies(sel, k_eq))
            else:
                k_eq = f"(= {out_k} {inp_k})"
                add_implies(sel, k_eq)
        
        def add_k_incr(sel, out_k, inp_k, increment):
            if isinstance(self.gen, PortfolioSolver):
                k_incr = Equals(out_k, Plus(inp_k, Int(increment)))
                self.gen.add_assertion(Implies(sel, k_incr))
            else:
                k_incr = f"(= {out_k} (+ {inp_k} {increment}))"
                add_implies(sel, k_incr)
                
        #implicitly add identity to the gate set if not present
        if 'id' not in self.gate_set:
            self.gate_set.append('id')
        if not check_supported(self.gate_set):
            raise ValueError("gate set contains an unsupported gate")
        
        selection_variables = []
        bool_variables = []
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
        if self.gen.name == "PortfolioSolver":
            self.gen.add_assertion(Or(*bool_variables))
        else:
            self.gen.add_assertion(f"(or {' '.join(bool_variables)})")
    
        for v in bool_variables:
            others = [v2 for v2 in bool_variables if v2 != v]
            if self.gen.name == "PortfolioSolver":
                self.gen.add_assertion(Implies(v, And(*[Not(v2) for v2 in others])))
            else:
                self.gen.add_assertion(f"(=> {v} (and {' '.join(f'(not {v2})' for v2 in others)}))")

        for selection_variable in selection_variables:
            bool_var = selection_variable[0]
            rest = selection_variable[1]
            gate = rest[0]
            if len(rest) == 2: # single qubit
                q = rest[1]
                if gate == 'id':
                    for pos in range(2**self.q):
                        eq_expr = out[pos] == inp[pos]
                        add_implies(bool_var, eq_expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'h':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        other = pos ^ (1 << q)
                        modified_positions.append(other)
                        if self.complex_representation == Complex:
                            expr1 = out[pos] == ((inp[pos] + inp[other]) * inv_sqrt2)
                            add_implies(bool_var, expr1)
                            expr2 = out[other] == ((inp[pos] + (inp[other] * minus1)) * inv_sqrt2)
                            add_implies(bool_var, expr2)
                        elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            expr1 = out[pos] == ((inp[pos] + inp[other]).divide_by_sqrt2(self.gen))
                            add_implies(bool_var, expr1)
                            expr2 = out[other] == ((inp[pos] + (inp[other].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen))
                            add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 1)
                elif gate == 's':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * i_phase)
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_i(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sdg':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * i_phase.conjugate(self.gen))
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_minus_i(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 't':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * t_phase)
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_omega(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'tdg':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * t_phase.conjugate(self.gen))
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_omega_counter(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'x':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        other = pos ^ (1 << q)
                        modified_positions.append(other)
                        expr1 = out[pos] == inp[other]
                        add_implies(bool_var, expr1)
                        expr2 = out[other] == inp[pos]
                        add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'sx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        other = pos ^ (1 << q)
                        modified_positions.append(other)
                        if self.complex_representation == Complex:
                            expr1 = out[pos] == (((inp[pos] + inp[other]) * one_half) + (inp[pos] - inp[other]) * i_half)
                            add_implies(bool_var, expr1)
                            expr2 = out[other] == (((inp[pos] + inp[other]) * one_half) + (inp[other] - inp[pos]) * i_half)
                            add_implies(bool_var, expr2)
                        elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            expr1 = out[pos] == ((inp[pos] + inp[other]) + (inp[pos] - inp[other]).multiply_by_i(self.gen))
                            add_implies(bool_var, expr1)
                            expr2 = out[other] == ((inp[pos] + inp[other]) + (inp[other] - inp[pos]).multiply_by_i(self.gen))
                            add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 2)
                elif gate == 'sxdg':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        other = pos ^ (1 << q)
                        modified_positions.append(other)
                        if self.complex_representation == Complex:
                            eq1_expr = out[pos] == (((inp[pos] + inp[other]) * one_half)  + (inp[other] - inp[pos]) * i_half)
                            add_implies(bool_var, eq1_expr)
                            eq2_expr = out[other]    == (((inp[pos] + inp[other]) * one_half)  + (inp[pos] - inp[other]) * i_half)
                            add_implies(bool_var, eq2_expr)
                        elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                            eq1_expr = out[pos] == ((inp[pos] + inp[other]) + (inp[other] - inp[pos]).multiply_by_i(self.gen))
                            add_implies(bool_var, eq1_expr)
                            eq2_expr = out[other] == ((inp[pos] + inp[other]) + (inp[pos] - inp[other]).multiply_by_i(self.gen))
                            add_implies(bool_var, eq2_expr)
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
                            if self.complex_representation == Complex:
                                expr1 = out[pos] == (inp[other] * i_phase)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == (inp[pos] * i_phase.conjugate(self.gen))
                                add_implies(bool_var, expr2)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr1 = out[pos] == inp[other].multiply_by_i(self.gen)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == inp[pos].multiply_by_minus_i(self.gen)
                                add_implies(bool_var, expr2)
                        else:
                            if self.complex_representation == Complex:
                                expr1 = out[pos] == (inp[other] * i_phase.conjugate(self.gen))
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == (inp[pos] * i_phase)
                                add_implies(bool_var, expr2)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr1 = out[pos] == inp[other].multiply_by_minus_i(self.gen)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == inp[pos].multiply_by_i(self.gen)
                                add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'z':
                    for pos in range(2**self.q):
                        one_flag = (pos >> q) & 1
                        if one_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * minus1)
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_minus_one(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
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
                        if not control_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            expr1 = out[pos] == inp[other]
                            add_implies(bool_var, expr1)
                            expr2 = out[other] == inp[pos]
                            add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'xcx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if control_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            expr1 = out[pos] == inp[other]
                            add_implies(bool_var, expr1)
                            expr2 = out[other] == inp[pos]
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
                        other = pos
                        if not control_flag and target_flag:
                            other = pos ^ ((1 << q1) | (1 << q2))
                        elif control_flag and not target_flag:
                            other = pos ^ (1 << q2)
                        elif control_flag and target_flag:
                            other = pos ^ (1 << q1)
                        expr = out[other] == inp[pos]
                        add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'ch':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if not control_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            if self.complex_representation == Complex:
                                expr1 = out[pos] == ((inp[pos] + inp[other]) * inv_sqrt2)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == ((inp[pos] + (inp[other] * minus1)) * inv_sqrt2)
                                add_implies(bool_var, expr2)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr1 = out[pos] == (inp[pos] + inp[other]).divide_by_sqrt2(self.gen)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == (inp[pos] + (inp[other] * minus1)).divide_by_sqrt2(self.gen)
                                add_implies(bool_var, expr2)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_incr(bool_var, out.k, inp.k, 1)
                elif gate == 'csx':
                    modified_positions = []
                    for pos in range(2**self.q):
                        if pos in modified_positions: continue
                        modified_positions.append(pos)
                        control_flag = (pos >> q1) & 1
                        if not control_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            if self.complex_representation == Complex:
                                expr1 = out[pos] == (((inp[pos] + inp[other]) * one_half)  + (inp[pos] - inp[other]) * i_half)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == (((inp[pos] + inp[other]) * one_half)  + (inp[other] - inp[pos]) * i_half)
                                add_implies(bool_var, expr2)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr1 = out[pos] == ((inp[pos] + inp[other]) + (inp[pos] - inp[other]).multiply_by_i(self.gen))
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == ((inp[pos] + inp[other]) + (inp[other] - inp[pos]).multiply_by_i(self.gen))
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
                        if not control_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ (1 << q2)
                            modified_positions.append(other)
                            if control_flag and not target_flag:
                                if self.complex_representation == Complex:
                                    expr1 = out[pos] == (inp[other] * i_phase.conjugate(self.gen))
                                    add_implies(bool_var, expr1)
                                    expr2 = out[other] == (inp[pos] * i_phase)
                                    add_implies(bool_var, expr2)
                                elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                    expr1 = out[pos] == inp[other].multiply_by_minus_i(self.gen)
                                    add_implies(bool_var, expr1)
                                    expr2 = out[other] == inp[pos].multiply_by_i(self.gen)
                                    add_implies(bool_var, expr2)
                            elif control_flag and target_flag:
                                if self.complex_representation == Complex:
                                    expr1 = out[pos] == (inp[other] * i_phase)
                                    add_implies(bool_var, expr1)
                                    expr2 = out[other] == (inp[pos] * i_phase.conjugate(self.gen))
                                    add_implies(bool_var, expr2)
                                elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                    expr1 = out[pos] == inp[other].multiply_by_i(self.gen)
                                    add_implies(bool_var, expr1)
                                    expr2 = out[other] == inp[pos].multiply_by_minus_i(self.gen)
                                    add_implies(bool_var, expr2)
                        
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'cz':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * minus1)
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_minus_one(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
                        add_implies(bool_var, expr)
                elif gate == 'cs':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * i_phase)
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_i(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'csdg':
                    for pos in range(2**self.q):
                        control_flag = (pos >> q1) & 1
                        target_flag = (pos >> q2) & 1
                        if control_flag and target_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * i_phase.conjugate(self.gen))
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_minus_i(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
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
                        if q1_flag == q2_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            expr1 = out[pos] == inp[other]
                            add_implies(bool_var, expr1)
                            expr2 = out[other] == inp[pos]
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
                        if q1_flag == q2_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            if self.complex_representation == Complex:
                                expr1 = out[pos] == (inp[other] * i_phase)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == (inp[pos] * i_phase)
                                add_implies(bool_var, expr2)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr1 = out[pos] == inp[other].multiply_by_i(self.gen)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == inp[pos].multiply_by_i(self.gen)
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
                        if q1_flag == q2_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            if self.complex_representation == Complex:
                                expr1 = out[pos] == (((inp[pos] + inp[other]) * one_half)  + (inp[pos] - inp[other]) * i_half)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == (((inp[pos] + inp[other]) * one_half)  + (inp[other] - inp[pos]) * i_half)
                                add_implies(bool_var, expr2)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr1 = out[pos] == (((inp[pos] + inp[other]))  + (inp[pos] - inp[other]).multiply_by_i(self.gen))
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == (((inp[pos] + inp[other]))  + (inp[other] - inp[pos]).multiply_by_i(self.gen))
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
                        if q1_flag == q2_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ ((1 << q1) | (1 << q2))
                            modified_positions.append(other)
                            if self.complex_representation == Complex:
                                expr1 = out[pos] == ((inp[pos] + (inp[other] * i_phase)) * inv_sqrt2)
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == (((inp[pos] * i_phase) + (inp[other])) * inv_sqrt2)
                                add_implies(bool_var, expr2)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                exp1 = out[pos] == ((inp[pos] + (inp[other].multiply_by_i(self.gen))))
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == ((inp[pos].multiply_by_i(self.gen)) + (inp[other]))
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
                        if not q1_flag or not q2_flag:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                        else:
                            other = pos ^ (1 << q3)
                            modified_positions.append(other)
                            expr1 = out[pos] == inp[other]
                            add_implies(bool_var, expr1)
                            expr2 = out[other] == inp[pos]
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
                        if q1_flag:
                            if q2_flag != q3_flag:
                                other = pos ^ ((1 << q2) | (1 << q3))
                                modified_positions.append(other)
                                expr1 = out[pos] == inp[other]
                                add_implies(bool_var, expr1)
                                expr2 = out[other] == inp[pos]
                                add_implies(bool_var, expr2)
                            else:
                                expr = out[pos] == inp[pos]
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)
                elif gate == 'ccz':
                    for pos in range(2**self.q):
                        q1_flag = (pos >> q1) & 1
                        q2_flag = (pos >> q2) & 1
                        q3_flag = (pos >> q3) & 1
                        if q1_flag and q2_flag and q3_flag:
                            if self.complex_representation == Complex:
                                expr = out[pos] == (inp[pos] * minus1)
                                add_implies(bool_var, expr)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                expr = out[pos] == inp[pos].multiply_by_minus_one(self.gen)
                                add_implies(bool_var, expr)
                        else:
                            expr = out[pos] == inp[pos]
                            add_implies(bool_var, expr)
                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        add_k_eq(bool_var, out.k, inp.k)

    def synthesis(self, qasm_file, output_qasm="circuit.qasm"):
        self.simulator = Simulator(qasm_file, complex_representation=self.complex_representation)
        vector_pairs = self.simulator.simulate_circuit()
        stats = self.simulator.circuit_stats()
        self.gate_set = stats['gate_set']
        self.q = stats['q']
        self.d = stats['d']
        self.basic_synthesis(vector_pairs)
        self.solve_and_extract_circuit("formula.smt2", self.q, self.d, output_qasm)
    
    def synthesis_zero(self, qasm_file, output_qasm="circuit.qasm"):
        self.simulator = Simulator(qasm_file, complex_representation=self.complex_representation)
        vector_pairs = self.simulator.simulate_zero()
        stats = self.simulator.circuit_stats()
        self.gate_set = stats['gate_set']
        self.q = stats['q']
        self.d = stats['d']
        self.basic_synthesis(vector_pairs)
        #self.synthesis_gate_optimal(vector_pairs, output_qasm)

    def synthesis_rus(self, qasm_file, output_qasm="circuit.qasm"):
        self.simulator = Simulator(qasm_file, complex_representation=self.complex_representation)
        vector_pairs = self.simulator.simulate_rus()
        stats = self.simulator.circuit_stats()
        self.gate_set = stats['gate_set']
        self.q = stats['q']
        self.d = stats['d']
        self.synthesis_gate_optimal(vector_pairs, output_qasm)

    def synthesis_vectors(self, vector_pairs, q, d, output_qasm="circuit.qasm"):
        self.q = q
        self.d = d
        self.synthesis_gate_optimal(vector_pairs, output_qasm)



    def basic_synthesis(self, vector_pairs, output_file="formula.smt2"):
        """
        vector_pairs: List of (input_vector, output_vector) pairs for input and its expected output.
        output_file: Filename to write the formula to
        """

        for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
            In = Vector(q=2**self.q, name=f"In_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k, n=input_vector.n)
            for i, val in enumerate(input_vector.vec):
                self.gen.add_assertion(In[i] == val)
            
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                if isinstance(input_vector.k, int):
                    self.gen.add_assertion(f"(= {In.k} {input_vector.k})")
                elif isinstance(input_vector.k, str) and input_vector.k != In.k:
                    self.gen.add_assertion(f"(= {In.k} {input_vector.k})")
            
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k if d == 0 else 0, n = input_vector.n) for d in range(self.d + 1)]
            else:
                inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation) for d in range(self.d + 1)]
            self.gen.add_assertion(inter[0] == In)
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                self.gen.add_assertion(f"(= {inter[0].k} {In.k})")
            
            for d in range(self.d):
                self.encode_layer(inter[d], inter[d+1], d)
            
            Target = Vector(q=2**self.q, name=f"Target_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = output_vector.k, n = output_vector.n)
            for i, val in enumerate(output_vector.vec):
                self.gen.add_assertion(Target[i] == val)
            
            if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                if isinstance(output_vector.k, int):
                    self.gen.add_assertion(f"(= {Target.k} {output_vector.k})")
                elif isinstance(output_vector.k, str) and output_vector.k != Target.k:
                    self.gen.add_assertion(f"(= {Target.k} {output_vector.k})")
                        

            # add k rescaling -- only possible in QF_NRA
            conj_rescaled1 = None
            rescaled1 = None
            rescaled2 = None
            approximate_equivalence = self.gen.approximate_equivalence
            if approximate_equivalence:
                # FIDELITY
                if self.gen.logic == "QF_NRA": 
                    fidelity = Complex(a=1.0, b=0.0, name="Fidelity", generator=self.gen)
                    conjugate = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Conjugate")
                    self.gen.add_assertion(conjugate == inter[self.d].conjugate())
                    self.gen.add_assertion(f"(= {conjugate.k} {inter[self.d].k})")
                    prod, k_final = conjugate * Target
                    prod_real = prod.abs2(k_final) # abs2 <==> fidelity
                    self.gen.add_assertion(f"(= {fidelity.real} {prod_real})")
                    self.gen.add_assertion(f"(>= {fidelity.real} 0.0)")
                    self.gen.add_assertion(f"(<= {fidelity.real} 1.0)")
                    self.gen.add_assertion(f"(>= {fidelity.real} {self.fidelity_threshold})")
                else:
                    raise ValueError("approximate equivalence not supported for non NRA")
            else:
                # EXACT EQUIVALENCE
                if self.gen.logic == "QF_NRA":
                    # since there is no floor(n/2) in dreal, do 2k <= n < 2*(k+1) where k = floor(n/2)
                    # check for odd/even r = n - 2k, r is in <0, 2)
                    # then, if r == 0, its even, if r == 1, its odd
                    self.gen.declare_real(f"n{pair_idx}")
                    self.gen.add_assertion(f"(ite (< {inter[self.d].k} {Target.k}) (= n{pair_idx} (- {Target.k} {inter[self.d].k})) (= n{pair_idx} (- {inter[self.d].k} {Target.k})))")
                    self.gen.declare_real(f"k{pair_idx}")
                    self.gen.add_assertion(f"(and (>= n{pair_idx} (* 2 k{pair_idx})) (< n{pair_idx} (* 2 (+ k{pair_idx} 1))))")
                    rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{inter[self.d].name}")
                    rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{Target.name}")
                    # enumerate possible k's <0, d1/2>
                    # calculate the power and parity check (n - 2k) == 0 if even
                    self.gen.enumerate_k_values(self.d//2, pair_idx)
                    self.gen.declare_real(f"pow2{pair_idx}")
                    self.gen.add_assertion(f"(= pow2{pair_idx} (pow 2 k{pair_idx})))")
                    self.gen.declare_real(f"r")
                    self.gen.add_assertion(f"(= r (- n{pair_idx} (* 2 k{pair_idx})))")
                    self.gen.declare_bool(f"is_even{pair_idx}")
                    self.gen.add_assertion(f"(ite (= r 0) (= is_even{pair_idx} true) (= is_even{pair_idx} false))")
                    self.gen.add_rescaling(rescaled1, rescaled2, inter[self.d], Target, pair_idx, self.d)
                    self.gen.add_assertion(rescaled1 == rescaled2)
                elif self.gen.logic == "QF_NIA":
                    # QF_NIA branch
                    # rescaling -- add enumeration of all possible powers of 2,
                    # calculate 2^(floor(n/2)) * M * vector
                    # n == abs(last_k - target_k)
                    self.gen.declare_integer(f"n{pair_idx}")
                    self.gen.add_assertion(f"(ite (< {inter[self.d].k} {Target.k}) (= n{pair_idx} (- {Target.k} {inter[self.d].k})) (= n{pair_idx} (- {inter[self.d].k} {Target.k})))")
                    self.gen.enumerate_powers_of_2(self.d + 1, pair_idx)
                    # after that, rescale the vectors -- create 2 new vectors, the one with lower k gets rescaled, the other one just gets copied
                    # then, compare them
                    rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{inter[self.d].name}")
                    rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{Target.name}")
                    self.gen.add_rescaling(rescaled1, rescaled2, inter[self.d], Target, pair_idx, self.d)
                    self.gen.add_assertion(rescaled1 == rescaled2)
                elif self.gen.logic == "QF_LIA":
                    # QF_LIA branch -- same rescaling as QF_NIA, but enumarates all possible outcomes for 2^(floor(n/2)), allowing rescaling by constant
                    self.gen.declare_integer(f"n{pair_idx}")
                    self.gen.declare_integer(f"k{pair_idx}")
                    self.gen.add_assertion(f"(= k{pair_idx} (div n{pair_idx} 2))")
                    self.gen.add_assertion(f"(ite (< {inter[self.d].k} {Target.k}) (= n{pair_idx} (- {Target.k} {inter[self.d].k})) (= n{pair_idx} (- {inter[self.d].k} {Target.k})))")
                    rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{inter[self.d].name}")
                    rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{Target.name}")
                    self.gen.add_rescaling(rescaled1, rescaled2, inter[self.d], Target, pair_idx, self.d)
                    self.gen.add_assertion(rescaled1 == rescaled2)
                else:
                    raise ValueError("invalid logic")
        
        # add constraining rules - no H H, Tdg T, ...
        self.gen.remove_identities(self.gate_set, self.q, self.d)
        
        smtlib_content = self.gen.generate(self.complex_representation)
        with open(output_file, 'w') as f:
            f.write(smtlib_content)


    def synthesis_gate_optimal(self, vector_pairs, output_qasm="circuit.qasm"):
        """
        use incremental solving to get the minimum number of gates in the resulting circuit
        uses pySMT and Cyclotomic8Dyadic
        """    
        self.add_solvers()
        logic = "QF_LIA"
        solvers = ["z3", "cvc5", "yices2", "smtinterpol", "opensmt"]

        with Portfolio(solvers,
                        logic=logic,
                        incremental=True,
                        generate_models=True) as solver:
            self.gen = PortfolioSolver(solver)
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
                    if self.gen.name == 'PortfolioSolver':
                        input_k_expr = self.gen.format_integer(input_vector.k)
                        self.gen.add_assertion(Equals(In.k, input_k_expr))
                    else:
                        self.gen.add_assertion(f"(= {In.k} {int(input_vector.k)})")

                # intermediate vectors generation
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation, k=input_vector.k if d == 0 else 0, n = input_vector.n) for d in range(self.d + 1)]
                else:
                    inter = [Vector(q=2**self.q, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=self.complex_representation) for d in range(self.d + 1)]
                self.gen.add_assertion(inter[0] == In)
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    if self.gen.name == 'PortfolioSolver':
                        self.gen.add_assertion(Equals(inter[0].k, In.k))
                    else:
                        self.gen.add_assertion(f"(= {inter[0].k} {In.k})")
                inter_vectors.append(inter)
                # generate target vector and connect it to output values
                Target = Vector(q=2**self.q, name=f"Target_{pair_idx}", generator=self.gen, element_representation=self.complex_representation, k = output_vector.k, n = output_vector.n)
                for i, val in enumerate(output_vector.vec):
                    self.gen.add_assertion(Target[i] == val)
                
                if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                    if self.gen.name == 'PortfolioSolver':
                        output_k_expr = self.gen.format_integer(output_vector.k)
                        self.gen.add_assertion(Equals(Target.k, output_k_expr))
                    else:
                        self.gen.add_assertion(f"(= {Target.k} {int(output_vector.k)})")
                target_vectors.append(Target)
            depth = 1
            solved = False
            while depth <= self.d and not solved:
                print("Trying depth: ", depth)
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
                        conj1_rescaled = rescaled1.conjugate()
                        
                        fidelity = Complex(a=1.0, b=0.0, name="Fidelity", generator=self.gen)
                        prod = conj1_rescaled * rescaled2
                        if self.gen.name == 'PortfolioSolver':
                            self.gen.add_assertion(Equals(fidelity.real, prod.real))
                            self.gen.add_assertion(Equals(fidelity.imag, prod.imag))
                            self.gen.add_assertion(GE(fidelity.real, 0.0))
                            self.gen.add_assertion(LE(fidelity.real, 1.0))
                            self.gen.add_assertion(GE(fidelity.real, self.fidelity_threshold))
                        else:
                            self.gen.add_assertion(f"(= {fidelity.real} {prod.real})")
                            self.gen.add_assertion(f"(= {fidelity.imag} {prod.imag})")
                            self.gen.add_assertion(f"(>= {fidelity.real} 0.0)")
                            self.gen.add_assertion(f"(<= {fidelity.real} 1.0)")
                            #self.gen.maximize(f"{fidelity.real}"
                            self.gen.add_assertion(f"(>= {fidelity.real} {self.fidelity_threshold})")
                    elif self.gen.logic == "QF_NIA":
                        # rescaling allowed
                        if self.complex_representation == FiveTuple:
                            self.gen.declare_integer(f"n{pair_idx}")
                            self.gen.add_assertion(Ite(LT(inter[depth].k, Target.k), Equals(self.gen.symbols[f"n{pair_idx}"], Minus(Target.k, inter[depth].k)), Equals(self.gen.symbols[f"n{pair_idx}"], Minus(inter[depth].k, Target.k))))
                            self.gen.enumerate_powers_of_2(depth + 1, pair_idx)
                            # after that, rescale the vectors -- create 2 new vectors, the one with lower k gets rescaled, the other one just gets copied
                            # then, compare them
                            rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{inter[depth].name}")
                            rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{Target.name}")
                            self.gen.add_rescaling(rescaled1, rescaled2, inter[depth], Target, pair_idx, depth)
                            self.gen.add_assertion(rescaled1 == rescaled2)
                    elif self.gen.logic == "QF_LIA":
                            self.gen.declare_integer(f"n{pair_idx}")
                            self.gen.declare_integer(f"k{pair_idx}")
                            n_sym = self.gen.symbols[f"n{pair_idx}"]
                            k_sym = self.gen.symbols[f"k{pair_idx}"]
                            self.gen.add_assertion(And(
                                LE(Times(k_sym, Int(2)), n_sym),
                                LT(n_sym, Times(Plus(k_sym, Int(1)), Int(2)))
                            ))
                            self.gen.add_assertion(Ite(LT(inter[depth].k, Target.k), Equals(self.gen.symbols[f"n{pair_idx}"], Minus(Target.k, inter[depth].k)), Equals(self.gen.symbols[f"n{pair_idx}"], Minus(inter[depth].k, Target.k))))
                            rescaled1 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled1_{inter[depth].name}")
                            rescaled2 = Vector(q=2**self.q, generator=self.gen, element_representation=self.complex_representation, k=0, n=self.q, name=f"Rescaled2_{Target.name}")
                            self.gen.add_rescaling(rescaled1, rescaled2, inter[depth], Target, pair_idx, self.d)
                            self.gen.add_assertion(rescaled1 == rescaled2)
                    else:
                        self.gen.add_assertion(inter[depth] == Target)
                print(f"Solving with {self.gen.name}...")
                result = self.gen.solver.solve()                       
                if result:
                    solved = True
                    model = self.gen.solver.get_model()
                else:
                    self.gen.solver.pop()
                    depth += 1
            
            if not solved:
                print("unsat")
                return False
            else:
                parse_pysmt(model, self.q, self.d, output_qasm, result)
                return True

                

    def solve_and_extract_circuit(self, smtlib_filename, output_qasm="circuit.qasm", solver=None) -> bool:
        """    
            smtlib_filename: Path to the SMT-LIB file
            output_qasm: Output filename for QASM circuit
            solver: z3, z3alpha, cvc5, opensmt, smtinterpol, yices2, dreal (experimental)
        """
        solver_to_filename = {
            "z3": "z3",
            "z3alpha": "../../solvers/z3alpha/z3alpha.py",
            "cvc5": "../../solvers/cvc5/starexec_run_sq",
            "opensmt": "../../solvers/opensmt/opensmt",
            "smtinterpol": "../../solvers/smtinterpol/smtinterpol",
            "yices2": "../../solvers/yices2/yices_smt2",
            "dreal": "/opt/dreal/4.21.06.2/bin/dreal"
        }
        
        if solver is None:
            solver = self.solver

        elif smtlib_filename is None:
            raise ValueError("smtlib_filename is None")
        
        if solver != "dreal" and hasattr(self.gen, 'rescaling') and self.gen.rescaling:
            raise ValueError("solver is not dreal but the generator is configured for dreal")

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
                [solver_to_filename[solver], smtlib_filename] + args.get(solver, []),
                capture_output=True,
                text=True,
            )
            parse_map = {
                "z3": parse_z3,
                "z3alpha": parse_z3alpha,
                "cvc5": parse_cvc5,
                "opensmt": parse_opensmt,
                "smtinterpol": parse_smtinterpol,
                "yices2": parse_yices2,
                "dreal": parse_dreal
            }
            parse_map[solver](result.stdout, self.q, self.d, output_qasm, result)
            return True
        except Exception as e:
            raise ValueError(f"Error: {e}")
            return False