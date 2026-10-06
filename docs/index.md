---
---

[Home](./) · [Installation](installation) · [Usage](usage) · [Reference](reference)

<p align="center">
  <img src="{{ '/milq-logo.png' | relative_url }}" alt="MILQ logo" width="300">
</p>

**MILQ** (**M**ixed **I**nteger linear programming & first order **L**ogic **Q**uantum circuit synthesis) takes a quantum circuit in OpenQASM and finds an equivalent circuit with the **minimum number of gates**. It encodes the synthesis problem as an SMT formula or a mixed integer linear program (MILP) and lets a solver find the circuit.

## How it works

MILQ simulates the input circuit on a set of input states and asks a solver for a circuit of *d* layers, with one gate per layer, that maps every input state to the same output state. In the default **incremental** mode, *d* starts at 1 and grows until the solver finds a circuit, so the first circuit found has the minimum gate count.

- **Exact arithmetic for Clifford+T.** Amplitudes of Clifford+T circuits can be written exactly as (*a* + *b*ω + *c*ω² + *d*ω³) / √2<sup>*k*</sup> with integers *a*–*d*, *k* and ω = e<sup>iπ/4</sup>. With this **FiveTuple** representation the whole problem is linear integer arithmetic, so there is no rounding. A floating-point **Classic** (*a* + *bi*) representation is available too, for cases that need it (end-of-circuit measurements, approximate synthesis).
- **Several backends.** SMT solvers (yices2, cvc5, OpenSMT, SMTInterpol, z3 and dReal, or a portfolio of them running in parallel) or the Gurobi MILP solver.
- **Different notions of equivalence.** Full unitary equivalence on all basis states, state preparation from \|0…0⟩, equivalence up to global phase, approximate equivalence with a fidelity threshold, and repeat-until-success (RUS) circuits.

## Quick example

The GHZ state preparation circuit in `benchmarks/ghz/3.qasm` is synthesized with yices2 (bundled with MILQ) in about a second:

```console
$ python3 cli/cli.py -s smt -a yices2 benchmarks/ghz/3.qasm
synthesis successful
...
OPENQASM 3.0;
include "stdgates.inc";
qubit[3] q;
bit[3] c;
h q[0];
cx q[0], q[1];
cx q[1], q[2];
```

Continue with [Installation](installation) and [Usage](usage).
