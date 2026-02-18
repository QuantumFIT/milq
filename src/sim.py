import re
from complex_numbers_smtlib import Complex, Vector, nTuple
from complex_numbers_smtlib import Cyclotomic8Dyadic as FiveTuple
from gates import GateSet


class Simulator:
    def __init__(self, qasm_file, complex_representation=FiveTuple):
        self.qasm_file = qasm_file
        self.complex_representation = complex_representation
        self.stats = {}
        self.stats['gate_set'] = GateSet()
        self.stats['d'] = 0
        self.stats['q'] = 0
        self.stats['qreg'] = ''

    def parse_file(self):
        with open(self.qasm_file, 'r') as f:
            qasm_content = f.read()
        
        lines = qasm_content.split('\n')
        vectors = []
        gates = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('OPENQASM') or line.startswith('include'):
                continue
            if line.startswith('qreg'):
                parts = line.split('[')
                if len(parts) > 1:
                    self.stats['q'] = int(parts[1].split(']')[0])
                    self.stats['qreg'] = parts[0].split(' ')[1].strip()
                    for i in range(2**self.stats['q']):
                        vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
                        vec[i] = self.complex_representation.one(None)
                        vectors.append(vec)
                continue
            
            if line.startswith('creg'):
                continue
            qreg_name = self.stats['qreg']
            qreg_pattern = re.compile(rf'{re.escape(f"{qreg_name}")}\s*\[')
            if qreg_pattern.search(line):
                gate_line = line.rstrip(';').strip()
                # parse the gate and its qubits as (gate, q1, q2, ...)
                parts = gate_line.split(' ')
                gate = parts[0].lower()
                if gate not in self.stats['gate_set']:
                    self.stats['gate_set'].append(gate)
                rest = ' '.join(parts[1:]).split(',')
                qubits = []
                for part in rest:
                    part = part.strip()
                    if qreg_pattern.search(part):
                        qubits.append(int(part.split('[')[1].split(']')[0]))
                gates.append((gate, qubits))
                self.stats['d'] += 1
                continue

            raise Exception(f"Failed to parse input file")
        return gates, vectors
            

    def simulate(self, vectors, parsed_file):        
        input_vectors = []
        for i, vector in enumerate(vectors):
            input_vectors.append(vector.copy())

        # constants declarations
        if self.complex_representation == Complex:
            inv_sqrt2 = self.complex_representation.inv_sqrt2(None)
            minus1    = self.complex_representation.minus_one(None)
            i_phase   = self.complex_representation.i_phase(None)
            t_phase   = self.complex_representation.t_phase(None)
            one_half  = self.complex_representation.one_half(None)
            i_half    = self.complex_representation.i_half(None)

        for (op, qubits) in parsed_file:
            for i, vector in enumerate(vectors):
                # apply the gate to each of the vectors
                new_vec = vector.copy()
                if op == 'h':
                    visited = set()
                    for a in range(len(vector)):
                        if a in visited: continue
                        b = a ^ (1 << qubits[0])
                        visited.update([a, b])
                        if self.complex_representation == Complex:
                            new_vec[a] = ((vector[a] + vector[b]) * inv_sqrt2)
                            new_vec[b] = ((vector[a] + (vector[b] * minus1)) * inv_sqrt2)
                        elif self.complex_representation == FiveTuple:
                            new_vec[a] = (vector[a] + vector[b]).divide_by_sqrt2(None)
                            new_vec[b] = (vector[a] + (vector[b].multiply_by_minus_one(None))).divide_by_sqrt2(None)
                    if self.complex_representation == FiveTuple:
                        new_vec.k = int(vector.k) + 1
                    
                elif op == 'id':
                    for a in range(len(vector)):
                        new_vec[a] = vector[a]
                    if self.complex_representation == FiveTuple:
                        new_vec.k = vector.k
                
                elif op == 's':
                    for a in range(len(vector)):
                        bit = (a >> qubits[0]) & 1
                        if bit == 0:
                            new_vec[a] = vector[a]
                        else:
                            if self.complex_representation == Complex:
                                new_vec[a] = vector[a] * i_phase
                            elif self.complex_representation == FiveTuple:
                                new_vec[a] = vector[a].multiply_by_i(None)
                    if self.complex_representation == FiveTuple:
                        new_vec.k = vector.k
                
                elif op == 'sdg':
                    for a in range(len(vector)):
                        bit = (a >> qubits[0]) & 1
                        if bit == 0:
                            new_vec[a] = vector[a]
                        else:
                            if self.complex_representation == Complex:
                                new_vec[a] = vector[a] * i_phase
                            elif self.complex_representation == FiveTuple:
                                new_vec[a] = vector[a].multiply_by_minus_i(None)
                    if self.complex_representation == FiveTuple:
                        new_vec.k = vector.k

                elif op == 't':
                    for a in range(len(vector)):
                        bit = (a >> qubits[0]) & 1
                        if bit == 0:
                            new_vec[a] = vector[a]
                        else:
                            if self.complex_representation == Complex:
                                new_vec[a] = vector[a] * t_phase
                            elif self.complex_representation == FiveTuple:
                                new_vec[a] = vector[a].multiply_by_omega(None)
                    if self.complex_representation == FiveTuple:
                        new_vec.k = vector.k

                elif op == 'tdg':                
                    for a in range(len(vector)):
                        bit = (a >> qubits[0]) & 1
                        if bit == 0:
                            new_vec[a] = vector[a]
                        else:
                            if self.complex_representation == Complex:
                                new_vec[a] = vector[a] * t_phase
                            elif self.complex_representation == FiveTuple:
                                new_vec[a] = vector[a].multiply_by_omega_counter(None)
                    if self.complex_representation == FiveTuple:
                        new_vec.k = vector.k
                    
                elif op == 'x':
                    visited = set()
                    for a in range(len(vector)):
                        if a in visited: continue
                        b = a ^ (1 << qubits[0])
                        visited.update([a, b])
                        new_vec[a] = vector[b]
                        new_vec[b] = vector[a]
                    if self.complex_representation == FiveTuple:
                        new_vec.k = vector.k
                        
                elif op == 'sx':
                    visited = set()
                    for a in range(len(vector)):
                        if a in visited: continue
                        b = a ^ (1 << qubits[0])
                        visited.update([a,b])
                        if self.complex_representation == Complex:
                            new_vec[a] = (((vector[a] + vector[b]) * one_half)  + (vector[a] - vector[b]) * i_half)
                            new_vec[b] = (((vector[a] + vector[b]) * one_half)  + (vector[b] - vector[a]) * i_half)
                        elif self.complex_representation == FiveTuple:
                            new_vec[a] = (((vector[a] + vector[b]))  + (vector[a] - vector[b]).multiply_by_i(None))
                            new_vec[b] = (((vector[a] + vector[b]))  + (vector[b] - vector[a]).multiply_by_i(None))
                    if self.complex_representation == FiveTuple:
                        new_vec.k = int(vector.k) + 2
                        
                elif op == 'sxdg':
                    visited = set()
                    for a in range(len(vector)):
                        if a in visited: continue
                        b = a ^ (1 << qubits[0])
                        visited.update([a,b])
                        if self.complex_representation == Complex:
                            new_vec[a] = (((vector[a] + vector[b]) * one_half)  + (vector[b] - vector[a]) * i_half)
                            new_vec[b] = (((vector[a] + vector[b]) * one_half)  + (vector[a] - vector[b]) * i_half)
                        elif self.complex_representation == FiveTuple:
                            new_vec[a] = (((vector[a] + vector[b]))  + (vector[b] - vector[a]).multiply_by_i(None))
                            new_vec[b] = (((vector[a] + vector[b]))  + (vector[a] - vector[b]).multiply_by_i(None))
                    if self.complex_representation == FiveTuple:
                        new_vec.k = int(vector.k) + 2
                        
                elif op == 'y':
                    visited = set()
                    for a in range(len(vector)):
                        if a in visited: continue
                        b = a ^ (1 << qubits[0])
                        visited.update([a, b])
                        bit = (a >> qubits[0]) & 1
                        if bit == 0:
                            if self.complex_representation == Complex:
                                new_vec[b] = (vector[a] * i_phase)
                                new_vec[a] = (vector[b] * i_phase.conjugate(None))
                            elif self.complex_representation == FiveTuple:
                                new_vec[b] = vector[a].multiply_by_i(None)
                                new_vec[a] = vector[b].multiply_by_minus_i(None)
                        else:
                            if self.complex_representation == Complex:
                                new_vec[b] = (vector[a] * i_phase.conjugate(None))
                                new_vec[a] = (vector[b] * i_phase)
                            elif self.complex_representation == FiveTuple:
                                new_vec[b] = vector[a].multiply_by_minus_i(None)
                                new_vec[a] = vector[b].multiply_by_i(None)
                    if self.complex_representation == FiveTuple:
                        new_vec.k = vector.k
                        
                elif op == 'z':
                    for a in range(len(vector)):
                        bit = (a >> qubits[0]) & 1
                        if bit == 0:
                            new_vec[a] = vector[a]
                        else:
                            if self.complex_representation == Complex:
                                new_vec[a] = vector[a] * minus1
                            elif self.complex_representation == FiveTuple:
                                new_vec[a] = vector[a].multiply_by_minus_one(None)
                    if self.complex_representation == FiveTuple:
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
                    if self.complex_representation == FiveTuple:
                        new_vec.k = vector.k
                        
                elif op == 'cz':
                    for a in range(len(vector)):
                        control_on = ((a >> qubits[0]) & 1) == 1
                        target_on  = ((a >> qubits[1]) & 1) == 1

                        if control_on and target_on:
                            if self.complex_representation == Complex:
                                new_vec[a] = (vector[a] * minus1)
                            elif self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                                new_vec[a] = (vector[a].multiply_by_minus_one(None))
                        else:
                            new_vec[a] = vector[a]

                    if self.complex_representation == FiveTuple or self.complex_representation == nTuple:
                        new_vec.k = vector.k
                    
                vectors[i] = new_vec


        results = []
        for i, vector in enumerate(vectors):
            results.append((input_vectors[i], vector))
                
        return results

    def simulate_circuit(self):
        gates, vectors = self.parse_file()
        return self.simulate(vectors, gates)

    def simulate_rus(self):
        gates, vectors = self.parse_file()
        
        if self.stats['q'] != 2:
            raise NotImplementedError("RUS protocol only supported with 2 qubits")
                
        # initialize the basis_states |0>, |1>, |+>
        vectors = []
        for i in range(2):
            vector = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
            vector[i] = self.complex_representation.one(None)
            vectors.append(vector)
            
        # |+>
        vector = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=1)
        vector[0] = self.complex_representation.one(None)
        vector[1] = self.complex_representation.one(None)
        vectors.append(vector)

        return self.simulate(vectors, gates)

    def circuit_stats(self) -> dict:
            return self.stats

    def print_stats(self):
        print(f"Qubits: {self.stats['q']}")
        print(f"Qreg: {self.stats['qreg']}")
        print(f"Gate set: {self.stats['gate_set']}")
        print(f"Number of gates: {self.stats['d']}")