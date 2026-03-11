"""
@file: sim.py
@author: Jakub Havlík
@date: 24.02.2026
@brief: simulation of quantum circuits in representation used in synthesis
"""

import re
from complex.vector import Vector
from complex.fivetuple import FiveTuple
from complex.ntuple import nTuple
from complex.classic import Complex
from gates import GateSet


class Simulator:
    """
    simulate quantum circuit using the representation for synthesis - complex, fivetuples, ntuples
    can simulate either normal circuits (all cbs) or RUS circuits (0, 1, + states)
    """
    def __init__(self, qasm_file: str, complex_representation: type[Vector] = FiveTuple):
        self.qasm_file = qasm_file
        self.complex_representation = complex_representation
        self.stats = {}
        self.stats['gate_set'] = GateSet()
        self.stats['d'] = 0
        self.stats['q'] = 0
        self.stats['qreg'] = ''
        self.stats['max_k'] = 0
        self.stats['input_circuit'] = []

    """
    parse the input qasm file into a sequence of gates with a respective list of qubits
    also collects information about the input circuits -- qubits, gate set ...
    """
    def parse_file(self) -> tuple[list[tuple[str, list[int]]], list[Vector]]:
        with open(self.qasm_file, 'r') as f:
            qasm_content = f.read()
        
        lines = qasm_content.split('\n')
        vectors = []
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
                        vectors.append(vec)
                continue
            
            if line.startswith('creg') or line.startswith('bit'):
                continue
            
            if line.startswith('barrier') or line.startswith('measure') or line.startswith('meas'):
                continue
            
            qreg_name = self.stats['qreg']
            # find gates using the register name
            qreg_pattern = re.compile(rf'{re.escape(f"{qreg_name}")}\s*\[')
            if qreg_pattern.search(line):
                gate_line = line.rstrip(';').strip()
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
                self.stats['d'] += 1
                if gate not in self.stats['gate_set']:
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
                        elif op == 'ccx':
                            control1_flag = (pos >> qubits[0]) & 1
                            control2_flag = (pos >> qubits[1]) & 1
                            if control1_flag and control2_flag:
                                other = pos ^ (1 << qubits[2])
                                modified_positions.append(other)
                                new_vec[pos] = vector[other]
                                new_vec[other] = vector[pos]
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
    simulate the input circuit on state |0>
    """
    def simulate_zero(self) -> list[tuple[Vector, Vector]]:
        gates, vectors = self.parse_file()
        vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
        vec[0] = self.complex_representation.one(None)
        vectors = [vec]
        return self.simulate(vectors, gates)

    """
    simulate the unitary part of RUS circuit (without the measurement) on states |0>, |1>, |+>
    """
    def simulate_rus(self, targets: int = 1, ancillas: int = 1) -> list[tuple[Vector, Vector]]:
        gates, vectors = self.parse_file()
        
        if self.stats['q'] != targets + ancillas:
            raise ValueError(f"Mismatch between circuit qubits and targets + ancillas")
                
        # initialize the basis_states |0>, |1>, |+>
        vectors = []
        
        # |0>^targets state and |1>^targets state
        for i in range(2**targets):
            vector = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
            vector[i] = self.complex_representation.one(None)
            vectors.append(vector)
            
        # |+>^targets
        vector = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=targets)
        for i in range(2**targets):
            vector[i] = self.complex_representation.inv_sqrt2(None)
        vectors.append(vector)
        return self.simulate(vectors, gates)

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