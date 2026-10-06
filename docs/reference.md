---
title: Command-line reference
---

[Home](./) · [Installation](installation) · [Usage](usage) · [Reference](reference)

## `cli/cli.py`: synthesis

```console
$ python3 cli/cli.py [options] <qasm_file>
```

| Option | Values | Default | Description |
|---|---|---|---|
| `qasm_file` | path | *(required)* | Input circuit ([format](usage#input-circuits)). |
| `-v`, `--vectors` | `all`, `zero`, `jamiolkowski`, `rus` | `all` | Input states the circuits must agree on ([details](usage#1-pick-what-must-be-preserved--v)). |
| `-s`, `--solving` | `smt`, `gurobi`, `milp` | `gurobi` | Solving method ([details](usage#2-pick-a-backend--s--a--c)). |
| `-a`, `--solver` | `yices2`, `cvc5`, `opensmt`, `smtinterpol`, `z3`, `dreal`, `portfolio`, `gurobi` | `gurobi` | Solver; SMT solvers require `-s smt`. |
| `-c`, `--complex_representation` | `FiveTuple`, `Classic` | `FiveTuple` | Representation of amplitudes. |
| `-m`, `--mode` | `incremental`, `basic`, `bottomup`, `topdown`, `binary`, `pareto-incremental` | `incremental` | Search mode ([details](usage#3-pick-a-search-mode--m)). |
| `-d`, `--depth` | integer | input gate count | Number of layers for the fixed-depth modes. |
| `-u`, `--up_to_global_phase` | flag | off | Allow a global phase difference. |
| `-ap`, `--approx` | flag | off | Approximate synthesis. |
| `-f`, `--fidelity_threshold` | number in [0, 1] | `1.0` | Minimum average fidelity for `-ap`. |
| `-T`, `--targets` | integer | `1` | Number of target qubits for `-v rus`. |
| `-A`, `--ancillas` | integer | `1` | Number of ancilla qubits for `-v rus`. |
| `-nm`, `--no_measurement` | flag | off | Ignore end-of-circuit measurements in the input. |
| `-o`, `--output_qasm` | path | `circuit.qasm` | Where to write the synthesized circuit. |
| `-b`, `--basis` | `cb` | `cb` | Basis of the encoding; only the computational basis is available. |

## `cli/simulator.py`: simulation

Prints the input and output vectors of a circuit in MILQ's own representations. It is useful to see what the synthesizer will be asked to match.

```console
$ python3 cli/simulator.py -v zero -c Classic benchmarks/ghz/2.qasm
[(1 + 0j), (0 + 0j), (0 + 0j), (0 + 0j)], k=0
[(0.7071067811865476 + 0.0j), (0.0 + 0.0j), (0.0 + 0.0j), (0.7071067811865476 + 0.0j)], k=0
--------------------------------
```

| Option | Values | Default | Description |
|---|---|---|---|
| `qasm_file` | path | *(required)* | Input circuit. |
| `-v`, `--vectors` | `all`, `zero`, `jamiolkowski`, `rus`, `matrix` | `all` | Input states to simulate, or `matrix` for the whole unitary. |
| `-c`, `--complex_representation` | `FiveTuple`, `Classic` | `FiveTuple` | Representation of amplitudes. FiveTuple vectors are printed as tuples with the exponent `k`. |
| `-T`, `--targets` | integer | `1` | Target qubits for `-v rus`. |
| `-A`, `--ancillas` | integer | `1` | Ancilla qubits for `-v rus`. |
| `-m`, `--meas` | `0` or `1` | `0` | Outcome assumed for measurements in the circuit. |

## Python API

The synthesizer can also be called from Python, with `src/` on the module path:

```python
import sys
sys.path.insert(0, "path/to/milq/src")
from synth import Synthesizer

synthesizer = Synthesizer()
ok, circuit, _ = synthesizer.synthesis(
    qasm_file="benchmarks/ghz/3.qasm",
    vectors="all",
    solving="smt", solver="yices2",
    mode="incremental",
    complex_representation="FiveTuple",
    output_qasm="ghz3_opt.qasm",
)
print(ok)                               # True
print(circuit)                          # the circuit as OpenQASM 3.0
print(synthesizer.logger.get_times())   # time per phase, in seconds
```

The keyword arguments mirror the command-line options (`vectors` ↔ `-v`, `solving` ↔ `-s`, `solver` ↔ `-a`, `mode` ↔ `-m`, `complex_representation` ↔ `-c`, `d` ↔ `-d`, `up_to_global_phase` ↔ `-u`, `approx` ↔ `-ap`, `fidelity_threshold` ↔ `-f`, `targets` ↔ `-T`, `ancillas` ↔ `-A`, `no_measurement` ↔ `-nm`). Two more are available only from Python:

- `gate_set=GateSet([...])` (from `gates`) restricts the gates the synthesized circuit may use.
- `vectors="custom"` together with `vector_pairs`, `q`, `d` and `gate_set` gives the (input, output) state pairs directly instead of a QASM file. Fixed-depth modes do not work with it yet ([#27](https://github.com/QuantumFIT/milq/issues/27)).

Create a new `Synthesizer` for every run.
