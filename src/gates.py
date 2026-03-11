"""
@file: gates.py
@author: Jakub Havlík
@date: 19.02.2026
@brief: gate-set class implementation
"""


# all supported gates in the tool
supported_gates = [
    ['h','s','sdg','t','id','tdg','x','y','z','sx','sxdg'],
    ['cx','swap', 'iswap', 'ch','cs','csdg','cy','cz','dcx','csx', 'xcx', 'sqrtswap'],
    ['ccx','cswap','ccz']
]

self_adjoints = ['h', 'x', 'y', 'z', 'cx', 'cz', 'cy', 'ch', 'swap', 'dcx', 'ccx', 'ccz']

# convert gate name to number of qubits
def gate_to_qubits(gate : str) -> int:
    for i, gates in enumerate(supported_gates):
        if gate in gates:
            return i + 1
    raise ValueError(f"Gate {gate} is not supported")

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
        if 'T' not in self.gates or 'Tdg' not in self.gates:
            raise ValueError("T and Tdg are not in the gate set")
        self.set_all_to_zero()
        self.set_gate('T', 1)
        self.set_gate('Tdg', 1)

    # set only CX count to matter
    def set_cx_optimal(self) -> None:
        if 'CX' not in self.gates:
            raise ValueError("CX is not in the gate set")
        self.set_all_to_zero()
        self.set_gate('CX', 1)

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
    
    def max_weight(self) -> int:
        max_weight = 0
        for gate in self.gates:
            if self.gates[gate] > max_weight:
                max_weight = self.gates[gate]
        return max_weight
    
class Gate:
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
    def __init__(self, gates: list[Gate], q: int, d: int) -> None:
        self.q = q
        self.d = d
        self.gates = gates
        self.bool_variables = []
        if len(gates) == 0:
            self.gates = [None] * d
            self.bool_variables = [None] * d
        else:
            for i, gate in enumerate(gates):
                gate_str = f"L{i}_{gate.name}"
                for qubit in gate.qubits:
                    gate_str += f"_q{qubit}"
                self.bool_variables.append(gate_str)
    
    def __str__(self) -> str:
        circuit_str = f"OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[{self.q}];\ncreg c[{self.q}];\n"
        for d in range(self.d):
            gate = self.gates[d]
            if gate is None: continue
            circuit_str += f"{gate}\n"
        return circuit_str
    
    def __repr__(self) -> str:
        return self.__str__()
    
    def write_to_file(self, output_qasm: str) -> None:
        with open(output_qasm, 'w') as f:
            f.write(self.__str__())
            
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