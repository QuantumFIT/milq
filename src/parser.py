
import re
from generator import Generator
from gates import Circuit, Gate
from complex.vector import Vector

class ModelParser:
    """
    class that converts model from any solver to QASM file
    """
    def __init__(self) -> None:
        self.stats = {}
        self.stats['gate_counts'] = {} # gate name -> count
        self.stats['cost'] = 0 # total cost of the circuit
        self.complex_representation = None
        self.v = None
        self.q = None
        self.d = None


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
            if var.name.startswith("I_"):
                items.append((var.name, var.value()))
        for var in gen.real_variables:
            if var.name.startswith("I_"):
                if var.value() is not None:
                    items.append((var.name, float(var.value())))
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

    def filter_items(self, model : any) -> tuple[Circuit, list[Vector]]:
        # get only the (gate, true) tuples
        new_items = []
        costs = [None] * (self.d + 1)
        best_indice = 0
        circ = Circuit(gates=[], q=self.q, d=self.d)
        out_vectors = [Vector(q=2**self.q, generator=None, element_representation=self.complex_representation, k=0) for _ in range(self.v)]
        for item in model:
            if isinstance(item, tuple) and len(item) >= 2:
                var_obj, value_obj = item[0], item[1]
                variable = str(var_obj)
                if variable.startswith("L"):
                    parse = False
                    if isinstance(value_obj, bool):
                        if value_obj:
                            parse = True
                    else:
                        if value_obj.is_true():
                            parse = True
                    if parse:
                        parts = variable.split("_")
                        d = int(parts[0][1:])
                        gate = parts[1]
                        gate_qubits = [int(p[1:]) for p in parts[2:]]
                        gate = Gate(name=gate, qubits=gate_qubits)
                        circ[d] = gate
                
                if variable.startswith("I_") and self.v != 0:
                    # check that I_{pair_idx}_{d}_{indice}_part, d == depth
                    parts = variable.split("_")
                    d = int(parts[2])
                    if d != self.d: continue

                    if isinstance(value_obj, float) or isinstance(value_obj, int):
                        # parse part of a vector -- check which vector by pair_idx, then index in the vector and which coefficient it is
                        pair_idx = int(parts[1])
                        if parts[3] == "k":
                            out_vectors[pair_idx].k = int(value_obj)
                        else:
                            indice = int(parts[3])
                            coeff = parts[4].strip()
                            if coeff == "r":
                                coeff = "real"
                            elif coeff == "i":
                                coeff = "imag"
                        setattr(out_vectors[pair_idx][indice], coeff, value_obj)
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
        circ.cost = self.stats['cost']
        return circ, out_vectors

    def parse(self, model : any, qubits : int, depth : int, output_qasm : str = "circuit.qasm", complex_representation: any = None, write_to_file : bool = True, v : int = 0) -> tuple[bool, Circuit, list[Vector]]:
        if complex_representation is not None:
            self.complex_representation = complex_representation
        self.v = v
        self.q = qubits
        self.d = depth
        items = model
        if isinstance(model, Generator):
            try:
                items = self.expand_milp_model(model)
            except Exception as e:
                print(f"Error expanding MILP model: {e}")
                return False
        elif isinstance(model, str):
            items = self.parse_model_to_items(model)

        circ, vectors = self.filter_items(items)

        if write_to_file:
            circ.write_to_file(output_qasm)
            png_filename = output_qasm.split(".")[0] + ".png"
            circ.draw(output_file=png_filename)
        return True, circ, vectors

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