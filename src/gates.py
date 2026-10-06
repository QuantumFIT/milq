"""
@file: gates.py
@author: Jakub Havlík
@date: 11.05.2026
@brief: Gate-set class implementation, abstraction over Circuits and Gates
"""


# all supported gates in the tool
supported_gates = [
    ['h','s','sdg','t','id','tdg','x','y','z','sx','sxdg'],
    ['cx','swap', 'iswap', 'ch','cs','csdg','cy','cz','dcx','csx', 'xcx', 'sqrtswap'],
    ['ccx','cswap','ccz']
]

self_adjoints = ['h', 'x', 'y', 'z', 'cx', 'cz', 'cy', 'ch', 'swap', 'dcx', 'ccx', 'ccz']

# OpenQASM 3 definitions of supported gates that are not part of stdgates.inc
nonstandard_gate_definitions = {
    'sxdg': "gate sxdg a { inv @ sx a; }",
    'cs': "gate cs a, b { ctrl @ s a, b; }",
    'csdg': "gate csdg a, b { ctrl @ sdg a, b; }",
    'csx': "gate csx a, b { ctrl @ sx a, b; }",
    'xcx': "gate xcx a, b { negctrl @ x a, b; }",
    'dcx': "gate dcx a, b { cx a, b; cx b, a; }",
    'iswap': "gate iswap a, b { s a; s b; h a; cx a, b; cx b, a; h b; }",
    'sqrtswap': "gate sqrtswap a, b { pow(0.5) @ swap a, b; }",
    'ccz': "gate ccz a, b, c { ctrl(2) @ z a, b, c; }",
}

# convert gate name to number of qubits
def gate_to_qubits(gate : str) -> int:
    for i, gates in enumerate(supported_gates):
        if gate in gates:
            return i + 1
    raise ValueError(f"Gate {gate} is not supported")

# check if all gates from the gate set are supported by Synthesizer (synth.py)
def check_supported(gate_set : 'GateSet') -> bool:
    for gate in gate_set:
        if gate not in supported_gates[0] and gate not in supported_gates[1] and gate not in supported_gates[2]:
            return False
    return True

class GateSet:
    """
    represent full gate-set with the information about qubits and weights for synthesis
    """

    def __init__(self, gate_set: list[str] = None, preset: str = None) -> None:
        # preset -- Clifford+T, Clifford
        # {gate_name: weight, ...}
        self.gates = {}
        self.qubits = {}

        if gate_set is not None:
            for gate in gate_set:
                if gate == 'id':
                    continue
                self.set_gate(gate=gate, qubits=gate_to_qubits(gate), weight=1)
            self.set_gate(gate='id', qubits=1, weight=0)
        elif preset is not None:
            if preset == 'Clifford+T':
                self.set_gate(gate='id', qubits=1, weight=0)
                self.set_gate(gate='x', qubits=1, weight=1)
                self.set_gate(gate='z', qubits=1, weight=1)
                self.set_gate(gate='h', qubits=1, weight=1)
                self.set_gate(gate='s', qubits=1, weight=1)
                self.set_gate(gate='sdg', qubits=1, weight=1)
                self.set_gate(gate='cx', qubits=2, weight=1)
                self.set_gate(gate='t', qubits=1, weight=1)
                self.set_gate(gate='tdg', qubits=1, weight=1)
            elif preset == 'Clifford':
                self.set_gate(gate='id', qubits=1, weight=0)
                self.set_gate(gate='h', qubits=1, weight=1)
                self.set_gate(gate='s', qubits=1, weight=1)
                self.set_gate(gate='sdg', qubits=1, weight=1)
                self.set_gate(gate='cx', qubits=2, weight=1)
            else:
                raise ValueError(f"Unknown preset: {preset}")
        # else empty gate set, will be filled later


    # add a new gate to the gate set with corresponding number of qubits and weight
    def add_gate(self, gate : str, weight : int = 1, qubits : int = 1) -> None:
        self.gates[gate] = weight
        self.qubits[gate] = qubits
    
    def set_gate(self, gate : str, weight : int = 1, qubits : int = 1) -> None:
        self.add_gate(gate, weight, qubits)

    def append(self, gate : str, weight : int = 1, qubits : int = 1) -> None:
        self.add_gate(gate, weight, qubits)
    
    # list all gates (names)
    def list_gates(self) -> list[str]:
        gates = []
        for gate in self.gates:
            gates.append(gate)
        return gates

    # define the T-optimality objective
    # only T weight matters
    def set_t_optimal(self) -> None:
        if 't' not in self.gates or 'tdg' not in self.gates:
            raise ValueError("t and tdg are not in the gate set")
        self.set_all_to_zero()
        self.set_gate('t', 1)
        self.set_gate('tdg', 1)

    # set only CX count to matter
    def set_cx_optimal(self) -> None:
        if 'cx' not in self.gates:
            raise ValueError("cx is not in the gate set")
        self.set_all_to_zero()
        self.set_gate('cx', 1)

    # reset all weights to 0
    def set_all_to_zero(self) -> None:
        for gate in self.gates:
            self.gates[gate] = 0

    def __contains__(self, gate : str) -> bool:
        return gate in self.gates

    def __len__(self) -> int:
        return len(self.gates)

    def __str__(self) -> str:
        list_gates = self.list_gates()
        return str(list_gates)

    def __repr__(self) -> str:
        list_gates = self.list_gates()
        return repr(list_gates)

    def __iter__(self):
        return iter(self.gates)
    
    @classmethod
    def union(cls, set1, set2) -> 'GateSet':
        # union of two gate sets
        new_set = GateSet()
        for gate in set1:
            new_set.add_gate(gate, set1.gates[gate], set1.qubits[gate])
        for gate in set2:
            new_set.add_gate(gate, set2.gates[gate], set2.qubits[gate])
        return new_set
    
    """
    get all gates from the gate set with respective number of qubits
    """
    def get_gates(self, q : int = 1) -> list[str]:
        gates = []
        for gate in self.gates:
            if self.qubits[gate] == q:
                gates.append(gate)
        return gates
    
    def get_weight(self, gate : str) -> int:
        return self.gates[gate]
    
    def get_qubits(self, gate : str) -> int:
        return self.qubits[gate]
    
    def max_weight(self) -> int:
        max_weight = 0
        for gate in self.gates:
            if self.gates[gate] > max_weight:
                max_weight = self.gates[gate]
        return max_weight
    
