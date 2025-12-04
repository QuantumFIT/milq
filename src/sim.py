import numpy as np
from complex_numbers_smtlib import Complex, Cyclotomic8Dyadic, Vector
from smtlib_generator import SMTLibGenerator

def simulate_circuit(qasm_file):
    # simulate the qasm file and return [Vector(Complex)] for each basis state for synthesis purposes
    with open(qasm_file, 'r') as f:
        qasm_content = f.read()
    
    lines = qasm_content.split('\n')
    n_qubits = None
    gates = []
    vectors = []
    complex_representation = Cyclotomic8Dyadic
    # list of (gate, [0, 1, 2 ... ]) --> (gatestr, qubits_vector)
    parsed_file = []
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('//') or line.startswith('OPENQASM') or line.startswith('include'):
            continue
        
        if line.startswith('qreg'):
            parts = line.split('[')
            if len(parts) > 1:
                n_qubits = int(parts[1].split(']')[0])
                for i in range(2**n_qubits):
                    vectors.append(Vector(q=2**n_qubits, generator=None, element_representation=complex_representation, k=0))
        
        if line.startswith('creg'):
            continue
        
        if 'q[' in line and not line.startswith('qreg') and not line.startswith('creg'):
            gate_line = line.rstrip(';').strip()
            # parse the gate and its qubits as (gate, q1, q2, ...)
            parts = gate_line.split(' ')
            gate = parts[0]
            rest = ' '.join(parts[1:]).split(',')
            qubits = []
            for part in rest:
                part = part.strip()
                if 'q[' in part:
                    qubits.append(int(part.split('[')[1].split(']')[0]))
            parsed_file.append((gate, qubits))
            
    # initialize the basis states
    for i in range(2**n_qubits):
        vector = vectors[i]
        vector[i] = complex_representation.one(None)
    

    # constants declarations
    inv_sqrt2 = complex_representation.inv_sqrt2(None)
    minus1    = complex_representation.minus_one(None)
    i_phase   = complex_representation.i_phase(None)
    t_phase   = complex_representation.t_phase(None)
    one_half  = complex_representation.one_half(None)
    i_half    = complex_representation.i_half(None)

    
    for (op, qubits) in parsed_file:
        for i, vector in enumerate(vectors):
            # apply the gate to each of the vectors
            new_vec = vector.copy()
            if op == 'h':
                # hadamard
                visited = set()
                for a in range(len(vector)):
                    if a in visited: continue
                    b = a ^ (1 << qubits[0])
                    visited.update([a,b])
                    if complex_representation == Complex:
                        new_vec[a] = ((vector[a] + vector[b]) * inv_sqrt2)
                        new_vec[b] = ((vector[a] + (vector[b] * minus1)) * inv_sqrt2)
                    elif complex_representation == Cyclotomic8Dyadic:
                        new_vec[a] = (vector[a] + vector[b]).divide_by_sqrt2(None)
                        new_vec[b] = (vector[a] + (vector[b].multiply_by_minus_one(None))).divide_by_sqrt2(None)
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = int(vector.k) + 1
                
            elif op == 'id':
                # identity
                pass                
            
            elif op == 's':
                for a in range(len(vector)):
                    bit = (a >> qubits[0]) & 1
                    if bit == 0:
                        new_vec[a] = vector[a]
                    else:
                        if complex_representation == Complex:
                            new_vec[a] = vector[a] * i_phase
                        elif complex_representation == Cyclotomic8Dyadic:
                            new_vec[a] = vector[a].multiply_by_i(None)
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = vector.k
            
            elif op == 'sdg':
                for a in range(len(vector)):
                    bit = (a >> qubits[0]) & 1
                    if bit == 0:
                        new_vec[a] = vector[a]
                    else:
                        if complex_representation == Complex:
                            new_vec[a] = vector[a] * i_phase
                        elif complex_representation == Cyclotomic8Dyadic:
                            new_vec[a] = vector[a].multiply_by_minus_i(None)
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = vector.k

            elif op == 't':
                for a in range(len(vector)):
                    bit = (a >> qubits[0]) & 1
                    if bit == 0:
                        new_vec[a] = vector[a]
                    else:
                        if complex_representation == Complex:
                            new_vec[a] = vector[a] * t_phase
                        elif complex_representation == Cyclotomic8Dyadic:
                            new_vec[a] = vector[a].multiply_by_omega(None)
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = vector.k

            elif op == 'tdg':                
                for a in range(len(vector)):
                    bit = (a >> qubits[0]) & 1
                    if bit == 0:
                        new_vec[a] = vector[a]
                    else:
                        if complex_representation == Complex:
                            new_vec[a] = vector[a] * t_phase
                        elif complex_representation == Cyclotomic8Dyadic:
                            new_vec[a] = vector[a].multiply_by_omega_counter(None)
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = vector.k
                
            elif op == 'x':
                visited = set()
                for a in range(len(vector)):
                    if a in visited: continue
                    b = a ^ (1 << qubits[0])  # Flip bit q
                    visited.update([a, b])
                    new_vec[a] = vector[b]
                    new_vec[b] = vector[a]
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = vector.k
                    
            elif op == 'sx':
                visited = set()
                for a in range(len(vector)):
                    if a in visited: continue
                    b = a ^ (1 << qubits[0])
                    visited.update([a,b])
                    if complex_representation == Complex:
                        new_vec[a] = (((vector[a] + vector[b]) * one_half)  + (vector[a] - vector[b]) * i_half)
                        new_vec[b] = (((vector[a] + vector[b]) * one_half)  + (vector[b] - vector[a]) * i_half)
                    elif complex_representation == Cyclotomic8Dyadic:
                        new_vec[a] = (((vector[a] + vector[b]))  + (vector[a] - vector[b]).multiply_by_i(None))
                        new_vec[b] = (((vector[a] + vector[b]))  + (vector[b] - vector[a]).multiply_by_i(None))
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = int(vector.k) + 2
                    
            elif op == 'sxdg':
                visited = set()
                for a in range(len(vector)):
                    if a in visited: continue
                    b = a ^ (1 << qubits[0])
                    visited.update([a,b])
                    if complex_representation == Complex:
                        new_vec[a] = (((vector[a] + vector[b]) * one_half)  + (vector[b] - vector[a]) * i_half)
                        new_vec[b] = (((vector[a] + vector[b]) * one_half)  + (vector[a] - vector[b]) * i_half)
                    elif complex_representation == Cyclotomic8Dyadic:
                        new_vec[a] = (((vector[a] + vector[b]))  + (vector[b] - vector[a]).multiply_by_i(None))
                        new_vec[b] = (((vector[a] + vector[b]))  + (vector[a] - vector[b]).multiply_by_i(None))
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = int(vector.k) + 2
                    
            elif op == 'y':
                visited = set()
                for a in range(len(vector)):
                    if a in visited: continue
                    b = a ^ (1 << qubits[0])
                    visited.update([a, b])
                    bit = (a >> qubits[0]) & 1
                    if bit == 0:
                        if complex_representation == Complex:
                            new_vec[b] = (vector[a] * i_phase)
                            new_vec[a] = (vector[b] * i_phase.conjugate(None))
                        elif complex_representation == Cyclotomic8Dyadic:
                            new_vec[b] = vector[a].multiply_by_i(None)
                            new_vec[a] = vector[b].multiply_by_minus_i(None)
                    else:
                        if complex_representation == Complex:
                            new_vec[b] = (vector[a] * i_phase.conjugate(None))
                            new_vec[a] = (vector[b] * i_phase)
                        elif complex_representation == Cyclotomic8Dyadic:
                            new_vec[b] = vector[a].multiply_by_minus_i(None)
                            new_vec[a] = vector[b].multiply_by_i(None)
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = vector.k
                    
            elif op == 'z':
                for a in range(len(vector)):
                    bit = (a >> qubits[0]) & 1
                    if bit == 0:
                        new_vec[a] = vector[a]
                    else:
                        if complex_representation == Complex:
                            new_vec[a] = vector[a] * minus1
                        elif complex_representation == Cyclotomic8Dyadic:
                            new_vec[a] = vector[a].multiply_by_minus_one(None)
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = vector.k
                    
            elif op == 'cx':
                for a in range(len(vector)):
                    control_on = ((a >> qubits[0]) & 1) == 1
                    if not control_on:
                        new_vec[a] = vector[a]
                    else:
                        b = a ^ (1 << qubits[1])
                        new_vec[a] = vector[b]
                        new_vec[b] = vector[a]
                if complex_representation == Cyclotomic8Dyadic:
                    new_vec.k = vector.k
                
            vectors[i] = new_vec


    results = []
    for i, vector in enumerate(vectors):
        # get also the basis state and return the pair, not the result only
        vec = Vector(q=2**n_qubits, generator=None, element_representation=complex_representation, k=0)
        vec[i] = complex_representation.one(None)
        results.append((vec, vector))
            
    return results