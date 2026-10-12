<p align="center">
  <img src="docs/milq-logo.png" alt="MILQ logo" width="320">
</p>

# MILQ: A tool for gate-count optimal Quantum circuit synthesis

[![CI](https://github.com/QuantumFIT/milq/actions/workflows/ci.yml/badge.svg)](https://github.com/QuantumFIT/milq/actions/workflows/ci.yml)
[![codecov](https://img.shields.io/codecov/c/github/QuantumFIT/milq/master?logo=codecov)](https://codecov.io/gh/QuantumFIT/milq)

**MILQ** (**M**ixed **I**nteger linear programming & first order **L**ogic **Q**uantum circuit synthesis) is a tool for gate-count optimal quantum circuit synthesis for `OPENQASM` circuits using SMT and MILP encodings.

Supported solvers:
dReal, z3, cvc5, opensmt, yices2, smtinterpol, Gurobi

Paths and command-line arguments of the SMT solvers are set in [`solvers.toml`](solvers.toml); see the [solver configuration](https://quantum.fit.vut.cz/milq/installation#solver-configuration) docs.

## Installation Guide
**Dependencies:**
- dReal solver 4.21.06.2 -- Refer to the [Installation Guide](https://github.com/dreal/dreal4)
- z3 solver -- comes with `z3-solver` from `requirements.txt` (on `PATH` while the virtual environment is active), or `sudo apt install z3`
- to use `smtinterpol`, Java 21.0.10 is required (`sudo apt install openjdk-21-jdk`)
- Python 3.11 or newer, with the dependencies in `requirements.txt`
```
pip install -r requirements.txt
```
- Gurobi License for 13.0.1 version (Get free academic license on [Gurobi site](https://www.gurobi.com/)), refer to their installation manuals and create `gurobi.lic` file. (The license is not re-distributable without explicit agreement with Gurobi)

```
chmod +x solvers/smtinterpol/smtinterpol
chmod +x solvers/cvc5/cvc5
chmod +x solvers/opensmt/opensmt
chmod +x solvers/yices2/yices_smt2
```

## Usage
To synthesize a quantum circuit, run the `milq` script in the repository root. It can be called from any directory, or through a symlink on your `PATH` (e.g. `ln -s "$PWD/milq" ~/.local/bin/milq`).

CLI flags for exact synthesis:
- `-v` pick what vectors to use in the synthesis (either |0>^n, all CBS, jamiolkowski identity vector, or the three RUS states)
- `-s` pick a solving method (gurobi, milp, smt) -- milp is for PuLP pure MILP formulations
- `-m` choose the synthesis mode -- either incremental, basic, or one of search methods that minimize the gate variables
- `-a` choose a solver to use in the solving (portfolio or one of the supported solvers)
- `-o` output circuit file
- `-c` representation of complex numbers (Classic for a+bj, FiveTuple for algebraic five-tuples)
- `-u` for up to global phase equivalence instead of identity check
- `-nm` to ignore end-of-circuit measurements
- `-d` synthesize up to an allowed depth


Approximate synthesis uses the `-ap` flag and a set `-f X` fidelity threshold `X` (in [0,1])

RUS synthesis can also require the specification of `-T X`, `-A Y` to specify the number of target qubits `X` and number of ancillae `A`.

Examples, run from the repository root:

- SMT portfolio (five-tuples, incremental) - state |0>^n
```
./milq -v zero -c FiveTuple -s smt -a portfolio -m incremental benchmarks/ghz/2.qasm
```
-  Gurobi (a+bj, incremental) - state |0>^n
```
./milq -v zero -c Classic -s gurobi -m incremental benchmarks/ghz/2.qasm
```
- Gurobi (five-tuples, incremental), all CBS synthesis
```
./milq -v all -c FiveTuple -s gurobi -m incremental benchmarks/ghz/2.qasm
```


## Running tests
```
pip install pytest
pytest
```
The tests use the bundled yices2/cvc5 binaries and the size-limited license shipped with `gurobipy`. They run in CI on every push and pull request; CI uses the full Gurobi license from the organization secret `GUROBI_LICENSE` when it works there, and the size-limited one otherwise. Known bugs are marked `xfail` with their issue number. Strict mode is on, so a fix must remove its marker from `KNOWN_BUGS` in `tests/test_simulator.py`.

## Project Structure

```
- README.md
- milq (CLI for synthesis)
- requirements.txt
- solvers.toml (paths and arguments of the SMT solvers)
- benchmarks/
| - ghz (GHZ circuits)
| - bernstein-vazirani (BV circuits)
| - qsharp (benchmarks for comparison with Quokka#)
| - mqt-bench (MQT benchmark library Clifford+T circuits)
| - rus (repeat-until-success circuits)
- solvers/
| ... (solver binaries from SMT-comp -- cvc5, opensmt, yices2...)
- cli/
| - simulator.py (CLI interface for our small simulator module)
- src/
| - complex/
| | - classic.py (a+bj)
| | - fivetuple.py (algebraic fivetuples)
| | - matrix.py (unitary matrices)
| | - vector.py (vector abstraction)
| - gates.py (Gate-Set, Circuit, and Gates abstractions)
| - generator.py (generating of SMT formulae or MILP programs)
| - pareto.py (pareto front)
| - parser.py (parsing of solver outputs)
| - sim.py (simulator module)
| - solver_config.py (loading of solvers.toml)
| - solvers.py (abstraction over SMT solvers and Portfolio solver)
| - synth.py (main synthesis module)
| - timing.py (phase timings)
```