class Gate:
    # abstraction to represent OPENQASM gate
    def __init__(self, name: str, qubits: list[int]) -> None:
        self.name = name
        self.qubits = qubits
    
    def __str__(self) -> str:
        gate_str = f"{self.name} "
        for qubit in self.qubits:
            gate_str += f"q[{qubit}], "
        gate_str = gate_str[:-2]
        gate_str += ";"
        return gate_str
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def __eq__(self, other: 'Gate') -> bool:
        return self.name == other.name and self.qubits == other.qubits

class Circuit:
    # abstraction to represent quantum circuit for OPENQASM representation
    def __init__(self, gates: list[Gate], q: int, d: int) -> None:
        self.q = q
        self.d = d
        self.gates = gates
        self.bool_variables = []
        self.cost = 0
        self.measured_qubits = set()
        if len(gates) == 0:
            self.gates = [None] * d
            self.bool_variables = [None] * d
        else:
            for i, gate in enumerate(gates):
                gate_str = f"L{i}_{gate.name}"
                for qubit in gate.qubits:
                    gate_str += f"_q{qubit}"
                self.bool_variables.append(gate_str)
    
    def operations(self) -> list[Gate]:
        # the gates of the circuit, without empty and identity layers
        return [gate for gate in self.gates[:self.d] if gate is not None and gate.name != 'id']

    def __str__(self) -> str:
        gates = self.operations()
        circuit_str = "OPENQASM 3.0;\ninclude \"stdgates.inc\";\n"
        defined = set()
        for gate in gates:
            if gate.name in nonstandard_gate_definitions and gate.name not in defined:
                circuit_str += f"{nonstandard_gate_definitions[gate.name]}\n"
                defined.add(gate.name)
        circuit_str += f"qubit[{self.q}] q;\nbit[{self.q}] c;\n"
        for gate in gates:
            circuit_str += f"{gate}\n"
        for qubit in sorted(self.measured_qubits):
            circuit_str += f"c[{qubit}] = measure q[{qubit}];\n"
        return circuit_str
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def write_to_file(self, output_qasm: str) -> None:
        with open(output_qasm, 'w') as f:
            f.write(self.__str__())
            
    def draw(self, output_file : str) -> None:
        from qiskit import QuantumCircuit
        from qiskit.circuit.library import SwapGate
        
        # add supported gates qiskit has no method for
        sqrtswap = SwapGate().power(0.5)
        sqrtswap.label = "√SWAP"
        xcx = QuantumCircuit(2, name="xcx")
        xcx.x(0)
        xcx.cx(0, 1)
        xcx.x(0)
        custom = {'xcx': xcx.to_gate(), 'sqrtswap': sqrtswap}
        # build the circuit
        circuit = QuantumCircuit(self.q)
        for gate in self.operations():
            if gate.name in custom:
                circuit.append(custom[gate.name], gate.qubits)
            else:
                getattr(circuit, gate.name)(*gate.qubits)
        circuit.draw(output="mpl", filename=output_file, reverse_bits=True)
        
    def add_measurement(self, qubits: list[int]) -> None:
        self.measured_qubits.update(qubits)
            
    def append(self, gate: Gate) -> None:
        self.gates.append(gate)
        
    def __getitem__(self, d: int) -> Gate:
        return self.gates[d]
    
    def __setitem__(self, d: int, gate: Gate) -> None:
        self.gates[d] = gate
        gate_str = f"L{d}_{gate.name}"
        for qubit in gate.qubits:
            gate_str += f"_q{qubit}"
        self.bool_variables[d] = gate_str
        
    def t_count(self) -> int:
        count = 0
        for gate in self.operations():
            if gate.name == 't' or gate.name == 'tdg':
                count += 1
        return count
    
    def gate_count(self) -> int:
        return len(self.operations())
    
    def get_cost(self) -> int:
        return self.cost
    
    def set_cost(self, cost: int) -> None:
        self.cost = cost