class GateSet:
    def __init__(self, gate_set=None, preset=None):
        # preset -- Clifford+T, Clifford
        # {gate_name: weight, ...}
        self.gates = {}

        if gate_set is not None:
            for gate in gate_set:
                self.set_gate(gate, 1)
                self.set_gate('I', 1)
        elif preset is not None:
            if preset == 'Clifford+T':
                self.set_gate('I', 1)
                self.set_gate('H', 1)
                self.set_gate('S', 1)
                self.set_gate('Sdg', 1)
                self.set_gate('CX', 1)
                self.set_gate('T', 1)
                self.set_gate('Tdg', 1)
            elif preset == 'Clifford':
                self.set_gate('I', 1)
                self.set_gate('H', 1)
                self.set_gate('S', 1)
                self.set_gate('Sdg', 1)
                self.set_gate('CX', 1)
            else:
                raise ValueError(f"Unknown preset: {preset}")
        # else empty gate set, will be filled later

    def add_gate(self, gate, weight=1):
        self.gates[gate] = weight
    
    def set_gate(self, gate, weight=1):
        self.gates[gate] = weight

    def append(self, gate, weight=1):
        self.gates[gate] = weight
    
    def list_gates(self):
        gates = []
        for gate in self.gates:
            gates.append(gate)
        return gates

    def set_t_optimal(self):
        if 'T' not in self.gates or 'Tdg' not in self.gates:
            raise ValueError("T and Tdg are not in the gate set")
        self.set_all_to_zero()
        self.set_gate('T', 1)
        self.set_gate('Tdg', 1)

    def set_cx_optimal(self):
        if 'CX' not in self.gates:
            raise ValueError("CX is not in the gate set")
        self.set_all_to_zero()
        self.set_gate('CX', 1)

    def set_all_to_zero(self):
        for gate in self.gates:
            self.gates[gate] = 0

    def __contains__(self, gate):
        return gate in self.gates

    def __len__(self):
        return len(self.gates)

    def __str__(self):
        list_gates = self.list_gates()
        return str(list_gates)

    def __repr__(self):
        list_gates = self.list_gates()
        return repr(list_gates)

    def __iter__(self):
        return iter(self.gates)
    