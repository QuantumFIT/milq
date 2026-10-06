"""
@file: sim.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: simulation of quantum circuits in desired representation used in synthesis
"""

import re
from complex.vector import Vector
from complex.fivetuple import FiveTuple
from complex.ntuple import nTuple
from complex.classic import Complex
from complex.matrix import Matrix
from gates import GateSet
import numpy as np


class Simulator:
    """
    simulate quantum circuit using the representation for synthesis - complex, fivetuples, ntuples
    can simulate either normal circuits (all cbs) or RUS circuits (0, 1, + states)
    """
    def __init__(self, qasm_file: str = None, matrix: np.array = None, complex_representation: type[Vector] = FiveTuple, meas: int = 0, basis="cb", no_measurement=False):
        if matrix is not None and qasm_file is not None:
            raise ValueError("matrix and qasm_file cannot be provided at the same time")
        if matrix is None and qasm_file is None:
            raise ValueError("matrix or qasm_file has to be provided")
        if matrix is not None and complex_representation != Complex:
            raise ValueError("matrix can be provided only for Classic complex representation")
        self.qasm_file = qasm_file
        self.complex_representation = complex_representation
        self.matrix = matrix
        self.stats = {}
        self.stats['gate_set'] = GateSet()
        self.stats['d'] = 0
        self.stats['q'] = 0
        self.stats['qreg'] = ''
        self.stats['max_k'] = 0
        self.stats['input_circuit'] = []
        self.stats['measured_qubits'] = []
        self.measurement_outcome = meas
        self.basis = basis
        self.no_measurement = no_measurement
        
    """
    parse the input qasm file into a sequence of gates with a respective list of qubits
    also collects information about the input circuits -- qubits, gate set ...
    """
    def parse_file(self) -> tuple[list[tuple[str, list[int]]], list[Vector]]:
        vectors = []
        if self.qasm_file is None:
            # matrix 2**q x 2**q
            self.stats['q'] = self.matrix.qubits
            for i in range(2**self.stats['q']):
                vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
                vec[i] = self.complex_representation.one(None)
                if self.basis == "pauli":
                    vec = Matrix.density_from_vector(vec)
                vectors.append(vec)
                
            return [], vectors

        with open(self.qasm_file, 'r') as f:
            qasm_content = f.read()
        # drop comments, definitions of non-standard gates (they are simulated natively);
        # a definition can span lines and be followed by more statements on the line of its '}'
        qasm_content = re.sub(r'//[^\n]*', '', qasm_content)
        qasm_content = re.sub(r'\bgate\s[^{]*\{[^}]*\}', '', qasm_content)

        lines = qasm_content.split('\n')
        gates = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('OPENQASM') or line.startswith('include'):
                continue
            # find quantum register to initialize vectors
            if line.startswith('qreg'):
                # qreg name[n]
                parts = line.split('[')
                if len(parts) > 1:
                    self.stats['q'] = int(parts[1].split(']')[0])
                    self.stats['qreg'] = parts[0].split(' ')[1].strip()
                    for i in range(2**self.stats['q']):
                        vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
                        vec[i] = self.complex_representation.one(None)
                        vectors.append(vec)
                continue
            if line.startswith('qubit'):
                # qubit[n] name
                parts = line.split('[')
                if len(parts) > 1:
                    self.stats['q'] = int(parts[1].split(']')[0])
                    self.stats['qreg'] = parts[1].split(']')[1].strip().split(';')[0].strip()
                    for i in range(2**self.stats['q']):
                        vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
                        vec[i] = self.complex_representation.one(None)
                        if self.basis == "pauli":
                            vec = Matrix.density_from_vector(vec)
                        vectors.append(vec)
                continue
            
            if line.startswith('creg') or line.startswith('bit'):
                continue

            # every complete definition was removed above, so this one has no closing brace
            if line.startswith('gate '):
                raise Exception("gate definition not closed, not a valid qasm file")

            qreg_name = self.stats['qreg']
            # find gates using the register name
            qreg_pattern = re.compile(rf'{re.escape(f"{qreg_name}")}\s*\[')
            if qreg_pattern.search(line):
                gate_line = line.rstrip(';').strip()
                # OpenQASM 3 measurement (c[i] = measure q[i]) -> measure q[i]
                assignment = re.match(r'^\S+\s*=\s*(measure\s+.*)$', gate_line)
                if assignment:
                    gate_line = assignment.group(1)
                # parse the gate and its qubits as (gate, q1, q2, ...)
                parts = gate_line.split(' ')
                gate = parts[0].lower()
                rest = ' '.join(parts[1:]).split(',')
                qubits = []
                # parse qubits
                for part in rest:
                    part = part.strip()
                    if qreg_pattern.search(part):
                        qubits.append(int(part.split('[')[1].split(']')[0]))
                gates.append((gate, qubits))
                self.stats['input_circuit'].append((gate, qubits))
                self.stats['d'] += 1 if gate != 'measure' and gate != 'meas' else 0
                if gate not in self.stats['gate_set'] and (gate != 'measure' and gate != 'meas'):
                    self.stats['gate_set'].append(gate, qubits=len(qubits))
                continue

            raise Exception(f"input file parsing failed")
        return gates, vectors
            
    """
    simulate the parsed circuit by modifying all input vectors by applying the gates
    """
    def simulate(self, vectors: list[Vector], parsed_file: list[tuple[str, list[int]]]) -> list[tuple[Vector, Vector]]:        
        input_vectors = []
        for i, vector in enumerate(vectors):
            input_vectors.append(vector.copy())
        
        if self.matrix is not None:
            results = []
            for i, vector in enumerate(vectors):
                vectors[i] = self.matrix * vector
                results.append((input_vectors[i], vectors[i]))
            return results
            

        for (op, qubits) in parsed_file:
            for i, vector in enumerate(vectors):
                # apply the gate to each of the vectors
                new_vec = vector.copy()
                modified_positions = []
                for pos in range(2**int(self.stats['q'])):
                    if pos in modified_positions:
                        continue
                    else:
                        modified_positions.append(pos)
                        if op == 'id':
                            break
                        elif op == 'h':
                            other = pos ^ (1 << qubits[0])
                            modified_positions.append(other)
                            new_vec[pos] = (vector[pos] + vector[other]).divide_by_sqrt2(None)
                            new_vec[other] = (vector[pos] + (vector[other].multiply_by_minus_one(None))).divide_by_sqrt2(None)
                        elif op == 's' or op == 'sdg':
                            one_flag = (pos >> qubits[0]) & 1
                            if one_flag:
                                new_vec[pos] = vector[pos].multiply_by_i(None) if op == 's' else vector[pos].multiply_by_minus_i(None)
                        elif op == 't' or op == 'tdg':
                            one_flag = (pos >> qubits[0]) & 1
                            if one_flag:
                                new_vec[pos] = vector[pos].multiply_by_omega(None) if op == 't' else vector[pos].multiply_by_omega_counter(None)
                        elif op == 'x':
                            other = pos ^ (1 << qubits[0])
                            modified_positions.append(other)
                            new_vec[pos] = vector[other]
                            new_vec[other] = vector[pos]
                        elif op == 'sx':
                            other = pos ^ (1 << qubits[0])
                            modified_positions.append(other)
                            new_vec[pos] = ((vector[pos] + vector[other]).divide_by_two(None)  + (vector[pos] - vector[other]).divide_by_two_i(None))
                            new_vec[other] = ((vector[pos] + vector[other]).divide_by_two(None)  + (vector[other] - vector[pos]).divide_by_two_i(None))
                        elif op == 'sxdg':
                            other = pos ^ (1 << qubits[0])
                            modified_positions.append(other)
                            new_vec[pos] = ((vector[pos] + vector[other]).divide_by_two(None)  + (vector[other] - vector[pos]).divide_by_two_i(None))
                            new_vec[other] = ((vector[pos] + vector[other]).divide_by_two(None)  + (vector[pos] - vector[other]).divide_by_two_i(None))
                        elif op == 'y':
                            other = pos ^ (1 << qubits[0])
                            modified_positions.append(other)
                            one_flag = (pos >> qubits[0]) & 1
                            new_vec[pos] = vector[other].multiply_by_i(None) if one_flag else vector[other].multiply_by_minus_i(None)
                            new_vec[other] = vector[pos].multiply_by_minus_i(None) if one_flag else vector[pos].multiply_by_i(None)
                        elif op == 'z':
                            one_flag = (pos >> qubits[0]) & 1
                            if one_flag:
                                new_vec[pos] = vector[pos].multiply_by_minus_one(None)
                        #
                        # 2 qubit gates
                        #
                        elif op == 'cx':
                            control_flag = (pos >> qubits[0]) & 1
                            if control_flag:
                                other = pos ^ (1 << qubits[1])
                                modified_positions.append(other)
                                new_vec[pos] = vector[other]
                                new_vec[other] = vector[pos]
                        elif op == 'cz':
                            control_flag = (pos >> qubits[0]) & 1
                            target_flag = (pos >> qubits[1]) & 1
                            if control_flag and target_flag:
                                new_vec[pos] = vector[pos].multiply_by_minus_one(None)
                        elif op == 'xcx':
                            control_flag = (pos >> qubits[0]) & 1
                            if not control_flag:
                                other = pos ^ (1 << qubits[1])
                                modified_positions.append(other)
                                new_vec[pos] = vector[other]
                                new_vec[other] = vector[pos]
                        elif op == 'dcx':
                            control_flag = (pos >> qubits[0]) & 1
                            target_flag = (pos >> qubits[1]) & 1
                            other = None
                            if not control_flag and target_flag:
                                other = pos ^ ((1 << qubits[0]) | (1 << qubits[1]))
                            elif control_flag and not target_flag:
                                other = pos ^ (1 << qubits[1])
                            else:
                                other = pos ^ (1 << qubits[0])
                            
                            if other is not None:
                                modified_positions.append(other)
                                new_vec[other] = vector[pos]
                        elif op == 'ch':
                            control_flag = (pos >> qubits[0]) & 1
                            if control_flag:
                                other = pos ^ (1 << qubits[1])
                                modified_positions.append(other)
                                new_vec[pos] = (vector[pos] + vector[other]).divide_by_sqrt2(None)
                                new_vec[other] = (vector[pos] + (vector[other].multiply_by_minus_one(None))).divide_by_sqrt2(None)
                            elif self.complex_representation == FiveTuple:
                                # k increases by 1 for the whole vector, compensate the untouched amplitudes
                                new_vec[pos] = vector[pos].increase_k(None)
                        elif op == 'ccx':
                            control1_flag = (pos >> qubits[0]) & 1
                            control2_flag = (pos >> qubits[1]) & 1
                            if control1_flag and control2_flag:
                                other = pos ^ (1 << qubits[2])
                                modified_positions.append(other)
                                new_vec[pos] = vector[other]
                                new_vec[other] = vector[pos]
                                
                        elif op == 'measure' or op == 'meas':
                            if self.no_measurement:
                                new_vec = vector.copy()
                                continue
                            new_vec = vector.measure(qubits, self.measurement_outcome)
                            self.stats['measured_qubits'].extend(qubits)
                            break
                        else:
                            raise NotImplementedError(f"Gate {op} is not yet implemented")


                if self.complex_representation == FiveTuple:
                    if op in ['h', 'ch']:
                        new_vec.k += 1
                    elif op in ['sx', 'sxdg']:
                        new_vec.k += 2
                vectors[i] = new_vec


        results = []
        for i, vector in enumerate(vectors):
            results.append((input_vectors[i], vector))
        
        return results

    """
    parse the circuit, simulate it, return pairs of input, output vectors
    """
    def simulate_circuit(self) -> list[tuple[Vector, Vector]]:
        gates, vectors = self.parse_file()
        res =  self.simulate(vectors, gates)
        for (_, vec) in res:
            if vec.k > self.stats['max_k']:
                self.stats['max_k'] = vec.k
        return res


    """
    simulate the input circuit on state |0>^n
    """
    def simulate_zero(self) -> list[tuple[Vector, Vector]]:
        gates, vectors = self.parse_file()
        vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
        vec[0] = self.complex_representation.one(None)
        if self.basis == "pauli":
            vec = Matrix.density_from_vector(vec)
        vectors = [vec]
        return self.simulate(vectors, gates)
    
    """
    simulate input circuit with a set of custom input vectors
    """
    def simulate_custom(self, vectors: list[Vector]) -> list[tuple[Vector, Vector]]:
        gates, _ = self.parse_file()
        return self.simulate(vectors, gates)

    """
    simulate the unitary part of RUS circuit (without the measurement) on states |0>, |1>, |+> for the target qubit
    """
    def simulate_rus(self, targets: int = 1, ancillas: int = 1) -> list[tuple[Vector, Vector]]:
        gates, vectors = self.parse_file()
        
        if self.stats['q'] != targets + ancillas:
            if self.matrix is not None:
                # expand the matrix (only target matrix can be set, and ancillas are to be expanded)
                # I \otimes I \otimes ... \otimes Target
                new_matrix = Matrix.i()
                for _ in range(1, ancillas):
                    new_matrix = new_matrix.tensor(Matrix.i())
                self.matrix = new_matrix.tensor(self.matrix)
                
            # else : just add new ancillae to the circuit, expand the vectors
            self.stats['q'] = targets + ancillas
                
        # initialize the basis_states |0>, |1>, |+>
        vectors = []
        
        # every computational basis state of the targets (|0...0> to |1...1>), ancillas in |0>
        for i in range(2**targets):
            vector = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
            vector[i] = self.complex_representation.one(None)
            if self.basis == "pauli":
                vector = Matrix.density_from_vector(vector)
            vectors.append(vector)
            
        # |+>^targets, ancillas in |0>
        vector = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=targets)
        for i in range(2**targets):
            amplitude = self.complex_representation.one(None)
            for _ in range(targets):
                amplitude = amplitude.divide_by_sqrt2(None)
            vector[i] = amplitude
        if self.basis == "pauli":
            vector = Matrix.density_from_vector(vector)
        vectors.append(vector)
        return self.simulate(vectors, gates)
    
    def simulate_jamiolkowski(self) -> list[tuple[Vector, Vector]]:
        # expand the circuit to 2n qubits and using jamiolkowski isomporhism,
        # prepare maximally entangled state and simulate the circuit on it
        gates, vectors = self.parse_file()
        # add new gates creating the maximally entangled state
        pre_gates = []
        for i in range(self.stats['q']):
            pre_gates.append(('h', [i]))
        
        for i in range(self.stats['q']):
            j = i + self.stats['q']
            pre_gates.append(('cx', [i, j]))
        
        self.stats['q'] = 2 * self.stats['q']
        self.stats['gate_set'].add_gate('h', qubits=1, weight=1)
        self.stats['gate_set'].add_gate('cx', qubits=2, weight=1)
        
        # create new input state
        vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
        vec[0] = self.complex_representation.one(None)
        if self.basis == "pauli":
            vec = Matrix.density_from_vector(vec)
        vectors = [vec]
        res = self.simulate(vectors, pre_gates)
        input_state = res[0][1] # get output of the simulation
        vectors = [input_state]
        
        return self.simulate(vectors, gates)
    
    """
    simulate the given input circuit by creating the unitary matrix instead of vectors
    """
    def simulate_matrix(self) -> Matrix:
        gates, _ = self.parse_file()
        matrix = Matrix.i(element_representation=self.complex_representation, q=0, qubits=self.stats['q'])
        for (op, qubits) in gates:
            if len(qubits) == 1:
                mat = getattr(Matrix, op)(element_representation=self.complex_representation, q=qubits[0], qubits=self.stats['q'])
                matrix = mat * matrix
            elif len(qubits) == 2:
                mat = getattr(Matrix, op)(element_representation=self.complex_representation, q1=qubits[0], q2=qubits[1], qubits=self.stats['q'])
                matrix = mat * matrix
            elif len(qubits) == 3:
                mat = getattr(Matrix, op)(element_representation=self.complex_representation, q1=qubits[0], q2=qubits[1], q3=qubits[2], qubits=self.stats['q'])
                matrix = mat * matrix
            else:
                raise NotImplementedError(f"Gate {op} with {len(qubits)} qubits is not yet implemented")
        return matrix
        
    """
    return the statistics about the input circuit
    """
    def circuit_stats(self) -> dict[str, any]:
            return self.stats

    """
    print the statistics about the input circuit
    """
    def print_stats(self) -> None:
        print(f"Qubits: {self.stats['q']}")
        print(f"Qreg: {self.stats['qreg']}")
        print(f"Gate set: {self.stats['gate_set']}")
        print(f"Number of gates: {self.stats['d']}")