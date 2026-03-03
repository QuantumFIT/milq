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
                self.set_gate(gate, 1, gate_to_qubits(gate))
            self.set_gate('id', 1)
        elif preset is not None:
            if preset == 'Clifford+T':
                self.set_gate('I', 1)
                self.set_gate('H', 1)
                self.set_gate('S', 1)
                self.set_gate('Sdg', 1)
                self.set_gate('CX', 1, 2)
                self.set_gate('T', 1)
                self.set_gate('Tdg', 1)
            elif preset == 'Clifford':
                self.set_gate('I', 1)
                self.set_gate('H', 1)
                self.set_gate('S', 1)
                self.set_gate('Sdg', 1)
                self.set_gate('CX', 1, 2)
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