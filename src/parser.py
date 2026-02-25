
import re
from generator import Generator

class ModelParser:
    """
    class that converts model from any solver to QASM file
    """
    def __init__(self) -> None:
        self.stats = {}
        self.stats['gate_counts'] = {} # gate name -> count
        self.stats['cost'] = 0 # total cost of the circuit


    def expand_milp_model(self, gen : Generator) -> list:
        items = []
        for var in gen.bool_variables:
            if var.name.startswith("L"):
                if abs(var.value() - 1) < 1e-6:
                    items.append((var.name, True))
                else:
                    items.append((var.name, False))
        for var in gen.integer_variables:
            if var.name.startswith("W"):
                items.append((var.name, var.value()))
        return items



    def parse_model_to_items(self, model : str) -> list:
        lines = model.split('\n')
        items = []
        i = 0
        line = ""
        while i < len(lines):
            line += lines[i].strip()
            # match (<whitespaces>define-fun var_name () var_type var_value<whitespaces>)
            match = re.search(r"(\.*)\(\s*define-fun\s*(\w+)\s*\(\s*\)\s*(\w+)\s*(-?\d+|true|false)\s*\)\s*", line, re.IGNORECASE)
            if match:
                line = ""
                var_name = match.group(2)
                var_type = match.group(3)
                var_value = match.group(4)
                if var_type.lower() == "bool":
                    var_value = var_value.lower() == "true"
                elif var_type.lower() == "int":
                    var_value = int(var_value)
                elif var_type.lower() == "real":
                    var_value = float(var_value)
                items.append((var_name, var_value))
            i += 1
        return items

    def filter_items(self, model : any, depth : int) -> list:
        # get only the (gate, true) tuples
        new_items = []
        costs = [None] * (depth + 1)
        best_indice = 0
        for item in model:
            if isinstance(item, tuple) and len(item) >= 2:
                var_obj, value_obj = item[0], item[1]
                variable = str(var_obj)
                if variable.startswith("L"):
                    print(f"{variable}: {value_obj}")
                    if isinstance(value_obj, bool):
                        if value_obj:
                            new_items.append(variable)
                    else:
                        if value_obj.is_true():
                            new_items.append(variable)
                if variable.startswith("W"):
                    if value_obj is None: continue
                    indice = int(variable.split("W")[1].strip())
                    if indice > best_indice:
                        best_indice = indice
                    if isinstance(value_obj, int):
                        costs[indice] = value_obj
                    elif isinstance(value_obj, float):
                        costs[indice] = int(value_obj)
                    else:
                        costs[indice] = int(value_obj.constant_value())
        self.stats['cost'] = costs[best_indice]
        return new_items

    def write_circuit_to_qasm(self, circuit : list, qubits : int, output_qasm : str = "circuit.qasm") -> bool:
        with open(output_qasm, 'w') as f:
            f.write("OPENQASM 2.0;\n")
            f.write("include \"qelib1.inc\";\n")
            f.write(f"qreg q[{qubits}];\n")
            f.write(f"creg c[{qubits}];\n")
            for d in range(len(circuit)):
                if circuit[d] is None: continue
                gate, qubits = circuit[d]
                gate_str = gate + " "
                for qubit in qubits:
                    gate_str += f"q[{qubit}], "
                gate_str = gate_str[:-2]
                gate_str += ";\n"
                f.write(gate_str)

    def parse(self, model : any, qubits : int, depth : int, output_qasm : str = "circuit.qasm") -> bool:
        items = model
        if isinstance(model, Generator):
            items = self.expand_milp_model(model)
        elif isinstance(model, str):
            items = self.parse_model_to_items(model)

        gates = self.filter_items(items, depth)

        circuit = [None] * depth
        for gate in gates:
            # parse L{d}_{gate}_q{q}_q{q2}_q{q3}_
            parts = gate.split("_")
            d = int(parts[0][1:])
            gate = parts[1]
            if gate not in self.stats['gate_counts']:
                self.stats['gate_counts'][gate] = 0
            self.stats['gate_counts'][gate] += 1
            gate_qubits = [int(p[1:]) for p in parts[2:]]
            circuit[d] = (gate, gate_qubits)

        self.print_stats()
        self.write_circuit_to_qasm(circuit, qubits, output_qasm)
        return True
    
    def get_stats(self) -> dict:
        return self.stats
    
    def print_stats(self) -> None:
        print(f"Gate counts: {self.stats['gate_counts']}")
        print(f"Cost: {self.stats['cost']}")

    def is_sat(self, model : any) -> bool:
        if isinstance(model, str):
            if "sat" in model.lower() or "delta-sat" in model.lower():
                return True
            else:
                return False
        else:
            return True