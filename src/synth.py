import numpy as np
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator
from qasm import parse_z3, parse_z3alpha, parse_cvc5, parse_opensmt, parse_smtinterpol, parse_yices2
import time
import resource
import subprocess
import os

def synthesis(vector_pairs, n, d1, output_file="formula.smt2", gen=None, gate_set=None):
    """
    vector_pairs: List of (input_vector, output_vector) pairs for input and its expected output.
    n: Number of qubits
    d1: Number of layers (operations)
    output_file: Filename to write the formula to
    """
    if gen is None:
        raise ValueError()
    
    if gate_set is None:
        raise ValueError()
    
    if not vector_pairs:
        raise ValueError()

    # check which complex representation we are using by the input vectors
    for pair_idx, (input_vec, output_vec) in enumerate(vector_pairs):
        if input_vec[0].__class__ != output_vec[0].__class__:
            raise ValueError()
        for val in input_vec.vec:
            if isinstance(val, Complex):
                complex_representation = Complex
                break
            elif isinstance(val, Cyclotomic8Dyadic):
                complex_representation = Cyclotomic8Dyadic
                break
        if complex_representation is None:
            raise ValueError()
        
    
    vec_len = 2**n
    
    for pair_idx, (input_vec, output_vec) in enumerate(vector_pairs):
        if len(input_vec.vec) != vec_len:
            raise ValueError()
        if len(output_vec.vec) != vec_len:
            raise ValueError()
    
    inv_sqrt2 = complex_representation.inv_sqrt2(gen)
    minus1    = complex_representation.minus_one(gen)
    i_phase   = complex_representation.i_phase(gen)
    t_phase   = complex_representation.t_phase(gen)
    one_half  = complex_representation.one_half(gen)
    i_half    = complex_representation.i_half(gen)
    

    def encode_layer(gen, inp, out, layer, n, vec_len, inv_sqrt2, minus1, i_phase, t_phase, one_half, i_half, gate_selections, gate_set):
        single_sel = {}
        two_sel = {}
        three_sel = {}
        sel_vars = []
        supported_single_qubit = ['H','S','Sdg','T','I','Tdg','X','Y','Z','SX','SXdg']
        supported_two_qubit = ['CX','SWAP', 'iSWAP', 'CH','CS','CSdg','CY','CZ','DCX','CSX', 'XCX', 'ECR', 'MAGIC', 'sqrtSWAP', 'isqrtSWAP']
        supported_three_qubit = ['CCX','CSWAP','CCZ', 'RCCX', 'PG']
        
        # todo: ecr (echoed dross resonance), magic, pg
        
        # implicitly add identity to the gate set if not present
        if 'I' not in gate_set:
            gate_set.append('I')
        
        supported_single_qubit = [gate for gate in supported_single_qubit if gate in gate_set]
        supported_two_qubit = [gate for gate in supported_two_qubit if gate in gate_set]
        supported_three_qubit = [gate for gate in supported_three_qubit if gate in gate_set]
        
        # check if the gate set has any unsupported gates
        unsupported_gates = set(gate_set) - set(supported_single_qubit) - set(supported_two_qubit) - set(supported_three_qubit)
        if unsupported_gates:
            raise ValueError(f"Unsupported gates: {unsupported_gates}")
        
        # ---- single-qubit gates ----
        for gate in supported_single_qubit:
            for q in range(n):
                key = (layer, gate, q)
                if key not in gate_selections:
                    v_name = f"L{layer}_{gate}_q{q}"
                    v = gen.declare_bool(v_name)
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
                        v = gen.declare_bool(v_name)
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
                            v = gen.declare_bool(v_name)
                            gate_selections[key] = v
                        three_sel[(gate, c1, c2, t)] = gate_selections[key]
                        sel_vars.append(gate_selections[key])

        # ---- exactly ONE gate per layer (only add constraints once per layer) ----
        if layer not in gate_selections.get('_constraints_added', set()):
            at_least = f"(or {' '.join(sel_vars)})"
            gen.add_assertion(at_least)
            
            for i, v1 in enumerate(sel_vars):
                for v2 in sel_vars[i+1:]:
                    gen.add_assertion(f"(=> {v1} (not {v2}))")
                    gen.add_assertion(f"(=> {v2} (not {v1}))")
            
            if '_constraints_added' not in gate_selections:
                gate_selections['_constraints_added'] = set()
            gate_selections['_constraints_added'].add(layer)
        
        # ---------------------------------------------------------- I
        for (gate,q), sel in single_sel.items():
            if gate != 'I': continue
            for a in range(vec_len):
                eq_expr = out[a] == inp[a]
                gen.add_assertion(f"(=> {sel} {eq_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")

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
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
                elif complex_representation == Cyclotomic8Dyadic:
                    eq1_expr = out[a] == (inp[a] + inp[b]).divide_by_sqrt2(gen)
                    eq2_expr = out[b] == (inp[a] + (inp[b].multiply_by_minus_one(gen))).divide_by_sqrt2(gen)
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
                    # Increment k when Hadamard is applied
            if complex_representation == Cyclotomic8Dyadic:
                k_incr = f"(= {out.k} (+ {inp.k} 1))"
                gen.add_assertion(f"(=> {sel} {k_incr})")

        # ---------------------------------------------------------- S
        for (gate,q), sel in single_sel.items():
            if gate != 'S': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * i_phase)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == inp[a].multiply_by_i(gen)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
        # ---------------------------------------------------------- Sdg
        for (gate,q), sel in single_sel.items():
            if gate != 'Sdg': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * i_phase)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == inp[a].multiply_by_minus_i(gen)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")

        # ---------------------------------------------------------- T
        for (gate,q), sel in single_sel.items():
            if gate != 'T': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * t_phase)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == inp[a].multiply_by_omega(gen)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")

        # ---------------------------------------------------------- Tdg
        for (gate,q), sel in single_sel.items():
            if gate != 'Tdg': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * t_phase.conjugate(gen))
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == inp[a].multiply_by_omega_counter(gen)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
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
                gen.add_assertion(f"(=> {sel} {eq1_expr})")
                gen.add_assertion(f"(=> {sel} {eq2_expr})")
            # k stays the same for X gate
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
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
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
                elif complex_representation == Cyclotomic8Dyadic:
                    eq1_expr = out[a] == (((inp[a] + inp[b]))  + (inp[a] - inp[b]).multiply_by_i(gen))
                    eq2_expr = out[b] == (((inp[a] + inp[b]))  + (inp[b] - inp[a]).multiply_by_i(gen))
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
                    k_incr = f"(= {out.k} (+ {inp.k} 2))"
                    gen.add_assertion(f"(=> {sel} {k_incr})")
                    
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
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
                elif complex_representation == Cyclotomic8Dyadic:
                    eq1_expr = out[a] == (((inp[a] + inp[b]))  + (inp[b] - inp[a]).multiply_by_i(gen))
                    eq2_expr = out[b] == (((inp[a] + inp[b]))  + (inp[a] - inp[b]).multiply_by_i(gen))
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
                    k_incr = f"(= {out.k} (+ {inp.k} 2))"
                    gen.add_assertion(f"(=> {sel} {k_incr})")
        
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
                        eq2_expr = out[a] == (inp[b] * i_phase.conjugate(gen))
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq1_expr = out[b] == inp[a].multiply_by_i(gen)
                        eq2_expr = out[a] == inp[b].multiply_by_minus_i(gen)
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
                else:
                    if complex_representation == Complex:
                        eq1_expr = out[b] == (inp[a] * i_phase.conjugate(gen))
                        eq2_expr = out[a] == (inp[b] * i_phase)
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq1_expr = out[b] == inp[a].multiply_by_minus_i(gen)
                        eq2_expr = out[a] == inp[b].multiply_by_i(gen)
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
            # k stays the same for Y gate
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
        
        # ---------------------------------------------------------- Z
        for (gate,q), sel in single_sel.items():
            if gate != 'Z': continue
            for a in range(vec_len):
                bit = (a >> q) & 1
                if bit == 0:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * minus1)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == inp[a].multiply_by_minus_one(gen)
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
        

        # ---------------------------------------------------------- CX
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CX': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                if not control_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ (1 << t)
                    eq1_expr = out[a] == inp[b]
                    eq2_expr = out[b] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
            # k stays the same for CNOT gate
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
        # ---------------------------------------------------------- xCX
        for (gate, c, t), sel in two_sel.items():
            if gate != 'XCX': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                if control_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ (1 << t)
                    eq1_expr = out[a] == inp[b]
                    eq2_expr = out[b] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
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
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                    visited.add(a)
            
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
        # ---------------------------------------------------------- CH
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CH': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                control_on = ((a >> c) & 1) == 1
                if not control_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ (1 << t)
                    visited.update([a, b])
                    if complex_representation == Complex:
                        eq1_expr = out[a] == ((inp[a] + inp[b]) * inv_sqrt2)
                        eq2_expr = out[b] == ((inp[a] + (inp[b] * minus1)) * inv_sqrt2)
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq1_expr = out[a] == (inp[a] + inp[b]).divide_by_sqrt2(gen)
                        eq2_expr = out[b] == (inp[a] + (inp[b].multiply_by_minus_one(gen))).divide_by_sqrt2(gen)
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
                        k_incr = f"(= {out.k} (+ {inp.k} 1))"
                        gen.add_assertion(f"(=> {sel} {k_incr})")
        
        # ---------------------------------------------------------- ECR
        for (gate, c, t), sel in two_sel.items():
            if gate != 'ECR': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on = ((a >> t) & 1) == 1
                if control_on and target_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                        
        # ---------------------------------------------------------- CSX
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CSX': continue
            visited = set()
            for a in range(vec_len):
                if a in visited: continue
                control_on = ((a >> c) & 1) == 1
                if not control_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ (1 << t)
                    visited.update([a,b])
                    if complex_representation == Complex:
                        eq1_expr = out[a] == (((inp[a] + inp[b]) * one_half)  + (inp[a] - inp[b]) * i_half)
                        eq2_expr = out[b] == (((inp[a] + inp[b]) * one_half)  + (inp[b] - inp[a]) * i_half)
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq1_expr = out[a] == (((inp[a] + inp[b]))  + (inp[a] - inp[b]).multiply_by_i(gen))
                        eq2_expr = out[b] == (((inp[a] + inp[b]))  + (inp[b] - inp[a]).multiply_by_i(gen))
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
                        k_incr = f"(= {out.k} (+ {inp.k} 2))"
                        gen.add_assertion(f"(=> {sel} {k_incr})")
                        
        # ---------------------------------------------------------- CY
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CY': continue
            visited = set()
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on  = ((a >> t) & 1) == 1
                
                if not control_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ (1 << t)
                    visited.update([a, b])
                    if control_on and not target_on:
                        # swap and multiply by -i
                        eq1_expr = out[a] == inp[b].multiply_by_minus_i(gen)
                        eq2_expr = out[b] == inp[a].multiply_by_i(gen)
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
                    
                    elif control_on and target_on:
                        # swap and multiply by i
                        eq1_expr = out[a] == inp[b].multiply_by_i(gen)
                        eq2_expr = out[b] == inp[a].multiply_by_minus_i(gen)
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")

            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
        
        # ---------------------------------------------------------- CZ
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CZ': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on  = ((a >> t) & 1) == 1

                if control_on and target_on:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * minus1)
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == (inp[a].multiply_by_minus_one(gen))
                else:
                    eq_expr = out[a] == inp[a]

                gen.add_assertion(f"(=> {sel} {eq_expr})")

            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")

        # ---------------------------------------------------------- CS
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CS': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on  = ((a >> t) & 1) == 1

                if control_on and target_on:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * i_phase)
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == (inp[a].multiply_by_i(gen))
                else:
                    eq_expr = out[a] == inp[a]

                gen.add_assertion(f"(=> {sel} {eq_expr})")

            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
        # ---------------------------------------------------------- CSdg
        for (gate, c, t), sel in two_sel.items():
            if gate != 'CSdg': continue
            for a in range(vec_len):
                control_on = ((a >> c) & 1) == 1
                target_on  = ((a >> t) & 1) == 1

                if control_on and target_on:
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[a] * minus1 * i_phase)
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == (inp[a].multiply_by_minus_i(gen))
                else:
                    eq_expr = out[a] == inp[a]

                gen.add_assertion(f"(=> {sel} {eq_expr})")

            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
        # ---------------------------------------------------------- SWAP
        for (gate, q1, q2), sel in two_sel.items():
            if gate != 'SWAP': continue
            for a in range(vec_len):
                q1_on = ((a >> q1) & 1)
                q2_on = ((a >> q2) & 1)
                if q1_on == q2_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ ((1 << q1) | (1 << q2))
                    eq_expr = out[a] == inp[b]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
        # ---------------------------------------------------------- iSWAP
        for (gate, q1, q2), sel in two_sel.items():
            if gate != 'iSWAP': continue
            for a in range(vec_len):
                q1_on = ((a >> q1) & 1)
                q2_on = ((a >> q2) & 1)
                if q1_on == q2_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ ((1 << q1) | (1 << q2))
                    if complex_representation == Complex:
                        eq_expr = out[a] == (inp[b] * i_phase)
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == (inp[b].multiply_by_i(gen))
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
        
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
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ ((1 << q1) | (1 << q2))
                    visited.update([a, b])
                    if complex_representation == Complex:
                        eq1_expr = out[a] == (((inp[a] + inp[b]) * one_half)  + (inp[a] - inp[b]) * i_half)
                        eq2_expr = out[b] == (((inp[a] + inp[b]) * one_half)  + (inp[b] - inp[a]) * i_half)
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq1_expr = out[a] == (((inp[a] + inp[b]))  + (inp[a] - inp[b]).multiply_by_i(gen))
                        eq2_expr = out[b] == (((inp[a] + inp[b]))  + (inp[b] - inp[a]).multiply_by_i(gen))
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} (+ {inp.k} 2))"
                gen.add_assertion(f"(=> {sel} {k_eq})")
        
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
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ ((1 << q1) | (1 << q2))
                    visited.update([a, b])
                    if complex_representation == Complex:
                        eq1_expr = out[a] == ((inp[a] + (inp[b] * i_phase)) * inv_sqrt2)
                        eq2_expr = out[b] == (((inp[a] * i_phase) + (inp[b])) * inv_sqrt2)
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq1_expr = out[a] == ((inp[a] + (inp[b].multiply_by_i(gen))))
                        eq2_expr = out[b] == ((inp[a].multiply_by_i(gen)) + (inp[b]))
                        gen.add_assertion(f"(=> {sel} {eq1_expr})")
                        gen.add_assertion(f"(=> {sel} {eq2_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} (+ {inp.k} 1))"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                    
        # ---------------------------------------------------------- CCX
        for (gate, c1, c2, t), sel in three_sel.items():
            if gate != 'CCX': continue
            for a in range(vec_len):
                control1_on = ((a >> c1) & 1) == 1
                control2_on = ((a >> c2) & 1) == 1
                if not control1_on or not control2_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ (1 << t)
                    eq1_expr = out[a] == inp[b]
                    eq2_expr = out[b] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
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
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == (inp[a].multiply_by_minus_one(gen))
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                elif not control1_on or not control2_on:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
                else:
                    b = a ^ (1 << t)
                    eq1_expr = out[a] == inp[b]
                    eq2_expr = out[b] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq1_expr})")
                    gen.add_assertion(f"(=> {sel} {eq2_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
        # ---------------------------------------------------------- CSWAP
        for (gate, c1, c2, t), sel in three_sel.items():
            control = c1
            target1 = c2
            target2 = t
            if gate != 'CSWAP': continue
            for a in range(vec_len):
                control_on = ((a >> control) & 1) == 1
                target1_on = ((a >> target1) & 1) == 1
                target2_on = ((a >> target2) & 1) == 1
                if a in visited: continue
                if control_on:
                    # apply swap between target1 and target2
                    if target1_on == target2_on:
                        eq_expr = out[a] == inp[a]
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
                    else:
                        b = a ^ ((1 << target1) | (1 << target2))
                        eq_expr = out[a] == inp[b]
                        gen.add_assertion(f"(=> {sel} {eq_expr})")
                    
                else:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
            
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")
                
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
                    elif complex_representation == Cyclotomic8Dyadic:
                        eq_expr = out[a] == (inp[a].multiply_by_minus_one(gen))
                else:
                    eq_expr = out[a] == inp[a]
                    gen.add_assertion(f"(=> {sel} {eq_expr})")
            if complex_representation == Cyclotomic8Dyadic:
                k_eq = f"(= {out.k} {inp.k})"
                gen.add_assertion(f"(=> {sel} {k_eq})")

    gate_selections = {}
    
    for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
        In = Vector(q=vec_len, name=f"In_{pair_idx}", generator=gen, element_representation=complex_representation, k = input_vector.k)
        for i, val in enumerate(input_vector.vec):
            gen.add_assertion(In[i] == val)
        
        # Assert that In.k equals the input_vector.k value
        if complex_representation == Cyclotomic8Dyadic:
            if isinstance(input_vector.k, int):
                gen.add_assertion(f"(= {In.k} {input_vector.k})")
            elif isinstance(input_vector.k, str) and input_vector.k != In.k:
                gen.add_assertion(f"(= {In.k} {input_vector.k})")
        
        if complex_representation == Cyclotomic8Dyadic:
            inter = [Vector(q=vec_len, name=f"I_{pair_idx}_{d}", generator=gen, element_representation=complex_representation, k=input_vector.k if d == 0 else 0) for d in range(d1 + 1)]
        else:
            inter = [Vector(q=vec_len, name=f"I_{pair_idx}_{d}", generator=gen, element_representation=complex_representation) for d in range(d1 + 1)]
        gen.add_assertion(inter[0] == In)
        
        for d in range(d1):
            encode_layer(gen, inter[d], inter[d+1], d, n, vec_len, inv_sqrt2, minus1, i_phase, t_phase, one_half, i_half, gate_selections, gate_set)
        
        Target = Vector(q=vec_len, name=f"Target_{pair_idx}", generator=gen, element_representation=complex_representation, k = output_vector.k)
        for i, val in enumerate(output_vector.vec):
            gen.add_assertion(Target[i] == val)
        
        # Assert that Target.k equals the output_vector.k value
        if complex_representation == Cyclotomic8Dyadic:
            # If output_vector.k is a literal integer, assert Target.k equals it
            # If it's already a string (symbolic), it should already be set correctly
            if isinstance(output_vector.k, int):
                gen.add_assertion(f"(= {Target.k} {output_vector.k})")
            # If output_vector.k is a string but not the same as Target.k, assert equality
            elif isinstance(output_vector.k, str) and output_vector.k != Target.k:
                gen.add_assertion(f"(= {Target.k} {output_vector.k})")
                    

        gen.add_assertion(inter[d1] == Target)
    
    smtlib_content = gen.generate(complex_representation)
    with open(output_file, 'w') as f:
        f.write(smtlib_content)

def solve_and_extract_circuit(smtlib_filename, n, d1, output_qasm="circuit.qasm", solver="z3"):
    """    
        smtlib_filename: Path to the SMT-LIB file
        n: Number of qubits
        d1: Number of layers
        output_qasm: Output filename for QASM circuit
        solver: z3, z3alpha, cvc5, opensmt, smtinterpol, yices2
    """
    solver_to_filename = {
        "z3": "z3",
        "z3alpha": "../../solvers/z3alpha/z3alpha.py",
        "cvc5": "../../solvers/cvc5/starexec_run_sq",
        "opensmt": "../../solvers/opensmt/opensmt",
        "smtinterpol": "../../solvers/smtinterpol/smtinterpol",
        "yices2": "../../solvers/yices2/yices_smt2"
    }
    if solver not in solver_to_filename:
        raise ValueError(f"Invalid solver: {solver}")
    try:
        result = subprocess.run(
            [solver_to_filename[solver], smtlib_filename],
            capture_output=True,
            text=True,
        )
        
        parse_map = {
            "z3": parse_z3,
            "z3alpha": parse_z3alpha,
            "cvc5": parse_cvc5,
            "opensmt": parse_opensmt,
            "smtinterpol": parse_smtinterpol,
            "yices2": parse_yices2
        }
        parse_map[solver](result.stdout, n, d1, output_qasm, result)
    except Exception as e:
        raise ValueError(f"Error: {e}")