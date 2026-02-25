
import re

def parse_z3(model_output, n, d1, output_qasm, result):
    if result.returncode == 0:
        output = result.stdout.strip()
        
        if output.startswith("sat"):
            model_output = result.stdout
            model_lines = model_output.split('\n')
            gate_assignments = {}
            i = 0
            while i < len(model_lines):
                line = model_lines[i].strip()
                if 'define-fun' in line.lower() and 'L' in line and '_' in line:
                    # (define-fun LX_GATE_qY () Bool true)
                    try:
                        start = line.find('define-fun')
                        if start >= 0:
                            start += len('define-fun')
                            end = line.find('()', start)
                            if end > start:
                                var_name = line[start:end].strip()
                                if var_name.startswith('L') and '_' in var_name:
                                    is_true = 'true' in line.lower()
                                    if not is_true and i + 1 < len(model_lines):
                                        next_line = model_lines[i + 1].strip().lower()
                                        if 'true' in next_line:
                                            is_true = True
                                    
                                    if is_true:
                                        gate_assignments[var_name] = True
                    except Exception:
                        pass
                i += 1
            
            if gate_assignments:
                save_to_qasm(n, d1, gate_assignments, output_qasm)
        else:
            raise ValueError("Solver returned UNSAT")
    else:
        raise ValueError(f"Solver returned error: {result.stderr}")
    
def parse_z3alpha(model_output, n, d1, output_qasm, result):
    parse_z3(model_output, n, d1, output_qasm, result)

def parse_cvc5(model_output, n, d1, output_qasm, result):
    if result.returncode != 0:
        raise ValueError(f"Solver returned error: {result.stderr}")
    
    output = result.stdout.strip()
    
    if not output.startswith("sat"):
        raise ValueError("Solver returned UNSAT")
    
    # cvc5 outputs: sat\n(\n(define-fun ...)\n...\n)
    # The model is wrapped in parentheses
    model_lines = result.stdout.split('\n')
    gate_assignments = {}
    i = 0
    while i < len(model_lines):
        line = model_lines[i].strip()
        if 'define-fun' in line.lower() and 'L' in line and '_' in line:
            try:
                if line.startswith('(define-fun'):
                    start = line.find('define-fun')
                    if start >= 0:
                        start += len('define-fun')
                        while start < len(line) and line[start] in ' \t':
                            start += 1
                        end = line.find('()', start)
                        if end > start:
                            var_name = line[start:end].strip()
                            if var_name.startswith('L') and '_' in var_name:
                                is_true = 'true' in line.lower()           
                                if is_true:
                                    gate_assignments[var_name] = True
            except Exception:
                pass
        i += 1
    
    if gate_assignments:
        save_to_qasm(n, d1, gate_assignments, output_qasm)
    else:
        raise ValueError("No gate assignments found in solver output")

def parse_opensmt(model_output, n, d1, output_qasm, result):
    parse_z3(model_output, n, d1, output_qasm, result)

def parse_smtinterpol(model_output, n, d1, output_qasm, result):
    lines = result.stdout.split('\n')
    filtered_lines = []
    found_result = False
    
    for line in lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        if line_lower in ['sat', 'unsat']:
            filtered_lines.append(line_stripped)
            found_result = True
        elif found_result:
            if line_lower != 'success' and line_stripped:
                filtered_lines.append(line)
    
    filtered_stdout = '\n'.join(filtered_lines)
    
    class FilteredResult:
        def __init__(self, original_result, filtered_stdout):
            self.returncode = original_result.returncode
            self.stdout = filtered_stdout
            self.stderr = original_result.stderr
    
    filtered_result = FilteredResult(result, filtered_stdout)
    
    parse_z3(model_output, n, d1, output_qasm, filtered_result)

def parse_yices2(model_output, n, d1, output_qasm, result):
    parse_cvc5(model_output, n, d1, output_qasm, result)
    
def parse_dreal(model_output, n, d1, output_qasm, result):    
    # should start with "delta-sat with delta = ..."
    # then come assignments LX_GATE_qY : True 
    
    if not model_output.startswith("delta-sat with delta = "):
        raise ValueError(f"Solver returned error: {model_output}")
    
    model_lines = result.stdout.split('\n')
    gate_assignments = {}
    i = 0
    while i < len(model_lines):
        line = model_lines[i].strip()
        if 'define-fun' in line.lower() and 'L' in line and '_' in line:
            try:
                if line.startswith('(define-fun'):
                    start = line.find('define-fun')
                    if start >= 0:
                        start += len('define-fun')
                        while start < len(line) and line[start] in ' \t':
                            start += 1
                        end = line.find('()', start)
                        if end > start:
                            var_name = line[start:end].strip()
                            if var_name.startswith('L') and '_' in var_name:
                                is_true = 'true' in line.lower()           
                                if is_true:
                                    gate_assignments[var_name] = True
            except Exception:
                pass
        i += 1
    
    if gate_assignments:
        save_to_qasm(n, d1, gate_assignments, output_qasm)
    else:
        raise ValueError("No gate assignments found in solver output")
    
class ModelParser:
    """
    class that converts model from any solver to QASM file
    """
    def __init__(self) -> None:
        self.stats = {}
        self.stats['gate_counts'] = {} # gate name -> count
        self.stats['cost'] = 0 # total cost of the circuit

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
        for item in model:
            if isinstance(item, tuple) and len(item) >= 2:
                var_obj, value_obj = item[0], item[1]
                variable = str(var_obj)
                if variable.startswith("L"):
                    if isinstance(value_obj, bool):
                        if value_obj:
                            new_items.append(variable)
                    else:
                        if value_obj.is_true():
                            new_items.append(variable)
                if variable == ("W" + str(depth)):
                    if isinstance(value_obj, int):
                        self.stats['cost'] = value_obj
                    elif isinstance(value_obj, float):
                        self.stats['cost'] = int(value_obj)
                    else:
                        self.stats['cost'] = int(value_obj.constant_value())
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
        if isinstance(model, str):
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