import numpy as np
from complex_numbers_smtlib import Complex, Vector, Cyclotomic8Dyadic
from smtlib_generator import SMTLibGenerator
from qasm import save_to_qasm
import time
import resource
import subprocess
import os

def synthesis(vector_pairs, n, d1, output_file="formula.smt2", gen=None):
    """
    vector_pairs: List of (input_vector, output_vector) pairs for input and its expected output.
    n: Number of qubits
    d1: Number of layers (operations)
    output_file: Filename to write the formula to
    """
    if gen is None:
        raise ValueError()
    
    if not vector_pairs:
        raise ValueError()

    # check which complex representation we are using by the input vectors
    for pair_idx, (input_vec, output_vec) in enumerate(vector_pairs):
        for val in input_vec:
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
        if len(input_vec) != vec_len:
            raise ValueError()
        if len(output_vec) != vec_len:
            raise ValueError()
    
    inv_sqrt2 = complex_representation.inv_sqrt2(gen)
    minus1    = complex_representation.minus_one(gen)
    i_phase   = complex_representation.i_phase(gen)
    t_phase   = complex_representation.t_phase(gen)

    def encode_layer(gen, inp, out, layer, n, vec_len, inv_sqrt2, minus1, i_phase, t_phase, gate_selections):
        single_sel = {}
        two_sel = {}
        sel_vars = []
        # ---- single-qubit gates ----
        for gate in ['H','S','T','I']:
            for q in range(n):
                key = (layer, gate, q)
                if key not in gate_selections:
                    v_name = f"L{layer}_{gate}_q{q}"
                    v = gen.declare_bool(v_name)
                    gate_selections[key] = v
                single_sel[(gate, q)] = gate_selections[key]
                sel_vars.append(gate_selections[key])

        # ---- two-qubit gate (CNOT) ----
        for c in range(n):
            for t in range(n):
                if c == t: continue
                key = (layer, 'CNOT', c, t)
                if key not in gate_selections:
                    v_name = f"L{layer}_CNOT_c{c}t{t}"
                    v = gen.declare_bool(v_name)
                    gate_selections[key] = v
                two_sel[(c,t)] = gate_selections[key]
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

        # ---------------------------------------------------------- CNOT
        for (c,t), sel in two_sel.items():
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

    gate_selections = {}
    
    for pair_idx, (input_vector, output_vector) in enumerate(vector_pairs):
        In = Vector(q=vec_len, name=f"In_{pair_idx}", generator=gen, element_representation=complex_representation)
        for i, val in enumerate(input_vector):
            assert isinstance(val, complex_representation)
            gen.add_assertion(In[i] == val)
        
        inter = [Vector(q=vec_len, name=f"I_{pair_idx}_{d}", generator=gen, element_representation=complex_representation) for d in range(d1 + 1)]
        gen.add_assertion(inter[0] == In)
        
        for d in range(d1):
            encode_layer(gen, inter[d], inter[d+1], d, n, vec_len, inv_sqrt2, minus1, i_phase, t_phase, gate_selections)
        
        Target = Vector(q=vec_len, name=f"Target_{pair_idx}", generator=gen, element_representation=complex_representation)
        for i, val in enumerate(output_vector):
            assert isinstance(val, complex_representation)
            gen.add_assertion(Target[i] == val)
        
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
        solver: z3, cvc5
    """
    if solver not in ["z3", "cvc5"]:
        raise ValueError(f"Invalid solver: {solver}")
    try:
        result = subprocess.run(
            [solver, smtlib_filename],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            
            if output.startswith("sat"):
                model_output = result.stdout
                model_lines = model_output.split('\n')
                gate_assignments = {}
                i = 0
                while i < len(model_lines):
                    line = model_lines[i].strip()
                    if 'define-fun' in line.lower() and 'L' in line and '_' in line:
                        # (define-fun LX_GATE_qY () Bool true)
                        try:
                            start = line.find('define-fun')
                            if start >= 0:
                                start += len('define-fun')
                                end = line.find('()', start)
                                if end > start:
                                    var_name = line[start:end].strip()
                                    if var_name.startswith('L') and '_' in var_name:
                                        is_true = 'true' in line.lower()
                                        if not is_true and i + 1 < len(model_lines):
                                            next_line = model_lines[i + 1].strip().lower()
                                            if 'true' in next_line:
                                                is_true = True
                                        
                                        if is_true:
                                            gate_assignments[var_name] = True
                        except Exception:
                            pass
                    i += 1
                
                if gate_assignments:
                    class SimpleModel:
                        def __init__(self, assignments):
                            self.assignments = assignments
                        def decls(self):
                            class Decl:
                                def __init__(self, name):
                                    self.name_val = name
                                def name(self):
                                    return self.name_val
                            return [Decl(name) for name in self.assignments.keys()]
                        def __getitem__(self, decl):
                            class Value:
                                def __str__(self):
                                    return "True"
                            return Value()
                    
                    m = SimpleModel(gate_assignments)
                    save_to_qasm(n, d1, m, output_qasm)
            else:
                raise ValueError(f"Solver {solver} returned UNSAT")
        else:
            raise ValueError(f"Solver {solver} returned error: {result.stderr}")
    except Exception as e:
        raise ValueError(f"Error: {e}")