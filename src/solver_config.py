"""
@file: solver_config.py
@brief: loading of the SMT solver configuration (solvers.toml in the repository root, written by ./configure-solvers)
"""

import os
import tomllib
from dataclasses import dataclass

DEFAULT_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "solvers.toml"))
ENV_VARIABLE = "MILQ_SOLVER_CONFIG"
LOGICS = ("QF_LIA", "QF_LRA", "QF_NIA", "QF_NRA")
# values of -a that do not name an SMT solver
RESERVED_NAMES = ("portfolio", "gurobi", "cbc")
_KEYS = {"path", "args", "incremental_args", "logics", "portfolio"}


class SolverConfigError(ValueError):
    """the solver configuration is missing or invalid, or names no usable solver"""


@dataclass(frozen=True)
class SolverConfig:
    name: str
    path: str
    logics: tuple[str, ...]
    args: tuple[str, ...] = ()
    incremental_args: tuple[str, ...] = ()
    portfolio: bool = True

    def command(self, incremental: bool = False) -> list[str]:
        return [self.path, *self.args, *(self.incremental_args if incremental else ())]


def config_path(path: str | None = None) -> str:
    # an explicit path wins over the environment variable, which wins over the file in the repository root
    return path or os.environ.get(ENV_VARIABLE) or DEFAULT_PATH


def _resolve(executable: str, base_dir: str) -> str:
    executable = os.path.expandvars(os.path.expanduser(executable))
    if os.sep not in executable:
        return executable  # a bare name is looked up on PATH when the solver starts
    return os.path.normpath(os.path.join(base_dir, executable))


def _string_list(where: str, key: str, value) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SolverConfigError(f"{where}: '{key}' must be a list of strings")
    return tuple(value)


def load_solver_config(path: str | None = None) -> dict[str, SolverConfig]:
    path = config_path(path)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        hint = f"; run {os.path.join(os.path.dirname(DEFAULT_PATH), 'configure-solvers')} to write it" if path == DEFAULT_PATH else ""
        raise SolverConfigError(f"{path}: solver configuration not found{hint}") from None
    except tomllib.TOMLDecodeError as e:
        raise SolverConfigError(f"{path}: {e}") from None

    unknown = set(data) - {"solvers"}
    if unknown:
        raise SolverConfigError(f"{path}: unknown top-level key(s) {sorted(unknown)}, expected [solvers.NAME] tables")
    tables = data.get("solvers", {})
    if not isinstance(tables, dict):
        raise SolverConfigError(f"{path}: 'solvers' must contain [solvers.NAME] tables")

    base_dir = os.path.dirname(os.path.abspath(path))
    solvers = {}
    for name, table in tables.items():
        where = f"{path}: [solvers.{name}]"
        if name in RESERVED_NAMES:
            raise SolverConfigError(f"{where}: '{name}' is reserved for -a {name}")
        if not isinstance(table, dict):
            raise SolverConfigError(f"{where}: must be a table")
        unknown = set(table) - _KEYS
        if unknown:
            raise SolverConfigError(f"{where}: unknown key(s) {sorted(unknown)}, expected {sorted(_KEYS)}")
        executable = table.get("path")
        if not isinstance(executable, str) or not executable:
            raise SolverConfigError(f"{where}: 'path' must be a non-empty string")
        logics = _string_list(where, "logics", table.get("logics"))
        if not logics or not set(logics) <= set(LOGICS):
            raise SolverConfigError(f"{where}: 'logics' must be a non-empty list from {list(LOGICS)}")
        portfolio = table.get("portfolio", True)
        if not isinstance(portfolio, bool):
            raise SolverConfigError(f"{where}: 'portfolio' must be true or false")
        solvers[name] = SolverConfig(name=name,
                                     path=_resolve(executable, base_dir),
                                     logics=logics,
                                     args=_string_list(where, "args", table.get("args", [])),
                                     incremental_args=_string_list(where, "incremental_args", table.get("incremental_args", [])),
                                     portfolio=portfolio)
    if not solvers:
        raise SolverConfigError(f"{path}: no solvers configured")
    return solvers
