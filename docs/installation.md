---
title: Installation
---

[Home](./) · [Installation](installation) · [Usage](usage) · [Reference](reference)

## Requirements

- **Linux on x86-64.** The bundled solver binaries are Linux x86-64 executables.
- **Python 3.12.** This is the version CI tests with. The pinned NumPy needs at least Python 3.11.

## Get MILQ and its Python dependencies

```console
$ git clone https://github.com/QuantumFIT/milq.git
$ cd milq
$ python3 -m venv .venv && source .venv/bin/activate
$ pip install -r requirements.txt
```

MILQ is not packaged; it runs from the repository (see [Usage](usage)).

## Solvers

You need at least one solver. **yices2 and cvc5 work out of the box** and are enough to get started.

| Solver | How to get it | Notes |
|---|---|---|
| yices2, cvc5, OpenSMT | bundled in `solvers/` | Ready to use |
| SMTInterpol | bundled in `solvers/` | Needs Java 21 (`sudo apt install openjdk-21-jdk`) |
| z3 | `sudo apt install z3` | Must be on `PATH` as `z3`; the `z3-solver` pip package provides only the Python library |
| dReal | [dReal 4.21.06.2](https://github.com/dreal/dreal4) | Expected at `/opt/dreal/4.21.06.2/bin/dreal` |
| Gurobi | `gurobipy` (installed by `requirements.txt`) | See below |

The `portfolio` option runs every compatible SMT solver, so it needs z3, and Java for SMTInterpol.

If the bundled binaries lost their executable bit (e.g. after copying the repository), restore it:

```console
$ chmod +x solvers/cvc5/cvc5 solvers/opensmt/opensmt solvers/yices2/yices_smt2 solvers/smtinterpol/smtinterpol
```

### Gurobi license

`pip install gurobipy` comes with a **size-limited license**: models with at most 2000 variables and constraints. That is enough for very small instances, e.g. a 2-qubit circuit with `-v zero -c Classic`. Larger instances fail with *"Model too large for size-limited license"*. Gurobi offers [free academic licenses](https://www.gurobi.com/academia/academic-program-and-licenses/). Follow Gurobi's instructions to install the `gurobi.lic` file.

## Check the installation

```console
$ python3 cli/cli.py -s smt -a yices2 benchmarks/ghz/2.qasm
synthesis successful
```

To run the test suite (uses yices2, cvc5 and the size-limited Gurobi license):

```console
$ pip install pytest
$ pytest
```
