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
            # L{d}_I_q{q}  -> id q[q];
            # L{d}_CNOT_c{c}t{t} -> cx q[c],q[t];
            if "_H_q" in name:
                q = int(name.split("_H_q")[1])
                f.write(f"h q[{q}];\n")
                return
            if "_S_q" in name:
                q = int(name.split("_S_q")[1])
                f.write(f"s q[{q}];\n")
                return
            if "_T_q" in name:
                q = int(name.split("_T_q")[1])
                f.write(f"t q[{q}];\n")
                return
            if "_I_q" in name:
                q = int(name.split("_I_q")[1])
                f.write(f"id q[{q}];\n")
                return
            if "_CNOT_c" in name and "t" in name:
                tail = name.split("_CNOT_c")[1]
                c_str, t_str = tail.split("t")
                c = int(c_str)
                t = int(t_str)
                f.write(f"cx q[{c}],q[{t}];\n")
                return
        for d in range(d1):
            for decl in sorted(m.decls(), key=lambda dcl: dcl.name()):
                name = decl.name()
                if f"L{d}_" in name and str(m[decl]) == "True":
                    emit_gate(name)
    return True