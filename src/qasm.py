def save_to_qasm(n, d1, m, filename):
    with open(filename, 'w') as f:
        f.write("OPENQASM 2.0;\n")
        f.write("include \"qelib1.inc\";\n")
        f.write("qreg q[%d];\n" % n)
        f.write("creg c[%d];\n" % n)
        def emit_gate(name: str):
            # Expected formats:
            # L{d}_H_q{q}  -> h q[q];
            # L{d}_S_q{q}  -> s q[q];
            # L{d}_T_q{q}  -> t q[q];
            # L{d}_Tdg_q{q}  -> tdg q[q];
            # L{d}_X_q{q}  -> x q[q];
            # L{d}_Y_q{q}  -> y q[q];
            # L{d}_Z_q{q}  -> z q[q];
            # L{d}_I_q{q}  -> id q[q];
            # L{d}_CX_c{c}t{t} -> cx q[c],q[t];
            # L{d}_CCX_c{c1}c{c2}t{t} -> ccx q[c1],q[c2],q[t];
            if "_CCX_c" in name and "t" in name:
                # Parse L{d}_CCX_c{c1}c{c2}t{t}
                # Example: L0_CCX_c0c1t2 -> c1=0, c2=1, t=2
                tail = name.split("_CCX_c")[1]
                # tail is like "0c1t2"
                # Split by 'c' to get ["0", "1t2"]
                parts = tail.split("c")
                if len(parts) >= 2:
                    c1 = int(parts[0])
                    # parts[1] is like "1t2", split by 't'
                    rest = parts[1]
                    t_part = rest.split("t")
                    if len(t_part) >= 2:
                        c2 = int(t_part[0])
                        t = int(t_part[1])
                        f.write(f"ccx q[{c1}],q[{c2}],q[{t}];\n")
                        return
            if "_RCCX_c" in name and "t" in name:
                # Parse L{d}_RCCX_c{c1}c{c2}t{t}
                # Example: L0_RCCX_c0c1t2 -> c1=0, c2=1, t=2
                tail = name.split("_RCCX_c")[1]
                parts = tail.split("c")
                if len(parts) >= 2:
                    c1 = int(parts[0])
                    rest = parts[1]
                    t_part = rest.split("t")
                    if len(t_part) >= 2:
                        c2 = int(t_part[0])
                        t = int(t_part[1])
                        f.write(f"rccx q[{c1}],q[{c2}],q[{t}];\n")
                        return
            if "_CSWAP_c" in name and "t" in name:
                tail = name.split("_CSWAP_c")[1]
                # tail is like "0c1t2"
                # Split by 'c' to get ["0", "1t2"]
                parts = tail.split("c")
                if len(parts) >= 2:
                    c1 = int(parts[0])
                    # parts[1] is like "1t2", split by 't'
                    rest = parts[1]
                    t_part = rest.split("t")
                    if len(t_part) >= 2:
                        c2 = int(t_part[0])
                        t = int(t_part[1])
                        f.write(f"cswap q[{c1}],q[{c2}],q[{t}];\n")
                        return
            if "_CCZ_c" in name and "t" in name:
                tail = name.split("_CCZ_c")[1]
                parts = tail.split("c")
                if len(parts) >= 2:
                    c1 = int(parts[0])
                    rest = parts[1]
                    t_part = rest.split("t")
                    if len(t_part) >= 2:
                        c2 = int(t_part[0])
                        t = int(t_part[1])
                        f.write(f"ccz q[{c1}],q[{c2}],q[{t}];\n")
                        return
            if "_CX_c" in name and "t" in name:
                tail = name.split("_CX_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"cx q[{c}],q[{t}];\n")
                return
            if "_X_q" in name:
                q = int(name.split("_X_q")[1])
                f.write(f"x q[{q}];\n")
                return
            if "_Y_q" in name:
                q = int(name.split("_Y_q")[1])
                f.write(f"y q[{q}];\n")
                return
            if "_Z_q" in name:
                q = int(name.split("_Z_q")[1])
                f.write(f"z q[{q}];\n")
                return
            if "_H_q" in name:
                q = int(name.split("_H_q")[1])
                f.write(f"h q[{q}];\n")
                return
            if "_Sdg_q" in name:
                q = int(name.split("_Sdg_q")[1])
                f.write(f"sdg q[{q}];\n")
                return
            if "_S_q" in name:
                q = int(name.split("_S_q")[1])
                f.write(f"s q[{q}];\n")
                return
            # Check Tdg before T to avoid substring match
            if "_Tdg_q" in name:
                q = int(name.split("_Tdg_q")[1])
                f.write(f"tdg q[{q}];\n")
                return
            if "_T_q" in name:
                q = int(name.split("_T_q")[1])
                f.write(f"t q[{q}];\n")
                return
            if "_I_q" in name:
                q = int(name.split("_I_q")[1])
                f.write(f"id q[{q}];\n")
                return
            if "_SX_q" in name:
                q = int(name.split("_SX_q")[1])
                f.write(f"sx q[{q}];\n")
                return
            if "_SXdg_q" in name:
                q = int(name.split("_SXdg_q")[1])
                f.write(f"sxdg q[{q}];\n")
                return
            if "_XCX_c" in name and "t" in name:
                tail = name.split("_XCX_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"xcx q[{c}],q[{t}];\n")
                return
            if "_CX_c" in name and "t" in name:
                tail = name.split("_CX_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"cx q[{c}],q[{t}];\n")
                return
            if "_CS_c" in name and "t" in name:
                tail = name.split("_CS_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"cs q[{c}],q[{t}];\n")
                return
            if "_CSdg_c" in name and "t" in name:
                tail = name.split("_CSdg_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"csdg q[{c}],q[{t}];\n")
                return
            if "_CY_c" in name and "t" in name:
                tail = name.split("_CY_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"cy q[{c}],q[{t}];\n")
                return
            if "_CZ_c" in name and "t" in name:
                tail = name.split("_CZ_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"cz q[{c}],q[{t}];\n")
                return
            if "_CH_c" in name and "t" in name:
                tail = name.split("_CH_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"ch q[{c}],q[{t}];\n")
                return
            if "_DCX_c" in name and "t" in name:
                tail = name.split("_DCX_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"dcx q[{c}],q[{t}];\n")
                return
            if "_CSX_c" in name and "t" in name:
                tail = name.split("_CSX_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"csx q[{c}],q[{t}];\n")
                return
            if "_iSWAP_c" in name and "t" in name:
                tail = name.split("_iSWAP_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"iswap q[{c}],q[{t}];\n")
                return
            if "_SWAP_c" in name and "t" in name:
                tail = name.split("_SWAP_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"swap q[{c}],q[{t}];\n")
                return
            if "_sqrtSWAP_c" in name and "t" in name:
                tail = name.split("_sqrtSWAP_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"sqrtswap q[{c}],q[{t}];\n")
                return
            if "_isqrtSWAP_c" in name and "t" in name:
                tail = name.split("_isqrtSWAP_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"isqrtswap q[{c}],q[{t}];\n")
                return
        for d in range(d1):
            for decl in sorted(m.decls(), key=lambda dcl: dcl.name()):
                name = decl.name()
                if f"L{d}_" in name and str(m[decl]) == "True":
                    emit_gate(name)
    return True

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
                class SimpleModel:
                    def __init__(self, assignments):
                        self.assignments = assignments
                    def decls(self):
                        class Decl:
                            def __init__(self, name):
                                self.name_val = name
                            def name(self):
                                return self.name_val
                        return [Decl(name) for name in self.assignments.keys()]
                    def __getitem__(self, decl):
                        class Value:
                            def __str__(self):
                                return "True"
                        return Value()
                
                m = SimpleModel(gate_assignments)
                save_to_qasm(n, d1, m, output_qasm)
        else:
            raise ValueError("Solver returned UNSAT")
    else:
        raise ValueError(f"Solver returned error: {result.stderr}")
    
def parse_z3alpha(model_output, n, d1, output_qasm, result):
    parse_z3(model_output, n, d1, output_qasm, result)

def parse_cvc5(model_output, n, d1, output_qasm, result):
    """Parse cvc5 solver output - handles cvc5-specific format with parentheses wrapping."""
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
        class SimpleModel:
            def __init__(self, assignments):
                self.assignments = assignments
            def decls(self):
                class Decl:
                    def __init__(self, name):
                        self.name_val = name
                    def name(self):
                        return self.name_val
                return [Decl(name) for name in self.assignments.keys()]
            def __getitem__(self, decl):
                class Value:
                    def __str__(self):
                        return "True"
                return Value()
        
        m = SimpleModel(gate_assignments)
        save_to_qasm(n, d1, m, output_qasm)
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