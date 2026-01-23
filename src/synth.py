import numpy as np
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic, nTuple
from smtlib_generator import SMTLibGenerator, PortfolioSolver
from qasm import parse_z3, parse_z3alpha, parse_cvc5, parse_opensmt, parse_smtinterpol, parse_yices2, parse_dreal, parse_pysmt
import time
import resource
import subprocess
import os
from pauli import syn_pauli
from multiprocessing import cpu_count
from pathlib import Path
from pysmt.logics import QF_NRA, QF_LIA, QF_NIA
from pysmt.shortcuts import Portfolio, Symbol, Real, And, Equals, Plus, GT, LT, get_env, Int, Or, Not, Implies, GE, LE, Ite, Minus
from pysmt.typing import REAL, INT
from pysmt.solvers.solver import Solver


class Synthesizer:
    def __init__(self, gen=None, gate_set=None, solver=None, fidelity_threshold=1.0):
        if gen is None:
            raise ValueError("gen is required")
        if gate_set is None:
            raise ValueError("gate_set is required")
        if solver is None:
            raise ValueError("solver is required")
        self.gen = gen
        self.gate_set = gate_set
        self.solver = solver
        self.fidelity_threshold = fidelity_threshold
        if solver == "dreal":
            self.gen.rescaling = True
            
    def add_solvers(self):
        # register custom solvers for pySMT portfolio solving (TODO change for relative paths, change logics to match the respective solvers)
        
        opensmt_name = "opensmt"
        opensmt_path = "/home/jakubhavlik/rus-synth/solvers/opensmt/opensmt"
        opensmt_logics = [QF_LIA]
        env = get_env()
        env.factory.add_generic_solver(opensmt_name, opensmt_path, opensmt_logics)
        
        yices2_name = "yices2"
        yices2_path = "/home/jakubhavlik/rus-synth/solvers/yices2/yices_smt2"
        yices2_logics = [QF_LIA, QF_NRA, QF_NIA]
        env.factory.add_generic_solver(yices2_name, yices2_path, yices2_logics)
        
        smtinterpol_name = "smtinterpol"
        smtinterpol_path = "/home/jakubhavlik/rus-synth/solvers/smtinterpol/smtinterpol"
        smtinterpol_logics = [QF_LIA, QF_NRA, QF_NIA]
        env.factory.add_generic_solver(smtinterpol_name, smtinterpol_path, smtinterpol_logics)
        
        cvc5_name = "cvc5"
        cvc5_path = "/home/jakubhavlik/rus-synth/solvers/cvc5/cvc5"
        cvc5_logics = [QF_LIA, QF_NRA, QF_NIA]
        env.factory.add_generic_solver(cvc5_name, cvc5_path, cvc5_logics)
        
        dreal_name = "dreal"
        dreal_path = "/home/jakubhavlik/rus-synth/solvers/dreal/run_dreal.sh"
        dreal_logics = [QF_NRA]
        env.factory.add_generic_solver(dreal_name, dreal_path, dreal_logics)
        

    def encode_layer(self, inp, out, layer, n, vec_len, inv_sqrt2, minus1, i_phase, t_phase, one_half, i_half, complex_representation):
        single_sel = {}
        two_sel = {}
        three_sel = {}
        sel_vars = []
        gate_selections = {}
        supported_single_qubit = ['H','S','Sdg','T','I','Tdg','X','Y','Z','SX','SXdg']
        supported_two_qubit = ['CX','SWAP', 'iSWAP', 'CH','CS','CSdg','CY','CZ','DCX','CSX', 'XCX', 'ECR', 'MAGIC', 'sqrtSWAP', 'isqrtSWAP']
        supported_three_qubit = ['CCX','CSWAP','CCZ', 'RCCX', 'PG']
        
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
                
        # implicitly add identity to the gate set if not present
        if 'I' not in self.gate_set:
            self.gate_set.append('I')
        
        supported_single_qubit = [gate for gate in supported_single_qubit if gate in self.gate_set]
        supported_two_qubit = [gate for gate in supported_two_qubit if gate in self.gate_set]
        supported_three_qubit = [gate for gate in supported_three_qubit if gate in self.gate_set]
        
        # check if the gate set has any unsupported gates
        unsupported_gates = set(self.gate_set) - set(supported_single_qubit) - set(supported_two_qubit) - set(supported_three_qubit)
        if unsupported_gates:
            raise ValueError(f"Unsupported gates: {unsupported_gates}")
        
        # ---- single-qubit gates ----
        for gate in supported_single_qubit:
            for q in range(n):
                key = (layer, gate, q)
                if key not in gate_selections:
                    v_name = f"L{layer}_{gate}_q{q}"
                    v = self.gen.declare_bool(v_name)
                    gate_selections[key] = v
                single_sel[(gate, q)] = gate_selections[key]
                sel_vars.append(gate_selections[key])

        # ---- two-qubit gates ----
        for gate in supported_two_qubit:
            for c in range(n):
                for t in range(n):
                    if c == t: continue
                    key = (layer, gate, c, t)
                    if key not in gate_selections:
                        v_name = f"L{layer}_{gate}_c{c}t{t}"
                        v = self.gen.declare_bool(v_name)
                        gate_selections[key] = v
                    two_sel[(gate, c, t)] = gate_selections[key]
                    sel_vars.append(gate_selections[key])            
                    
        # ---- three-qubit gates ----
        for gate in supported_three_qubit:
            for c1 in range(n):
                for c2 in range(n):
                    for t in range(n):
                        if c1 == c2 or c1 == t or c2 == t: continue
                        key = (layer, gate, c1, c2, t)
                        if key not in gate_selections:
                            v_name = f"L{layer}_{gate}_c{c1}c{c2}t{t}"
                            v = self.gen.declare_bool(v_name)
                            gate_selections[key] = v
                        three_sel[(gate, c1, c2, t)] = gate_selections[key]
                        sel_vars.append(gate_selections[key])

        # ---- exactly ONE gate per layer (only add constraints once per layer) ----
        if layer not in gate_selections.get('_constraints_added', set()):
            if isinstance(self.gen, PortfolioSolver):
                at_least = Or(*sel_vars)
                self.gen.add_assertion(at_least)
                
                for i, v1 in enumerate(sel_vars):
                    for v2 in sel_vars[i+1:]:
                        self.gen.add_assertion(Implies(v1, Not(v2)))
                        self.gen.add_assertion(Implies(v2, Not(v1)))
            else:
                at_least = f"(or {' '.join(sel_vars)})"
                self.gen.add_assertion(at_least)
                
                for i, v1 in enumerate(sel_vars):
                    for v2 in sel_vars[i+1:]:
                        self.gen.add_assertion(f"(=> {v1} (not {v2}))")
                        self.gen.add_assertion(f"(=> {v2} (not {v1}))")
            
            if '_constraints_added' not in gate_selections:
                gate_selections['_constraints_added'] = set()
            gate_selections['_constraints_added'].add(layer)
            
        # ---------------------------------------------------------- I
        for (gate,q), sel in single_sel.items():
            if gate != 'I': continue
            for a in range(vec_len):
                eq_expr = out[a] == inp[a]
                add_implies(sel, eq_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)

        # ---------------------------------------------------------- H
        for (gate,q), sel in single_sel.items():
            if gate != 'H': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                b = a ^ (1 << q)
                visited.update([a,b])
                if complex_representation == Complex:
                    eq1_expr = out[a] == ((inp[a] + inp[b]) * inv_sqrt2)
                    eq2_expr = out[b] == ((inp[a] + (inp[b] * minus1)) * inv_sqrt2)
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
                elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                    eq1_expr = out[a] == (inp[a] + inp[b]).divide_by_sqrt2(self.gen)
                    eq2_expr = out[b] == (inp[a] + (inp[b].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen)
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
                    # Increment k when Hadamard is applied
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                    add_k_incr(sel, out.k, inp.k, 1)
                    
        # ---------------------------------------------------------- S
        for (gate,q), sel in single_sel.items():
            if gate != 'S': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * i_phase)
                        add_implies(sel, eq_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == inp[a].multiply_by_i(self.gen)
                        add_implies(sel, eq_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- Sdg
        for (gate,q), sel in single_sel.items():
            if gate != 'Sdg': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * i_phase)
                        add_implies(sel, eq_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == inp[a].multiply_by_minus_i(self.gen)
                        add_implies(sel, eq_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)

        # ---------------------------------------------------------- T
        for (gate,q), sel in single_sel.items():
            if gate != 'T': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * t_phase)
                        add_implies(sel, eq_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == inp[a].multiply_by_omega(self.gen)
                        add_implies(sel, eq_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)

        # ---------------------------------------------------------- Tdg
        for (gate,q), sel in single_sel.items():
            if gate != 'Tdg': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * t_phase.conjugate(self.gen))
                        add_implies(sel, eq_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == inp[a].multiply_by_omega_counter(self.gen)
                        add_implies(sel, eq_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- X
        for (gate,q), sel in single_sel.items():
            if gate != 'X': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                b = a ^ (1 << q)  # Flip bit q
                visited.update([a, b])
                # X gate swaps amplitudes: |0> <-> |1>
                eq1_expr = out[a] == inp[b]
                eq2_expr = out[b] == inp[a]
                add_implies(sel, eq1_expr)
                add_implies(sel, eq2_expr)
            # k stays the same for X gate
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- SX
        for (gate,q), sel in single_sel.items():
            if gate != 'SX': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                b = a ^ (1 << q)
                visited.update([a,b])
                if complex_representation == Complex:
                    eq1_expr = out[a] == (((inp[a] + inp[b]) * one_half)  + (inp[a] - inp[b]) * i_half)
                    eq2_expr = out[b] == (((inp[a] + inp[b]) * one_half)  + (inp[b] - inp[a]) * i_half)
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
                elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                    eq1_expr = out[a] == (((inp[a] + inp[b]))  + (inp[a] - inp[b]).multiply_by_i(self.gen))
                    eq2_expr = out[b] == (((inp[a] + inp[b]))  + (inp[b] - inp[a]).multiply_by_i(self.gen))
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
                    add_k_incr(sel, out.k, inp.k, 2)
                    
        for (gate,q), sel in single_sel.items():
            if gate != 'SXdg': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                b = a ^ (1 << q)
                visited.update([a,b])
                if complex_representation == Complex:
                    eq1_expr = out[a] == (((inp[a] + inp[b]) * one_half)  + (inp[b] - inp[a]) * i_half)
                    eq2_expr = out[b] == (((inp[a] + inp[b]) * one_half)  + (inp[a] - inp[b]) * i_half)
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
                elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                    eq1_expr = out[a] == (((inp[a] + inp[b]))  + (inp[b] - inp[a]).multiply_by_i(self.gen))
                    eq2_expr = out[b] == (((inp[a] + inp[b]))  + (inp[a] - inp[b]).multiply_by_i(self.gen))
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
                    add_k_incr(sel, out.k, inp.k, 2)
        
        # ---------------------------------------------------------- Y
        for (gate,q), sel in single_sel.items():
            if gate != 'Y': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                b = a ^ (1 << q)
                visited.update([a, b])
                bit = (a >> q) & 1
                if bit == 0:
                    if complex_representation == Complex:
                        eq1_expr = out[b] == (inp[a] * i_phase)
                        eq2_expr = out[a] == (inp[b] * i_phase.conjugate(self.gen))
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq1_expr = out[b] == inp[a].multiply_by_i(self.gen)
                        eq2_expr = out[a] == inp[b].multiply_by_minus_i(self.gen)
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
                else:
                    if complex_representation == Complex:
                        eq1_expr = out[b] == (inp[a] * i_phase.conjugate(self.gen))
                        eq2_expr = out[a] == (inp[b] * i_phase)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq1_expr = out[b] == inp[a].multiply_by_minus_i(self.gen)
                        eq2_expr = out[a] == inp[b].multiply_by_i(self.gen)
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
            # k stays the same for Y gate
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
        
        # ---------------------------------------------------------- Z
        for (gate,q), sel in single_sel.items():
            if gate != 'Z': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * minus1)
                        add_implies(sel, eq_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == inp[a].multiply_by_minus_one(self.gen)
                        add_implies(sel, eq_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
        

        # ---------------------------------------------------------- CX
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CX': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                if not control_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ (1 << t)
                    eq1_expr = out[a] == inp[b]
                    eq2_expr = out[b] == inp[a]
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
            # k stays the same for CNOT gate
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- xCX
        for (gate, c, t), sel in two_sel.items():
            if gate != 'XCX': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                if control_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ (1 << t)
                    eq1_expr = out[a] == inp[b]
                    eq2_expr = out[b] == inp[a]
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- DCX
        # DCX (Double-CNOT) gate: permutation gate with truth table:
        # |00> -> |00>, |01> -> |10>, |10> -> |11>, |11> -> |01>
        for (gate, c, t), sel in two_sel.items():
            if gate != 'DCX': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                control_on = ((a >> c) & 1) == 1
                target_on = ((a >> t) & 1) == 1
                
                if not control_on and not target_on:
                    # |00> -> |00>
                    b = a
                elif not control_on and target_on:
                    # |01> -> |10>
                    b = a ^ ((1 << c) | (1 << t))
                elif control_on and not target_on:
                    # |10> -> |11>
                    b = a ^ (1 << t)
                else:  # control_on and target_on
                    # |11> -> |01>
                    b = a ^ (1 << c)
                    
                    eq_expr = out[b] == inp[a]
                    add_implies(sel, eq_expr)
                    visited.add(a)
            
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- CH
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CH': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                control_on = ((a >> c) & 1) == 1
                if not control_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ (1 << t)
                    visited.update([a, b])
                    if complex_representation == Complex:
                        eq1_expr = out[a] == ((inp[a] + inp[b]) * inv_sqrt2)
                        eq2_expr = out[b] == ((inp[a] + (inp[b] * minus1)) * inv_sqrt2)
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq1_expr = out[a] == (inp[a] + inp[b]).divide_by_sqrt2(self.gen)
                        eq2_expr = out[b] == (inp[a] + (inp[b].multiply_by_minus_one(self.gen))).divide_by_sqrt2(self.gen)
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
                    add_k_incr(sel, out.k, inp.k, 1)
        
        # ---------------------------------------------------------- ECR
        for (gate, c, t), sel in two_sel.items():
            if gate != 'ECR': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on = ((a >> t) & 1) == 1
                if control_on and target_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                        
        # ---------------------------------------------------------- CSX
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CSX': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                control_on = ((a >> c) & 1) == 1
                if not control_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ (1 << t)
                    visited.update([a,b])
                    if complex_representation == Complex:
                        eq1_expr = out[a] == (((inp[a] + inp[b]) * one_half)  + (inp[a] - inp[b]) * i_half)
                        eq2_expr = out[b] == (((inp[a] + inp[b]) * one_half)  + (inp[b] - inp[a]) * i_half)
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq1_expr = out[a] == (((inp[a] + inp[b]))  + (inp[a] - inp[b]).multiply_by_i(self.gen))
                        eq2_expr = out[b] == (((inp[a] + inp[b]))  + (inp[b] - inp[a]).multiply_by_i(self.gen))
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
                    add_k_incr(sel, out.k, inp.k, 2)
                        
        # ---------------------------------------------------------- CY
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CY': continue
            visited = set()
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on  = ((a >> t) & 1) == 1
                
                if not control_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ (1 << t)
                    visited.update([a, b])
                    if control_on and not target_on:
                        # swap and multiply by -i
                        eq1_expr = out[a] == inp[b].multiply_by_minus_i(self.gen)
                        eq2_expr = out[b] == inp[a].multiply_by_i(self.gen)
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
                    
                    elif control_on and target_on:
                        # swap and multiply by i
                        eq1_expr = out[a] == inp[b].multiply_by_i(self.gen)
                        eq2_expr = out[b] == inp[a].multiply_by_minus_i(self.gen)
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)

            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
        
        # ---------------------------------------------------------- CZ
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CZ': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on  = ((a >> t) & 1) == 1

                if control_on and target_on:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * minus1)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == (inp[a].multiply_by_minus_one(self.gen))
                else:
                    eq_expr = out[a] == inp[a]

                add_implies(sel, eq_expr)

            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)

        # ---------------------------------------------------------- CS
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CS': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on  = ((a >> t) & 1) == 1

                if control_on and target_on:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * i_phase)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == (inp[a].multiply_by_i(self.gen))
                else:
                    eq_expr = out[a] == inp[a]

                add_implies(sel, eq_expr)

            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- CSdg
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CSdg': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on  = ((a >> t) & 1) == 1

                if control_on and target_on:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * minus1 * i_phase)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == (inp[a].multiply_by_minus_i(self.gen))
                else:
                    eq_expr = out[a] == inp[a]

                add_implies(sel, eq_expr)

            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- SWAP
        for (gate, q1, q2), sel in two_sel.items():
            if gate != 'SWAP': continue
            for a in range(vec_len):
                q1_on = ((a >> q1) & 1)
                q2_on = ((a >> q2) & 1)
                if q1_on == q2_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ ((1 << q1) | (1 << q2))
                    eq_expr = out[a] == inp[b]
                    add_implies(sel, eq_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- iSWAP
        for (gate, q1, q2), sel in two_sel.items():
            if gate != 'iSWAP': continue
            for a in range(vec_len):
                q1_on = ((a >> q1) & 1)
                q2_on = ((a >> q2) & 1)
                if q1_on == q2_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ ((1 << q1) | (1 << q2))
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[b] * i_phase)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == (inp[b].multiply_by_i(self.gen))
                    add_implies(sel, eq_expr)
        
        # ---------------------------------------------------------- sqrtSWAP
        for (gate, q1, q2), sel in two_sel.items():
            if gate != 'sqrtSWAP': continue
            visited = set()
            for a in range(vec_len):
                q1_on = ((a >> q1) & 1)
                q2_on = ((a >> q2) & 1)
                if a in visited: continue
                if q1_on == q2_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ ((1 << q1) | (1 << q2))
                    visited.update([a, b])
                    if complex_representation == Complex:
                        eq1_expr = out[a] == (((inp[a] + inp[b]) * one_half)  + (inp[a] - inp[b]) * i_half)
                        eq2_expr = out[b] == (((inp[a] + inp[b]) * one_half)  + (inp[b] - inp[a]) * i_half)
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq1_expr = out[a] == (((inp[a] + inp[b]))  + (inp[a] - inp[b]).multiply_by_i(self.gen))
                        eq2_expr = out[b] == (((inp[a] + inp[b]))  + (inp[b] - inp[a]).multiply_by_i(self.gen))
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                k_eq = f"(= {out.k} (+ {inp.k} 2))"
                add_implies(sel, k_eq)
        
        # ---------------------------------------------------------- isqrtSWAP
        for (gate, q1, q2), sel in two_sel.items():
            if gate != 'isqrtSWAP': continue
            visited = set()
            for a in range(vec_len):
                q1_on = ((a >> q1) & 1)
                q2_on = ((a >> q2) & 1)
                if a in visited: continue
                if q1_on == q2_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ ((1 << q1) | (1 << q2))
                    visited.update([a, b])
                    if complex_representation == Complex:
                        eq1_expr = out[a] == ((inp[a] + (inp[b] * i_phase)) * inv_sqrt2)
                        eq2_expr = out[b] == (((inp[a] * i_phase) + (inp[b])) * inv_sqrt2)
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq1_expr = out[a] == ((inp[a] + (inp[b].multiply_by_i(self.gen))))
                        eq2_expr = out[b] == ((inp[a].multiply_by_i(self.gen)) + (inp[b]))
                        add_implies(sel, eq1_expr)
                        add_implies(sel, eq2_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                k_eq = f"(= {out.k} (+ {inp.k} 1))"
                add_implies(sel, k_eq)
                    
        # ---------------------------------------------------------- CCX
        for (gate, c1, c2, t), sel in three_sel.items():
            if gate != 'CCX': continue
            for a in range(vec_len):
                control1_on = ((a >> c1) & 1) == 1
                control2_on = ((a >> c2) & 1) == 1
                if not control1_on or not control2_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ (1 << t)
                    eq1_expr = out[a] == inp[b]
                    eq2_expr = out[b] == inp[a]
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- RCCX
        for (gate, c1, c2, t), sel in three_sel.items():
            if gate != 'RCCX': continue
            for a in range(vec_len):
                control1_on = ((a >> c1) & 1) == 1
                control2_on = ((a >> c2) & 1) == 1
                target_on = ((a >> t) & 1) == 1
                if target_on and control1_on and not control2_on:
                    # the minus one
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * minus1)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == (inp[a].multiply_by_minus_one(self.gen))
                    add_implies(sel, eq_expr)
                elif not control1_on or not control2_on:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
                else:
                    b = a ^ (1 << t)
                    eq1_expr = out[a] == inp[b]
                    eq2_expr = out[b] == inp[a]
                    add_implies(sel, eq1_expr)
                    add_implies(sel, eq2_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- CSWAP
        for (gate, c1, c2, t), sel in three_sel.items():
            control = c1
            target1 = c2
            target2 = t
            if gate != 'CSWAP': continue
            visited = set()
            for a in range(vec_len):
                control_on = ((a >> control) & 1) == 1
                target1_on = ((a >> target1) & 1) == 1
                target2_on = ((a >> target2) & 1) == 1
                if a in visited: continue
                if control_on:
                    # apply swap between target1 and target2
                    if target1_on == target2_on:
                        eq_expr = out[a] == inp[a]
                        add_implies(sel, eq_expr)
                    else:
                        b = a ^ ((1 << target1) | (1 << target2))
                        eq_expr = out[a] == inp[b]
                        add_implies(sel, eq_expr)
                    
                else:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
            
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)
                
        # ---------------------------------------------------------- CCZ
        for (gate, c1, c2, t), sel in three_sel.items():
            if gate != 'CCZ': continue
            for a in range(vec_len):
                control1_on = ((a >> c1) & 1) == 1
                control2_on = ((a >> c2) & 1) == 1
                target_on = ((a >> t) & 1) == 1
                if control1_on and control2_on and target_on:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * minus1)
                    elif complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                        eq_expr = out[a] == (inp[a].multiply_by_minus_one(self.gen))
                else:
                    eq_expr = out[a] == inp[a]
                    add_implies(sel, eq_expr)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                add_k_eq(sel, out.k, inp.k)

    def synthesis(self, vector_pairs, n, d1, output_file="formula.smt2", pauli=False, pauli_input=None):
        """
        vector_pairs: List of (input_vector, output_vector) pairs for input and its expected output.
        n: Number of qubits
        d1: Number of layers (operations)
        output_file: Filename to write the formula to
        TODO: rescaling with multiple vectors
        """
        self.formula_file = output_file
        if pauli:
            syn_pauli(pauli_input, n, d1, output_file)
            return
    
        if n is None or d1 is None:
            raise ValueError("n and d1 are required")
        
        self.n = n
        self.d1 = d1
        
        if not vector_pairs:
            raise ValueError("vector_pairs is required")

        # check which complex representation we are using by the input vectors
        complex_representation = None
        for pair_idx, (input_vec, output_vec) in enumerate(vector_pairs):
            if input_vec[0].__class__ != output_vec[0].__class__:
                raise ValueError("input_vec and output_vec have different complex representations")
            for val in input_vec.vec:
                if isinstance(val, Complex):
                    complex_representation = Complex
                    break
                elif isinstance(val, Cyclotomic8Dyadic):
                    complex_representation = Cyclotomic8Dyadic
                    break
                elif isinstance(val, nTuple):
                    complex_representation = nTuple
                    break
            if complex_representation is None:
                raise ValueError("input_vec and output_vec have different complex representations")
            
        
        vec_len = 2**n
        
        for pair_idx, (input_vec, output_vec) in enumerate(vector_pairs):
            if len(input_vec.vec) != vec_len:
                raise ValueError("input_vec and output_vec have different lengths")
            if len(output_vec.vec) != vec_len:
                raise ValueError("input_vec and output_vec have different lengths")
        
        if complex_representation == Complex:
            inv_sqrt2 = complex_representation.inv_sqrt2(self.gen)
            minus1    = complex_representation.minus_one(self.gen)
            i_phase   = complex_representation.i_phase(self.gen)
            t_phase   = complex_representation.t_phase(self.gen)
            one_half  = complex_representation.one_half(self.gen)
            i_half    = complex_representation.i_half(self.gen)
        else:
            inv_sqrt2 = None
            minus1 = None
            i_phase = None
            t_phase = None
            one_half = None
            i_half = None
        

        for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
            In = Vector(q=vec_len, name=f"In_{pair_idx}", generator=self.gen, element_representation=complex_representation, k = input_vector.k, n = input_vector.n)
            for i, val in enumerate(input_vector.vec):
                self.gen.add_assertion(In[i] == val)
            
            # Assert that In.k equals the input_vector.k value
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                if isinstance(input_vector.k, int):
                    self.gen.add_assertion(f"(= {In.k} {input_vector.k})")
                elif isinstance(input_vector.k, str) and input_vector.k != In.k:
                    self.gen.add_assertion(f"(= {In.k} {input_vector.k})")
            
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                inter = [Vector(q=vec_len, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=complex_representation, k=input_vector.k if d == 0 else 0, n = input_vector.n) for d in range(d1 + 1)]
            else:
                inter = [Vector(q=vec_len, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=complex_representation) for d in range(d1 + 1)]
            self.gen.add_assertion(inter[0] == In)
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                self.gen.add_assertion(f"(= {inter[0].k} {In.k})")
            
            for d in range(d1):
                self.encode_layer(inter[d], inter[d+1], d, n, vec_len, inv_sqrt2, minus1, i_phase, t_phase, one_half, i_half, complex_representation)
            
            Target = Vector(q=vec_len, name=f"Target_{pair_idx}", generator=self.gen, element_representation=complex_representation, k = output_vector.k, n = output_vector.n)
            for i, val in enumerate(output_vector.vec):
                self.gen.add_assertion(Target[i] == val)
            
            if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
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
                    conjugate = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Conjugate")
                    self.gen.add_assertion(conjugate == inter[d1].conjugate())
                    self.gen.add_assertion(f"(= {conjugate.k} {inter[d1].k})")
                    prod, k_final = conjugate * Target
                    prod_real = prod.abs2(k_final) # abs2 <==> fidelity
                    self.gen.add_assertion(f"(= {fidelity.real} {prod_real})")
                    self.gen.add_assertion(f"(>= {fidelity.real} 0.0)")
                    self.gen.add_assertion(f"(<= {fidelity.real} 1.0)")
                    #self.gen.maximize(f"{fidelity.real}"
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
                    self.gen.add_assertion(f"(ite (< {inter[d1].k} {Target.k}) (= n{pair_idx} (- {Target.k} {inter[d1].k})) (= n{pair_idx} (- {inter[d1].k} {Target.k})))")
                    self.gen.declare_real(f"k{pair_idx}")
                    self.gen.add_assertion(f"(and (>= n{pair_idx} (* 2 k{pair_idx})) (< n{pair_idx} (* 2 (+ k{pair_idx} 1))))")
                    rescaled1 = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Rescaled1_{inter[d1].name}")
                    rescaled2 = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Rescaled2_{Target.name}")
                    # enumerate possible k's <0, d1/2>
                    # calculate the power and parity check (n - 2k) == 0 if even
                    self.gen.enumerate_k_values(d1//2, pair_idx)
                    self.gen.declare_real(f"pow2{pair_idx}")
                    self.gen.add_assertion(f"(= pow2{pair_idx} (pow 2 k{pair_idx})))")
                    self.gen.declare_real(f"r")
                    self.gen.add_assertion(f"(= r (- n{pair_idx} (* 2 k{pair_idx})))")
                    self.gen.declare_bool(f"is_even{pair_idx}")
                    self.gen.add_assertion(f"(ite (= r 0) (= is_even{pair_idx} true) (= is_even{pair_idx} false))")
                    self.gen.add_rescaling(rescaled1, rescaled2, inter[d1], Target, pair_idx, d1)
                    self.gen.add_assertion(rescaled1 == rescaled2)
                elif self.gen.logic == "QF_NIA":
                    # QF_NIA branch
                    # rescaling -- add enumeration of all possible powers of 2,
                    # calculate 2^(floor(n/2)) * M * vector
                    # n == abs(last_k - target_k)
                    self.gen.declare_integer(f"n{pair_idx}")
                    self.gen.add_assertion(f"(ite (< {inter[d1].k} {Target.k}) (= n{pair_idx} (- {Target.k} {inter[d1].k})) (= n{pair_idx} (- {inter[d1].k} {Target.k})))")
                    self.gen.enumerate_powers_of_2(d1 + 1, pair_idx)
                    # after that, rescale the vectors -- create 2 new vectors, the one with lower k gets rescaled, the other one just gets copied
                    # then, compare them
                    rescaled1 = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Rescaled1_{inter[d1].name}")
                    rescaled2 = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Rescaled2_{Target.name}")
                    self.gen.add_rescaling(rescaled1, rescaled2, inter[d1], Target, pair_idx, d1)
                    self.gen.add_assertion(rescaled1 == rescaled2)
                elif self.gen.logic == "QF_LIA":
                    # QF_LIA branch -- same rescaling as QF_NIA, but enumarates all possible outcomes for 2^(floor(n/2)), allowing rescaling by constant
                    self.gen.declare_integer(f"n{pair_idx}")
                    self.gen.declare_integer(f"k{pair_idx}")
                    self.gen.add_assertion(f"(= k{pair_idx} (div n{pair_idx} 2))")
                    self.gen.add_assertion(f"(ite (< {inter[d1].k} {Target.k}) (= n{pair_idx} (- {Target.k} {inter[d1].k})) (= n{pair_idx} (- {inter[d1].k} {Target.k})))")
                    rescaled1 = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Rescaled1_{inter[d1].name}")
                    rescaled2 = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Rescaled2_{Target.name}")
                    self.gen.add_rescaling(rescaled1, rescaled2, inter[d1], Target, pair_idx, d1)
                    self.gen.add_assertion(rescaled1 == rescaled2)
                else:
                    raise ValueError("invalid logic")
        
        # add constraining rules - no H H, Tdg T, ...
        self.gen.remove_identities(self.gate_set, n, d1)
        
        smtlib_content = self.gen.generate(complex_representation)
        with open(output_file, 'w') as f:
            f.write(smtlib_content)


    def synthesis_gate_optimal(self, vector_pairs, n, d1, output_file="formula.smt2", pauli=False, pauli_input=None, output_qasm="circuit.qasm"):
        """
        use incremental solving to get the minimum number of gates in the resulting circuit
        uses pySMT and Cyclotomic8Dyadic
        """
        self.formula_file = output_file
        if pauli:
            syn_pauli(pauli_input, n, d1, output_file)
            return
    
        if n is None or d1 is None:
            raise ValueError("n and d1 are required")
        
        self.n = n
        self.d1 = d1
        
        if not vector_pairs:
            raise ValueError("vector_pairs is required")

        # check which complex representation we are using by the input vectors
        complex_representation = None
        for pair_idx, (input_vec, output_vec) in enumerate(vector_pairs):
            if input_vec[0].__class__ != output_vec[0].__class__:
                raise ValueError("input_vec and output_vec have different complex representations")
            for val in input_vec.vec:
                if isinstance(val, Complex):
                    complex_representation = Complex
                    break
                elif isinstance(val, Cyclotomic8Dyadic):
                    complex_representation = Cyclotomic8Dyadic
                    break
                elif isinstance(val, nTuple):
                    complex_representation = nTuple
                    break
            if complex_representation is None:
                raise ValueError("input_vec and output_vec have different complex representations")
            
        
        vec_len = 2**n
        
        for pair_idx, (input_vec, output_vec) in enumerate(vector_pairs):
            if len(input_vec.vec) != vec_len:
                raise ValueError("input_vec and output_vec have different lengths")
            if len(output_vec.vec) != vec_len:
                raise ValueError("input_vec and output_vec have different lengths")
        
        if complex_representation == Complex:
            inv_sqrt2 = complex_representation.inv_sqrt2(self.gen)
            minus1    = complex_representation.minus_one(self.gen)
            i_phase   = complex_representation.i_phase(self.gen)
            t_phase   = complex_representation.t_phase(self.gen)
            one_half  = complex_representation.one_half(self.gen)
            i_half    = complex_representation.i_half(self.gen)
        else:
            inv_sqrt2 = None
            minus1 = None
            i_phase = None
            t_phase = None
            one_half = None
            i_half = None
            
        self.add_solvers()
        logic = "QF_NIA"
        solvers = ["z3", "cvc5", "yices2", "smtinterpol"]

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
                In = Vector(q=vec_len, name=f"In_{pair_idx}", generator=self.gen, element_representation=complex_representation, k = input_vector.k, n = input_vector.n)
                for i, val in enumerate(input_vector.vec):
                    self.gen.add_assertion(In[i] == val)
        
                if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                    if self.gen.name == 'PortfolioSolver':
                        input_k_expr = self.gen.format_integer(input_vector.k)
                        self.gen.add_assertion(Equals(In.k, input_k_expr))
                    else:
                        self.gen.add_assertion(f"(= {In.k} {int(input_vector.k)})")

                # intermediate vectors generation
                if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                    inter = [Vector(q=vec_len, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=complex_representation, k=input_vector.k if d == 0 else 0, n = input_vector.n) for d in range(d1 + 1)]
                else:
                    inter = [Vector(q=vec_len, name=f"I_{pair_idx}_{d}", generator=self.gen, element_representation=complex_representation) for d in range(d1 + 1)]
                self.gen.add_assertion(inter[0] == In)
                if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                    if self.gen.name == 'PortfolioSolver':
                        self.gen.add_assertion(Equals(inter[0].k, In.k))
                    else:
                        self.gen.add_assertion(f"(= {inter[0].k} {In.k})")
                inter_vectors.append(inter)
                # generate target vector and connect it to output values
                Target = Vector(q=vec_len, name=f"Target_{pair_idx}", generator=self.gen, element_representation=complex_representation, k = output_vector.k, n = output_vector.n)
                for i, val in enumerate(output_vector.vec):
                    self.gen.add_assertion(Target[i] == val)
                
                if complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple:
                    if self.gen.name == 'PortfolioSolver':
                        output_k_expr = self.gen.format_integer(output_vector.k)
                        self.gen.add_assertion(Equals(Target.k, output_k_expr))
                    else:
                        self.gen.add_assertion(f"(= {Target.k} {int(output_vector.k)})")
                target_vectors.append(Target)
            depth = 1
            solved = False
            while depth <= d1 and not solved:
                for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
                    inter = inter_vectors[pair_idx]
                    # encode new layer (depth-1) and connect inter[depth-1] to inter[depth]
                    self.encode_layer(inter[depth-1], inter[depth], depth-1, n, vec_len, inv_sqrt2, minus1, i_phase, t_phase, one_half, i_half, complex_representation)
                self.gen.solver.push()
                
                # inter[depth] == Target
                for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
                    inter = inter_vectors[pair_idx]
                    Target = target_vectors[pair_idx]
                    
                    if self.gen.logic == "QF_NRA" and (complex_representation == Cyclotomic8Dyadic or complex_representation == nTuple):
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
                        if complex_representation == Cyclotomic8Dyadic:
                            self.gen.declare_integer(f"n{pair_idx}")
                            self.gen.add_assertion(Ite(LT(inter[depth].k, Target.k), Equals(self.gen.symbols[f"n{pair_idx}"], Minus(Target.k, inter[depth].k)), Equals(self.gen.symbols[f"n{pair_idx}"], Minus(inter[depth].k, Target.k))))
                            self.gen.enumerate_powers_of_2(depth + 1, pair_idx)
                            # after that, rescale the vectors -- create 2 new vectors, the one with lower k gets rescaled, the other one just gets copied
                            # then, compare them
                            rescaled1 = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Rescaled1_{inter[depth].name}")
                            rescaled2 = Vector(q=vec_len, generator=self.gen, element_representation=complex_representation, k=0, n=n, name=f"Rescaled2_{Target.name}")
                            self.gen.add_rescaling(rescaled1, rescaled2, inter[depth], Target, pair_idx, depth)
                            self.gen.add_assertion(rescaled1 == rescaled2)
                    else:
                        self.gen.add_assertion(inter[depth] == Target)
                #print(f"Solving with {self.gen.name}...")
                result = self.gen.solver.solve()
                                
                #print(f"Result: {result}")
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
                parse_pysmt(model, n, d1, output_qasm, result)
                return True

                

    def solve_and_extract_circuit(self, smtlib_filename, n, d1, output_qasm="circuit.qasm", solver=None) -> bool:
        """    
            smtlib_filename: Path to the SMT-LIB file
            n: Number of qubits
            d1: Number of layers
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
        
        if smtlib_filename is None and hasattr(self, 'formula_file') and self.formula_file is not None:
            smtlib_filename = self.formula_file
        elif smtlib_filename is None:
            raise ValueError("smtlib_filename is None")
        
        if n is None and hasattr(self, 'n') and self.n is not None:
            n = self.n
        elif n is None:
            raise ValueError("n is None")
        
        if d1 is None and hasattr(self, 'd1') and self.d1 is not None:
            d1 = self.d1
        elif d1 is None:
            raise ValueError("d1 is None")
        
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
            parse_map[solver](result.stdout, n, d1, output_qasm, result)
            return True
        except Exception as e:
            raise ValueError(f"Error: {e}")
            return False