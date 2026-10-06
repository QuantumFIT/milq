---
title: Usage
---

[Home](./) · [Installation](installation) · [Usage](usage) · [Reference](reference)

# Usage

Synthesis is run with `cli/cli.py`. It can be started from any directory: paths are relative to the current directory, which is also where the output files go.

```console
$ python3 cli/cli.py [options] <input.qasm>
```

All options are listed in the [command-line reference](reference). This page walks through the choices you usually make.

## Input circuits

The input is an OpenQASM 2.0 or 3.0 file with a single quantum register. Examples are in `benchmarks/`.

- **Registers:** `qreg q[n];` / `creg c[n];` (2.0), or `qubit[n] q;` / `bit[n] c;` (3.0).
- **Gates without parameters,** one per statement, applied to qubits `q[i]`: `h`, `x`, `y`, `z`, `s`, `sdg`, `t`, `tdg`, `sx`, `sxdg`, `id`, `cx`, `cz`, `ch`, `ccx`, `dcx`, and `xcx` (a CX controlled on \|0⟩).
- **Measurements at the end:** `measure q[i] -> c[i];` (2.0) or `c[i] = measure q[i];` (3.0). See [Measurements](#measurements).
- Comments and `gate` definitions are skipped.

## 1. Pick what must be preserved (`-v`)

MILQ simulates the input circuit on a set of input states and requires the synthesized circuit to produce the same output states.

| `-v` | Input states | Meaning |
|---|---|---|
| `all` (default) | all 2<sup>n</sup> computational basis states | the two circuits implement the same unitary |
| `zero` | only \|0…0⟩ | state preparation: the same state is produced from \|0…0⟩ |
| `jamiolkowski` | one maximally entangled state on 2n qubits | the same unitary, checked with a single vector |
| `rus` | \|0⟩, \|1⟩ and \|+⟩ on the targets, ancillas in \|0⟩ | repeat-until-success circuits, see [below](#repeat-until-success-circuits) |

`-v zero` is usually much faster than `-v all`, but it only guarantees the state prepared from \|0…0⟩:

```console
$ python3 cli/cli.py -s smt -a cvc5 -v zero benchmarks/ghz/3.qasm
...
h q[2];
cx q[2], q[1];
cx q[2], q[0];
```

## 2. Pick a backend (`-s`, `-a`, `-c`)

| `-s` | `-a` | What runs |
|---|---|---|
| `smt` | a solver name | The formula is sent to an external SMT solver. In incremental mode a single solver keeps running, and new layers are added with `push`/`pop`. |
| `smt` | `portfolio` | All compatible SMT solvers run in parallel on each formula, and the first answer wins. |
| `gurobi` (default) | `gurobi` | The problem is built directly in Gurobi's Python API. |
| `milp` | `gurobi` | The problem is built as a PuLP model and solved by Gurobi. |

The **complex-number representation** (`-c`) decides which SMT solvers can be used:

| `-c` | Arithmetic | SMT solvers |
|---|---|---|
| `FiveTuple` (default) | exact, linear integer (QF_LIA) | yices2, cvc5, OpenSMT, SMTInterpol, z3 |
| `Classic` | floating point *a* + *bi*, nonlinear real (QF_NRA) | yices2, cvc5, SMTInterpol, z3, dReal |

FiveTuple is exact and usually the fastest choice for Clifford+T circuits. Classic is needed for end-of-circuit measurements and is the practical choice for approximate synthesis.

```console
$ python3 cli/cli.py -s smt -a opensmt benchmarks/ghz/2.qasm      # FiveTuple, OpenSMT
$ python3 cli/cli.py -s gurobi -c Classic -v zero benchmarks/ghz/2.qasm
```

## 3. Pick a search mode (`-m`)

| `-m` | What it does |
|---|---|
| `incremental` (default) | Tries 1, 2, 3, … layers until a circuit is found, so the result has the minimum number of gates. |
| `basic` | Encodes a fixed number of layers *d* (the input's gate count, or `-d`) and solves once. Gurobi minimizes the gate count within *d* layers. SMT solvers return *some* circuit with at most *d* gates. |
| `bottomup`, `topdown`, `binary` | Encode *d* layers like `basic`, then search over a bound on the gate count: upwards from 0, downwards from *d* + 1, or by bisection. |
| `pareto-incremental` | Enumerates all circuits depth by depth and keeps a Pareto front of cost vs. probability of success (useful for RUS circuits; other circuits always succeed). Every point is written to `pareto_front/` and the front is plotted to `pareto_front.pdf`. It stops at the input's gate count (RUS: at the `-pt` time limit). |

The gate set is the set of gates in the input circuit plus Clifford+T (`x`, `z`, `h`, `s`, `sdg`, `t`, `tdg`, `cx`). Every gate costs 1. An empty layer (`id`) costs 0, so circuits shorter than *d* are allowed in the fixed-depth modes.

```console
$ python3 cli/cli.py -s smt -a yices2 -m bottomup benchmarks/ghz/2.qasm
```

## Measurements

If the input circuit measures qubits at the end, the synthesized circuit must produce the same post-measurement state, and that requires `-c Classic`. To ignore the final measurements instead, pass `-nm`. Circuits from [MQT Bench](https://www.cda.cit.tum.de/mqtbench/) end with measurements, for example:

```console
$ python3 cli/cli.py -s smt -a yices2 -nm benchmarks/mqt-bench/ghz_nativegates_clifford+t_opt2_2.qasm
```

## Equivalence up to global phase

With `-u`, the synthesized circuit may differ from the input by a global phase. For FiveTuple, the phase is a multiple of π/4.

```console
$ python3 cli/cli.py -s smt -a yices2 -u -v zero benchmarks/ghz/2.qasm
```

**Warning:** In incremental SMT mode, `-u` currently works only with a single input state (`-v zero`). With `-v all` it crashes ([#7](https://github.com/QuantumFIT/milq/issues/7)). With Gurobi it works in both cases.

## Approximate synthesis

With `-ap`, the circuits only need an average fidelity of at least `-f` (default 1.0). The fidelity constraint is nonlinear. Gurobi handles small instances quickly, while SMT solvers can take very long.

```console
$ python3 cli/cli.py -ap -f 0.9 -c Classic -s gurobi -v zero benchmarks/ghz/2.qasm
```

## Repeat-until-success circuits

With `-v rus`, the input circuit is treated as a repeat-until-success (RUS) circuit with `-T` target qubits (the lowest indices) and `-A` ancilla qubits (the highest indices). The input states are \|0⟩, \|1⟩ and \|+⟩ on the targets, with the ancillas in \|0⟩. The cost counts only `t`/`tdg` gates (T-count). Examples are in `benchmarks/rus/`.

```console
$ python3 cli/cli.py -v rus -T 1 -A 1 -c Classic -s gurobi benchmarks/rus/2/spec.qasm
```

**Note:** RUS instances need a full Gurobi license; they exceed the size-limited one.

## Output

On success, `cli.py` prints the timing of each phase and the synthesized circuit:

```console
synthesis successful
Full time: 0.27 seconds
Parsing time: 0.002 seconds
Encoding time: 0.11 seconds
Solving time: 0.15 seconds
Updating time: 0 seconds
OPENQASM 3.0;
...
```

The following files are written:

| File | Content |
|---|---|
| `-o` path (default `circuit.qasm`) | the synthesized circuit in OpenQASM 3.0 |
| the same name with `.smt2` or `.lp` | the last formula given to the solver |
| `synth.log` in the current directory | a detailed log of the run |

**Note:** The directory of the `-o` path must already exist.

The circuit file uses `include "stdgates.inc";`. If it uses gates that are not in the standard library (e.g. `sxdg`, `dcx`, `ccz`), their definitions are added at the top. Measured qubits are written as `c[i] = measure q[i];`. The file can be loaded by other tools, for example with `qiskit.qasm3.loads`.

## Known limitations

- **Beyond the input's gate count:** incremental SMT synthesis crashes if it needs more layers than the input circuit has gates ([#5](https://github.com/QuantumFIT/milq/issues/5)). This only happens with `-d` or settings under which the input circuit itself is not a solution.
- **Solver errors:** a solver error or crash is treated like "no circuit at this depth" ([#4](https://github.com/QuantumFIT/milq/issues/4)), and a portfolio can hang if every solver answers *unknown* ([#9](https://github.com/QuantumFIT/milq/issues/9)).
- **Gurobi statuses:** Gurobi results other than *optimal* or *infeasible*, such as a time limit, are treated as success ([#8](https://github.com/QuantumFIT/milq/issues/8)).
- **Input gates:** `swap`, `iswap`, `cy`, `cs`, `csdg`, `csx`, `sqrtswap`, `cswap` and `ccz` can appear in synthesized circuits but are not yet accepted in input circuits ([#18](https://github.com/QuantumFIT/milq/issues/18)).

All open issues are listed on [GitHub](https://github.com/QuantumFIT/milq/issues).
