---
title: Installation
---

[Home](./) · [Installation](installation) · [Usage](usage) · [Reference](reference)

# Installation

## Requirements

- **Linux on x86-64.** The bundled solver binaries are Linux x86-64 executables.
- **Python 3.11 or newer.** CI tests Python 3.11 with the lowest versions of the dependencies that `requirements.txt` allows, and Python 3.12 and 3.14 with the newest.

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
| z3 | `z3-solver` (installed by `requirements.txt`), or `sudo apt install z3` | Looked up on `PATH` as `z3`; `z3-solver` puts it into the virtual environment's `bin`, which is on `PATH` while the environment is active |
| dReal | [dReal 4.21.06.2](https://github.com/dreal/dreal4) | Expected at `/opt/dreal/4.21.06.2/bin/dreal` |
| Gurobi | `gurobipy` (installed by `requirements.txt`) | See below |

Where the SMT solvers are and how they are called is set in [`solvers.toml`](#solver-configuration).

The `portfolio` option runs every compatible SMT solver. Solvers that are not installed or that fail (e.g. SMTInterpol without Java) are skipped, so it works with just the bundled ones.

If the bundled binaries lost their executable bit (e.g. after copying the repository), restore it:

```console
$ chmod +x solvers/cvc5/cvc5 solvers/opensmt/opensmt solvers/yices2/yices_smt2 solvers/smtinterpol/smtinterpol
```

### Solver configuration

The SMT solvers are defined in `solvers.toml` in the repository root. Each `[solvers.NAME]` table defines one solver, and `-a NAME` selects it:

```toml
[solvers.cvc5]
path = "solvers/cvc5/cvc5"            # relative to solvers.toml; a bare name is looked up on PATH
args = ["--produce-models"]           # always passed
incremental_args = ["--incremental"]  # added in the incremental modes, which send the formula through stdin
logics = ["QF_LIA", "QF_NIA", "QF_NRA"]
```

| Key | Required | Meaning |
|---|---|---|
| `path` | yes | The executable. A relative path is relative to the configuration file, a bare name (e.g. `"z3"`) is looked up on `PATH`, and `~` and `$VARIABLES` are expanded. |
| `logics` | yes | SMT-LIB logics the solver supports, from `QF_LIA`, `QF_LRA`, `QF_NIA`, `QF_NRA`. FiveTuple formulas are `QF_LIA`, Classic ones `QF_NRA`. |
| `args` | no | Arguments always passed to the solver. |
| `incremental_args` | no | Extra arguments for the incremental modes. |
| `portfolio` | no | `false` keeps `-a portfolio` from running the solver (default `true`). |

To install a solver somewhere else, change its `path`. To add a solver, add a table; the names `portfolio`, `gurobi` and `cbc` are reserved. To keep your own settings outside the repository, copy the file and pass it with `--solver-config FILE`, or set the `MILQ_SOLVER_CONFIG` environment variable (`--solver-config` takes precedence).

### Gurobi license

`pip install gurobipy` comes with a **size-limited license**: models with at most 2000 variables and constraints. That is enough for very small instances, e.g. a 2-qubit circuit with `-v zero -c Classic`. Larger instances fail with *"Model too large for size-limited license"*. The license also expires about two years after the major release of gurobipy (13.x on 2027-11-29); after that, every Gurobi run fails with *"License expired"*, and `pip install -U gurobipy` brings a newer one. Gurobi offers [free academic licenses](https://www.gurobi.com/academia/academic-program-and-licenses/). Follow Gurobi's instructions to install the `gurobi.lic` file.

Without a Gurobi license, `-s milp -a cbc` solves the same MILP encoding with CBC, which ships with PuLP. It is much slower, though: `benchmarks/ghz/3.qasm` with `-v zero` takes about 2 minutes, against about a second with yices2.

## Put `milq` on your `PATH` (optional)

`milq` is an executable script in the repository root. To call it from anywhere, link it into a directory on your `PATH` (run in the repository root):

```console
$ ln -s "$PWD/milq" ~/.local/bin/milq
$ milq --help
```

## Check the installation

```console
$ ./milq -s smt -a yices2 benchmarks/ghz/2.qasm
synthesis successful
```

To run the test suite (uses yices2, cvc5 and the size-limited Gurobi license):

```console
$ pip install pytest
$ pytest
```
