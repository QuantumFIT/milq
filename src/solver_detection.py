"""
@file: solver_detection.py
@brief: the SMT solvers MILQ knows (how to find, call and download them), and generation of the solver
        configuration (solvers.toml) from the solvers installed on the computer
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from solver_config import SolverConfig


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    sha256: str  # as GitHub reports it for the release asset


@dataclass(frozen=True)
class KnownSolver:
    name: str
    executables: tuple[str, ...]  # names to look for, in order of preference; a download links the first
    logics: tuple[str, ...]
    args: tuple[str, ...] = ()
    incremental_args: tuple[str, ...] = ()
    globs: tuple[str, ...] = ()  # where else the solver is usually installed
    comment: str = ""
    releases: dict[str, Release] = field(default_factory=dict)  # by platform, for configure-solvers --download


_YICES = "https://github.com/SRI-CSL/yices2/releases/download/yices-2.7.0/yices-2.7.0-"
_CVC5 = "https://github.com/cvc5/cvc5/releases/download/cvc5-1.3.1/cvc5-"
_OPENSMT = "https://github.com/usi-verification-and-security/opensmt/releases/download/v2.9.2/opensmt-"

# the solvers MILQ knows how to call, in the order the portfolio lists them
KNOWN_SOLVERS = (
    # yices_smt2 is the name in the SMT-COMP builds
    KnownSolver("yices2", ("yices-smt2", "yices_smt2"), ("QF_LIA", "QF_LRA", "QF_NIA", "QF_NRA"),
                incremental_args=("--incremental",),
                releases={
                    "linux-x86_64": Release("2.7.0", _YICES + "x86_64-pc-linux-gnu-static-gmp.tar.gz",
                                            "49566b6f817692820538df78fe406878400d79810631c9372b2495bc81d3e00a"),
                    "darwin-arm64": Release("2.7.0", _YICES + "arm-apple-darwin24.5.0-static-gmp.tar.gz",
                                            "5682fedf13add7818e8d05796b9133e67844fce2bb72fd1ecc75dcb73167c7ac"),
                    "darwin-x86_64": Release("2.7.0", _YICES + "x86_64-apple-darwin21.6.0-static-gmp.tar.gz",
                                             "dff40838ae5674abed2c08c383d702c1358ad64627c15799d2a15e67d1b4495a"),
                }),
    KnownSolver("cvc5", ("cvc5",), ("QF_LIA", "QF_NIA", "QF_NRA"),
                args=("--produce-models",), incremental_args=("--incremental",),
                releases={
                    "linux-x86_64": Release("1.3.1", _CVC5 + "Linux-x86_64-static.zip",
                                            "1a1cda20d2df4938fa4944a69f33ddc9172e319ece0eed0aa09c4d7abede3ed1"),
                    "linux-arm64": Release("1.3.1", _CVC5 + "Linux-arm64-static.zip",
                                           "fe2b661834a82fd8830f7a757c340f0e20041fa41e19b038fa02ace0eaf1c6f2"),
                    "darwin-arm64": Release("1.3.1", _CVC5 + "macOS-arm64-static.zip",
                                            "a0e7f5b03b1bc4284fbfff7cdfb08c704801701cf7ece83a13f8a505e7581215"),
                    "darwin-x86_64": Release("1.3.1", _CVC5 + "macOS-x86_64-static.zip",
                                             "e7fe4af9491bd7c0db7591c0a483775735bd1a98b23933fd337a73ae39c10ff9"),
                }),
    KnownSolver("opensmt", ("opensmt",), ("QF_LIA", "QF_LRA"),
                releases={
                    "linux-x86_64": Release("2.9.2", _OPENSMT + "x64-linux-static.tar.bz2",
                                            "be4767bf5d6c08bc7f4f49ae1480f2ae2ac8f38a277d0ec39d56badd974b84bd"),
                    "darwin-arm64": Release("2.9.2", _OPENSMT + "arm-osx.tar.bz2",
                                            "6c8605db38e0f62ea040cffc670e65bd5f47e4fb65ecd65c6aaf4170cd19c51c"),
                    "darwin-x86_64": Release("2.9.2", _OPENSMT + "x64-osx.tar.bz2",
                                             "b376e0339793f1ed5c546155f865de10fb39d1346d1788b57c80dfb538375ada"),
                }),
    KnownSolver("smtinterpol", ("smtinterpol",), ("QF_LIA", "QF_NIA"),
                comment="no QF_NRA: SMTInterpol answers unknown to any nonlinear real term"),
    KnownSolver("z3", ("z3",), ("QF_LIA", "QF_NIA", "QF_NRA"), incremental_args=("-in",)),
    KnownSolver("dreal", ("dreal",), ("QF_NRA",),
                args=("--precision", "1e-9", "--produce-models"), incremental_args=("--in",),
                globs=("/opt/dreal/*/bin/dreal",),
                comment="--precision is dReal's delta: it answers delta-sat when the formula holds up to that precision"),
)

# a satisfiable formula for each logic, to check that a solver runs
_CHECKS = {
    "QF_LIA": "(set-logic QF_LIA)\n(declare-fun x () Int)\n(assert (> x 1))\n(check-sat)\n(exit)\n",
    "QF_LRA": "(set-logic QF_LRA)\n(declare-fun x () Real)\n(assert (> x 1.0))\n(check-sat)\n(exit)\n",
    "QF_NIA": "(set-logic QF_NIA)\n(declare-fun x () Int)\n(assert (> (* x x) 1))\n(check-sat)\n(exit)\n",
    "QF_NRA": "(set-logic QF_NRA)\n(declare-fun x () Real)\n(assert (> (* x x) 1.0))\n(check-sat)\n(exit)\n",
}

HEADER = """\
# SMT solvers available to `milq -s smt`, generated by ./configure-solvers from the solvers installed on this
# computer. Run it again after installing a solver, or edit this file. Each [solvers.NAME] table defines one
# solver; NAME is what `-a NAME` selects. The names `portfolio`, `gurobi` and `cbc` are reserved.
#
#   path              the executable. A relative path is relative to this file, a bare name (e.g. "z3")
#                     is looked up on PATH, and ~ and $VARIABLES are expanded.
#   args              arguments always passed to the solver (default: none)
#   incremental_args  extra arguments for the incremental modes, where MILQ sends the formula through
#                     stdin instead of a file (default: none)
#   logics            SMT-LIB logics the solver supports, from QF_LIA, QF_LRA, QF_NIA, QF_NRA.
#                     FiveTuple formulas are QF_LIA, Classic ones QF_NRA.
#   portfolio         whether `-a portfolio` runs this solver (default: true). The portfolio runs every
#                     such solver whose logics include the formula's logic.
#
# To use another file, pass `--solver-config FILE` or set the MILQ_SOLVER_CONFIG environment variable.
"""


def candidates(solver: KnownSolver, search_dirs: list[str] = (), path: str | None = None) -> list[str]:
    # executables that may be the solver: from search_dirs (and their bin/), then PATH, then the usual places
    found = []
    for directory in search_dirs:
        for subdir in (directory, os.path.join(directory, "bin")):
            for executable in solver.executables:
                candidate = os.path.join(subdir, executable)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    found.append(candidate)
    for executable in solver.executables:
        candidate = shutil.which(executable, path=path)
        if candidate:
            found.append(candidate)
    for pattern in solver.globs:
        # the newest version first
        found.extend(sorted((p for p in glob.glob(pattern) if os.access(p, os.X_OK)), reverse=True))
    unique = []
    for candidate in map(os.path.abspath, found):
        if candidate not in unique:
            unique.append(candidate)
    return unique


def check(solver: KnownSolver, executable: str, timeout: float = 30) -> str | None:
    # None if the solver answers sat to a trivial formula, else why it doesn't work
    with tempfile.TemporaryDirectory() as tmp:
        formula = os.path.join(tmp, "check.smt2")
        with open(formula, "w") as f:
            f.write(_CHECKS[solver.logics[0]])
        try:
            # in tmp: some solvers write files into the working directory
            result = subprocess.run([executable, *solver.args, formula], cwd=tmp, capture_output=True, text=True,
                                    timeout=timeout)
        except OSError as e:
            return str(e)
        except subprocess.TimeoutExpired:
            return f"no answer within {timeout:g} s"
    # SMTInterpol may answer "success" to every command
    words = [word for word in result.stdout.split() if word != "success"]
    if words and words[0] in ("sat", "delta-sat"):
        return None
    output = (result.stdout + result.stderr).strip().splitlines()
    return f"exit code {result.returncode}" + (f": {output[0]}" if output else ", no output")


@dataclass(frozen=True)
class Detection:
    solver: KnownSolver
    path: str | None  # the working executable, None if there is none
    rejected: tuple[tuple[str, str], ...] = ()  # (executable, why it doesn't work)

    def config(self) -> SolverConfig:
        return SolverConfig(name=self.solver.name, path=self.path, logics=self.solver.logics, args=self.solver.args,
                            incremental_args=self.solver.incremental_args)


def detect(search_dirs: list[str] = (), path: str | None = None, timeout: float = 30) -> list[Detection]:
    detections = []
    for solver in KNOWN_SOLVERS:
        rejected = []
        working = None
        for executable in candidates(solver, search_dirs, path):
            problem = check(solver, executable, timeout)
            if problem is None:
                working = executable
                break
            rejected.append((executable, problem))
        detections.append(Detection(solver, working, tuple(rejected)))
    return detections


def _toml_list(items) -> str:
    # JSON strings are valid TOML basic strings
    return "[" + ", ".join(json.dumps(item) for item in items) + "]"


def render(detections: list[Detection]) -> str:
    tables = []
    for detection in detections:
        solver = detection.solver
        if detection.path is None:
            continue
        lines = [f"# {solver.comment}"] if solver.comment else []
        lines.append(f"[solvers.{solver.name}]")
        lines.append(f"path = {json.dumps(detection.path)}")
        if solver.args:
            lines.append(f"args = {_toml_list(solver.args)}")
        if solver.incremental_args:
            lines.append(f"incremental_args = {_toml_list(solver.incremental_args)}")
        lines.append(f"logics = {_toml_list(solver.logics)}")
        tables.append("\n".join(lines) + "\n")
    missing = [d.solver.name for d in detections if d.path is None]
    footer = [f"# not found: {', '.join(missing)}\n"] if missing else []
    return "\n".join([HEADER, *tables, *footer])
