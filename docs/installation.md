---
title: Installation
---

[Home](./) · [Installation](installation) · [Usage](usage) · [Reference](reference)

# Installation

## Requirements

- **Linux.** MILQ is developed and tested on Linux (CI runs Ubuntu on x86-64).
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

You need at least one solver. MILQ does not ship SMT solvers: install the ones you want, then let `./configure-solvers` find them (see [below](#solver-configuration)). z3 comes with the Python dependencies; **yices2** is the solver the examples and tests use, and a good one to add.

| Solver | How to get it | Notes |
|---|---|---|
| yices2 | [release binaries](https://github.com/SRI-CSL/yices2/releases) (`bin/yices-smt2` in e.g. `yices-2.6.5-x86_64-pc-linux-gnu-static-gmp.tar.gz`) | |
| cvc5 | [release binaries](https://github.com/cvc5/cvc5/releases) (e.g. `cvc5-Linux-x86_64-static.zip`) | |
| OpenSMT | [OpenSMT](https://github.com/usi-verification-and-security/opensmt) | FiveTuple only |
| SMTInterpol | [smtinterpol.jar](https://ultimate.informatik.uni-freiburg.de/smtinterpol/) | Needs Java 21 (`sudo apt install openjdk-21-jdk`) and an executable `smtinterpol` wrapper, e.g. `java -jar /path/to/smtinterpol.jar "$@"`. FiveTuple only |
| z3 | `z3-solver` (installed by `requirements.txt`), or `sudo apt install z3` | `z3-solver` puts `z3` into the virtual environment's `bin` |
| dReal | [dReal 4](https://github.com/dreal/dreal4) | Classic only; also found in `/opt/dreal/*/bin` |
| Gurobi | `gurobipy` (installed by `requirements.txt`) | See [below](#gurobi-license); needs no configuration |

The `portfolio` option runs every configured SMT solver that supports the formula's logic. Solvers that fail are skipped.

### Solver configuration

Where the SMT solvers are and how they are called is set in `solvers.toml` in the repository root. `./configure-solvers` writes it for the solvers it finds on your `PATH` (with the virtual environment active, so that it finds `z3`):

```console
$ ./configure-solvers
yices2: /usr/local/bin/yices-smt2
cvc5: /home/me/cvc5/bin/cvc5
opensmt: not found
smtinterpol: not found
z3: /home/me/milq/.venv/bin/z3
dreal: not found
wrote /home/me/milq/solvers.toml
```

It looks for `yices-smt2` (or `yices_smt2`), `cvc5`, `opensmt`, `smtinterpol`, `z3` and `dreal`, and keeps each one only if it answers a trivial formula, so e.g. SMTInterpol without Java is left out. `-s DIR` also looks in `DIR` and `DIR/bin`, `-o FILE` writes another file (`-` for standard output), and `--force` overwrites an existing one. Run it again after installing a solver.

Each `[solvers.NAME]` table of the file defines one solver, and `-a NAME` selects it:

### Solver configuration

The SMT solvers are defined in `solvers.toml` in the repository root. Each `[solvers.NAME]` table defines one solver, and `-a NAME` selects it:

```toml
[solvers.cvc5]
path = "/home/me/cvc5/bin/cvc5"       # a relative path is relative to solvers.toml, a bare name is looked up on PATH
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

You can edit the file: to add a solver that `configure-solvers` does not know, add a table; the names `portfolio`, `gurobi` and `cbc` are reserved. `solvers.toml` is not tracked by git. To use another file, pass it with `--solver-config FILE`, or set the `MILQ_SOLVER_CONFIG` environment variable (`--solver-config` takes precedence).

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
