from z3 import *
import numpy as np
from complex_numbers import Complex, ComplexVector
from qasm import save_to_qasm
import time
import resource

n  = 4
d1 = 5
s  = Optimize()

# define the input vector(s)
In = ComplexVector(q=2**n, name="In")
s.add(In[0] == Complex(1, 0))
for i in range(1, 2**n):
    s.add(In[i] == Complex(0, 0))

# intermediate vectors for each operation
inter = [ComplexVector(q=2**n, name=f"I{d}") for d in range(d1 + 1)]
s.add(inter[0] == In)



inv_sqrt2 = Complex(1/np.sqrt(2), 0)
minus1    = Complex(-1, 0)
i_phase   = Complex(0, 1)
t_phase   = Complex(np.sqrt(1/2), np.sqrt(1/2))

def encode_layer(slv, inp, out, layer):
    sel_vars = []

    # ---- single-qubit gates ----
    single_sel = {}                     # (gate,q) → Bool
    for gate in ['H','S','T','I']:
        for q in range(n):
            v = Bool(f"L{layer}_{gate}_q{q}")
            single_sel[(gate,q)] = v
            sel_vars.append(v)

    # ---- two-qubit gate (CNOT) ----
    two_sel = {}                        # (c,t) → Bool
    for c in range(n):
        for t in range(n):
            if c == t: continue
            v = Bool(f"L{layer}_CNOT_c{c}t{t}")
            two_sel[(c,t)] = v
            sel_vars.append(v)

    # ---- exactly ONE gate per layer ----
    slv.add(AtLeast(*sel_vars, 1))
    slv.add(AtMost (*sel_vars, 1))
    
    # ---------------------------------------------------------- I
    for (gate,q), sel in single_sel.items():
        if gate != 'I': continue
        for a in range(2**n):
            slv.add(Implies(sel, out[a] == inp[a]))

    # ---------------------------------------------------------- H
    for (gate,q), sel in single_sel.items():
        if gate != 'H': continue
        visited = set()
        for a in range(2**n):
            if a in visited: continue
            b = a ^ (1 << q)
            visited.update([a,b])
            slv.add(Implies(sel, out[a] == (inp[a] + inp[b]) * inv_sqrt2))
            slv.add(Implies(sel, out[b] == (inp[a] + inp[b]*minus1) * inv_sqrt2))

    # ---------------------------------------------------------- S
    for (gate,q), sel in single_sel.items():
        if gate != 'S': continue
        for a in range(2**n):
            bit = (a >> q) & 1
            if bit == 0:
                slv.add(Implies(sel, out[a] == inp[a]))
            else:
                slv.add(Implies(sel, out[a] == inp[a] * i_phase))

    # ---------------------------------------------------------- T
    for (gate,q), sel in single_sel.items():
        if gate != 'T': continue
        for a in range(2**n):
            bit = (a >> q) & 1
            if bit == 0:
                slv.add(Implies(sel, out[a] == inp[a]))
            else:
                slv.add(Implies(sel, out[a] == inp[a] * t_phase))

    # ---------------------------------------------------------- CNOT
    for (c,t), sel in two_sel.items():
        for a in range(2**n):
            control_on = ((a >> c) & 1) == 1
            if not control_on:
                slv.add(Implies(sel, out[a] == inp[a]))
            else:
                b = a ^ (1 << t)
                slv.add(Implies(sel, out[a] == inp[b]))   # |…c=1,t=0⟩ → |…c=1,t=1⟩
                slv.add(Implies(sel, out[b] == inp[a]))   # |…c=1,t=1⟩ → |…c=1,t=0⟩

# --------------------------------------------------------------
for d in range(d1):
    encode_layer(s, inter[d], inter[d+1], d)


# ---------- target  ----------
Target = ComplexVector(q=2**n, name="Target")
s.add(Target[0]               == Complex(1/np.sqrt(2), 0))
s.add(Target[2**n - 1]        == Complex(1/np.sqrt(2), 0))
for i in range(1, 2**n - 1):
    s.add(Target[i] == Complex(0, 0))

# Maximize the fidelity between Target and inter[d1]
Re = Sum([Target[k].real * inter[d1][k].real + Target[k].imag * inter[d1][k].imag 
          for k in range(2**n)])
Im = Sum([Target[k].real * inter[d1][k].imag - Target[k].imag * inter[d1][k].real 
          for k in range(2**n)])
F = Re**2 + Im**2
s.maximize(F)

# Minimize number of non-identity gates selected across all layers
cost_terms = []
for d in range(d1):
    for q in range(n):
        cost_terms.append(If(Bool(f"L{d}_H_q{q}"), 1, 0))
        cost_terms.append(If(Bool(f"L{d}_S_q{q}"), 1, 0))
        cost_terms.append(If(Bool(f"L{d}_T_q{q}"), 1, 0))
    for c in range(n):
        for t in range(n):
            if c == t:
                continue
            cost_terms.append(If(Bool(f"L{d}_CNOT_c{c}t{t}"), 1, 0))

total_cost = Sum(cost_terms) if cost_terms else IntVal(0)
s.minimize(total_cost)

# --------------------------------------------------------------
print("checking ...")
start_time = time.perf_counter()
result = s.check()
elapsed_s = time.perf_counter() - start_time
stats = s.statistics()

if result == sat:
    m = s.model()
    print("=== circuit found ===")
    for d in range(d1):
        gates = [str(decl) for decl in m.decls()
                 if str(m[decl]) == "True" and f"L{d}_" in str(decl)]
        if gates:
            print(f"Layer {d}: {', '.join(gates)}")
    save_to_qasm(n, d1, m, "circuit.qasm")
    fidelity_val = m.eval(F)
    print(f"Fidelity: {fidelity_val.as_decimal(10)}")
else:
    print("UNSAT")

# --- statistics ---
print("=== stats ===")
print(f"result: {result}")
print(f"wall_time_s: {elapsed_s:.6f}")
try:
    for k in ["time", "memory", "max memory", "num conflicts", "rlimit count"]:
        if k in stats:
            print(f"z3_{k.replace(' ', '_')}: {stats[k]}")
except Exception:
    pass
try:
    ru = resource.getrusage(resource.RUSAGE_SELF)
    print(f"process_peak_rss_kb: {ru.ru_maxrss}")
except Exception:
    pass