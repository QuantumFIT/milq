"""
@file: sim.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: simulation of quantum circuits in desired representation used in synthesis
"""

import re
from complex.vector import Vector
from complex.fivetuple import FiveTuple
from complex.classic import Complex
from complex.matrix import Matrix
from gates import GateSet
import numpy as np


def classical_declaration(line: str) -> str:
    # OpenQASM 2 `creg c[n]` is `bit[n] c` in OpenQASM 3, the output format
    creg = re.fullmatch(r'creg (\w+) ?\[ ?(\d+) ?\]', line)
    return f"bit[{creg.group(2)}] {creg.group(1)}" if creg else line


class Simulator:
    """
    simulate quantum circuit using the representation for synthesis - complex, fivetuples
    can simulate either normal circuits (all cbs) or RUS circuits (0, 1, + states)
    """
    def __init__(self, qasm_file: str = None, matrix: np.array = None, complex_representation: type[Vector] = FiveTuple, meas: int = 0, basis="cb", no_measurement=False):
        if matrix is not None and qasm_file is not None:
            raise ValueError("matrix and qasm_file cannot be provided at the same time")
        if matrix is None and qasm_file is None:
            raise ValueError("matrix or qasm_file has to be provided")
        if matrix is not None and complex_representation != Complex:
            raise ValueError("matrix can be provided only for Classic complex representation")
        if basis != "cb":
            raise ValueError("basis can be only cb (the computational basis)")
        if meas not in (0, 1):
            raise ValueError("the measurement outcome (meas) can be only 0 or 1")
        self.qasm_file = qasm_file
        self.complex_representation = complex_representation
        self.matrix = matrix
        self.measurement_outcome = meas
        self.basis = basis
        self.no_measurement = no_measurement
        self.reset_stats()

    def reset_stats(self) -> None:
        # every simulate_* parses the file again, and parsing starts from here, so the stats describe one simulation
        self.stats = {}
        self.stats['gate_set'] = GateSet()
        self.stats['d'] = 0
        self.stats['q'] = 0
        self.stats['qreg'] = ''
        self.stats['max_k'] = 0
        self.stats['input_circuit'] = []
        # each measured qubit once, in the order of its first measurement (empty with no_measurement)
        self.stats['measured_qubits'] = []
        # end-of-circuit measurements as (qubit, classical bit or None) and the classical declarations, both in the
        # input's order and OpenQASM 3 syntax, to write them to the synthesized circuit as they are in the input
        self.stats['measurements'] = []
        self.stats['classical_declarations'] = []
        
    """
    parse the input qasm file into a sequence of gates with a respective list of qubits
    also collects information about the input circuits -- qubits, gate set ...
    """
    def parse_file(self) -> tuple[list[tuple[str, list[int]]], list[Vector]]:
        self.reset_stats()
        vectors = []
        if self.qasm_file is None:
            # matrix 2**q x 2**q
            self.stats['q'] = self.matrix.qubits
            for i in range(2**self.stats['q']):
                vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
                vec[i] = self.complex_representation.one(None)
                vectors.append(vec)
                
            return [], vectors

        with open(self.qasm_file, 'r') as f:
            qasm_content = f.read()
        # drop comments, definitions of non-standard gates (they are simulated natively);
        # a definition can span lines and be followed by more statements on the line of its '}'
        qasm_content = re.sub(r'//[^\n]*|/\*.*?\*/', '', qasm_content, flags=re.S)
        qasm_content = re.sub(r'\bgate\s[^{]*\{[^}]*\}', '', qasm_content)

        gates = []
        # one statement per ';', whitespace (tabs, newlines) collapsed to single spaces
        for line in qasm_content.split(';'):
            line = ' '.join(line.split())
            if not line or line.startswith('OPENQASM') or line.startswith('include'):
                continue
            # find quantum register to initialize vectors
            if re.match(r'qreg\b', line):
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
            if re.match(r'qubit\b', line):
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
            
            # classical declarations; `bit c = measure q[0]` is a measurement and is parsed below
            if re.match(r'(creg|bit)\b', line) and 'measure' not in line:
                self.stats['classical_declarations'].append(classical_declaration(line))
                continue

            # every complete definition was removed above, so this one has no closing brace
            if line.startswith('gate '):
                raise Exception("gate definition not closed, not a valid qasm file")

            qreg_name = self.stats['qreg']
            # whole-register measurement (measure q -> c, c = measure q) -> measure every qubit
            if re.fullmatch(rf'(?:[^=]*=\s*)?measure {re.escape(qreg_name)}(?: ?->.*)?', line):
                register = self.measurement_target(line)
                for i in range(self.stats['q']):
                    gates.append(('measure', [i]))
                    self.stats['input_circuit'].append(('measure', [i]))
                    self.stats['measurements'].append((i, None if register is None else f"{register}[{i}]"))
                    self.add_measured_qubits([i])
                continue
            # find gates using the register name
            qreg_pattern = re.compile(rf'{re.escape(f"{qreg_name}")}\s*\[')
            if qreg_pattern.search(line):
                gate_line = line.rstrip(';').strip()
                # OpenQASM 3 measurement (c[i] = measure q[i], bit c = measure q[i]) -> measure q[i]
                assignment = re.match(r'^[^=]*=\s*(measure\s+.*)$', gate_line)
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
                if gate == 'measure':
                    self.stats['measurements'].append((qubits[0], self.measurement_target(line)))
                if gate in ('measure', 'meas'):
                    self.add_measured_qubits(qubits)
                self.stats['d'] += 1 if gate != 'measure' and gate != 'meas' else 0
                if gate not in self.stats['gate_set'] and (gate != 'measure' and gate != 'meas'):
                    self.stats['gate_set'].add_gate(gate, qubits=len(qubits))
                continue

            raise Exception(f"input file parsing failed")
        return gates, vectors
            
    def add_measured_qubits(self, qubits: list[int]) -> None:
        # simulate() ignores measurements with no_measurement, so they measure no qubit
        if self.no_measurement:
            return
        for q in qubits:
            if q not in self.stats['measured_qubits']:
                self.stats['measured_qubits'].append(q)
            
    def measurement_target(self, line: str) -> str:
        # the classical bit (or register) of `c = measure q`, `bit c = measure q` or `measure q -> c`, None for a plain
        # `measure q`; a declaration in the statement is moved to the classical declarations
        if '=' in line:
            target = line.split('=')[0].strip()
            if re.match(r'bit\b', target):
                self.stats['classical_declarations'].append(target)
                target = target.split()[-1]
            return target
        if '->' in line:
            return line.split('->')[1].strip()
        return None

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
                            # dcx = cx(q1, q2) cx(q2, q1) permutes |a, b> -> |b, a xor b> (a 3-cycle)
                            control_flag = (pos >> qubits[0]) & 1
                            target_flag = (pos >> qubits[1]) & 1
                            image = (pos & ~((1 << qubits[0]) | (1 << qubits[1]))) | (target_flag << qubits[0]) | ((control_flag ^ target_flag) << qubits[1])
                            new_vec[image] = vector[pos]
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
                        elif op == 'cy':
                            control_flag = (pos >> qubits[0]) & 1
                            if control_flag:
                                other = pos ^ (1 << qubits[1])
                                modified_positions.append(other)
                                target_flag = (pos >> qubits[1]) & 1
                                new_vec[pos] = vector[other].multiply_by_i(None) if target_flag else vector[other].multiply_by_minus_i(None)
                                new_vec[other] = vector[pos].multiply_by_minus_i(None) if target_flag else vector[pos].multiply_by_i(None)
                        elif op == 'cs' or op == 'csdg':
                            control_flag = (pos >> qubits[0]) & 1
                            target_flag = (pos >> qubits[1]) & 1
                            if control_flag and target_flag:
                                new_vec[pos] = vector[pos].multiply_by_i(None) if op == 'cs' else vector[pos].multiply_by_minus_i(None)
                        elif op == 'csx':
                            control_flag = (pos >> qubits[0]) & 1
                            if control_flag:
                                other = pos ^ (1 << qubits[1])
                                modified_positions.append(other)
                                new_vec[pos] = ((vector[pos] + vector[other]).divide_by_two(None)  + (vector[pos] - vector[other]).divide_by_two_i(None))
                                new_vec[other] = ((vector[pos] + vector[other]).divide_by_two(None)  + (vector[other] - vector[pos]).divide_by_two_i(None))
                            elif self.complex_representation == FiveTuple:
                                # k increases by 2 for the whole vector, compensate the untouched amplitudes
                                new_vec[pos] = vector[pos].multiply_by_two(None)
                        elif op == 'swap' or op == 'iswap':
                            q1_flag = (pos >> qubits[0]) & 1
                            q2_flag = (pos >> qubits[1]) & 1
                            if q1_flag != q2_flag:
                                other = pos ^ ((1 << qubits[0]) | (1 << qubits[1]))
                                modified_positions.append(other)
                                new_vec[pos] = vector[other] if op == 'swap' else vector[other].multiply_by_i(None)
                                new_vec[other] = vector[pos] if op == 'swap' else vector[pos].multiply_by_i(None)
                        elif op == 'sqrtswap':
                            q1_flag = (pos >> qubits[0]) & 1
                            q2_flag = (pos >> qubits[1]) & 1
                            if q1_flag != q2_flag:
                                other = pos ^ ((1 << qubits[0]) | (1 << qubits[1]))
                                modified_positions.append(other)
                                new_vec[pos] = ((vector[pos] + vector[other]).divide_by_two(None)  + (vector[pos] - vector[other]).divide_by_two_i(None))
                                new_vec[other] = ((vector[pos] + vector[other]).divide_by_two(None)  + (vector[other] - vector[pos]).divide_by_two_i(None))
                            elif self.complex_representation == FiveTuple:
                                # k increases by 2 for the whole vector, compensate the untouched amplitudes
                                new_vec[pos] = vector[pos].multiply_by_two(None)
                        elif op == 'cswap':
                            control_flag = (pos >> qubits[0]) & 1
                            q2_flag = (pos >> qubits[1]) & 1
                            q3_flag = (pos >> qubits[2]) & 1
                            if control_flag and q2_flag != q3_flag:
                                other = pos ^ ((1 << qubits[1]) | (1 << qubits[2]))
                                modified_positions.append(other)
                                new_vec[pos] = vector[other]
                                new_vec[other] = vector[pos]
                        elif op == 'ccz':
                            if all((pos >> qubit) & 1 for qubit in qubits):
                                new_vec[pos] = vector[pos].multiply_by_minus_one(None)

                        elif op == 'measure' or op == 'meas':
                            if self.no_measurement:
                                new_vec = vector.copy()
                                continue
                            new_vec = vector.measure(qubits, self.measurement_outcome)
                            break
                        else:
                            raise NotImplementedError(f"Gate {op} is not yet implemented")


                if self.complex_representation == FiveTuple:
                    if op in ['h', 'ch']:
                        new_vec.k += 1
                    elif op in ['sx', 'sxdg', 'csx', 'sqrtswap']:
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
        vectors = [vec]
        return self.simulate(vectors, gates)
    
    """
    simulate input circuit with a set of custom input vectors
    """
    def simulate_custom(self, vectors: list[Vector]) -> list[tuple[Vector, Vector]]:
        gates, _ = self.parse_file()
        size = 2**self.stats['q']
        for i, vector in enumerate(vectors):
            if len(vector) != size:
                raise ValueError(f"input vector {i} has {len(vector)} amplitudes, the circuit acts on {self.stats['q']} qubit(s) ({size} amplitudes)")
            if vector.element_representation != self.complex_representation:
                raise ValueError(f"input vector {i} uses {vector.element_representation.__name__}, "
                                 f"the synthesis uses {self.complex_representation.__name__}")
        # simulate() replaces the elements of the list it gets, so the caller's list is left alone
        res = self.simulate(list(vectors), gates)
        for (inp, out) in res:
            self.stats['max_k'] = max(self.stats['max_k'], inp.k, out.k)
        return res

    """
    simulate the unitary part of RUS circuit (without the measurement) on states |0>, |1>, |+> for the target qubit
    """
    def simulate_rus(self, targets: int = 1, ancillas: int = 1) -> list[tuple[Vector, Vector]]:
        gates, vectors = self.parse_file()

        # targets are the lowest qubits, ancillas the highest; a narrower input is extended by ancillas, a wider one
        # would act on qubits that are neither
        width = targets + ancillas
        if targets < 1:
            raise ValueError("rus needs at least 1 target qubit")
        if self.matrix is not None and self.stats['q'] not in (targets, width):
            raise ValueError(f"the matrix acts on {self.stats['q']} qubit(s), but there are {targets} target(s) "
                             f"and {targets} + {ancillas} = {width} target and ancilla qubits")
        if self.matrix is None and self.stats['q'] > width:
            raise ValueError(f"the circuit has {self.stats['q']} qubits, but targets + ancillas = {targets} + {ancillas} = {width}")
        if self.matrix is not None and self.stats['q'] != width:
            new_matrix = Matrix.i()
            for _ in range(1, ancillas):
                new_matrix = new_matrix.tensor(Matrix.i())
            self.matrix = new_matrix.tensor(self.matrix)
        self.stats['q'] = width
                
        # initialize the basis_states |0>, |1>, |+>
        vectors = []
        
        # every computational basis state of the targets (|0...0> to |1...1>), ancillas in |0>
        for i in range(2**targets):
            vector = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
            vector[i] = self.complex_representation.one(None)
            vectors.append(vector)
            
        # |+>^targets, ancillas in |0>
        vector = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=targets)
        for i in range(2**targets):
            amplitude = self.complex_representation.one(None)
            for _ in range(targets):
                amplitude = amplitude.divide_by_sqrt2(None)
            vector[i] = amplitude
        vectors.append(vector)
        return self.simulate(vectors, gates)
    
    def simulate_jamiolkowski(self) -> list[tuple[Vector, Vector]]:
        # expand the circuit to 2n qubits and using jamiolkowski isomorphism,
        gates, vectors = self.parse_file()
        # add new gates creating the maximally entangled state
        pre_gates = []
        for i in range(self.stats['q']):
            pre_gates.append(('h', [i]))
        
        for i in range(self.stats['q']):
            j = i + self.stats['q']
            pre_gates.append(('cx', [i, j]))
        
        self.stats['q'] = 2 * self.stats['q']
        
        # create new input state
        vec = Vector(q=2**self.stats['q'], generator=None, element_representation=self.complex_representation, k=0)
        vec[0] = self.complex_representation.one(None)
        vectors = [vec]
        res = self.simulate(vectors, pre_gates)
        input_state = res[0][1] # get output of the simulation
        vectors = [input_state]
        
        return self.simulate(vectors, gates)
    
    """
    simulate the given input circuit by creating the unitary matrix instead of vectors
    """
    def simulate_matrix(self) -> Matrix:
        gates, vectors = self.parse_file()
        if not self.no_measurement and any(gate == 'measure' for gate, _ in gates):
            raise ValueError("a circuit with measurements has no unitary matrix (no_measurement ignores them)")
        outputs = [output for _, output in self.simulate(vectors, gates)]
        # every column went through the same gates, so they share k
        return Matrix(matrix=[[column[row] for column in outputs] for row in range(len(outputs))], k=outputs[0].k)
        
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