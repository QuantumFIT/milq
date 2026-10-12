"""The SMT solver configuration (solvers.toml) and how synthesis uses it."""

import os
import subprocess
import sys

import pytest

from conftest import BENCHMARKS, REPO_ROOT
from solver_config import DEFAULT_PATH, ENV_VARIABLE, SolverConfigError, load_solver_config
from synth import Synthesizer

FAKE = os.path.join(os.path.dirname(__file__), "fake_solver.py")
YICES = os.path.join(REPO_ROOT, "solvers", "yices2", "yices_smt2")
GHZ2 = os.path.join(BENCHMARKS, "ghz/2.qasm")


def write_config(path, text):
    path.write_text(text)
    return str(path)


@pytest.fixture(autouse=True)
def no_config_from_environment(monkeypatch):
    monkeypatch.delenv(ENV_VARIABLE, raising=False)


def test_default_config():
    config = load_solver_config()
    assert list(config) == ["yices2", "cvc5", "opensmt", "smtinterpol", "z3", "dreal"]
    assert config["yices2"].command() == [YICES]
    assert config["yices2"].command(incremental=True) == [YICES, "--incremental"]
    assert config["cvc5"].command(incremental=True) == [os.path.join(REPO_ROOT, "solvers", "cvc5", "cvc5"),
                                                        "--produce-models", "--incremental"]
    assert config["z3"].path == "z3"  # looked up on PATH
    assert config["dreal"].logics == ("QF_NRA",)
    assert all(solver.portfolio for solver in config.values())


def test_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/home/someone")
    monkeypatch.setenv("SOLVERS", "/opt/solvers")
    path = write_config(tmp_path / "s.toml", """
[solvers.relative]
path = "bin/solver"
logics = ["QF_LIA"]
[solvers.home]
path = "~/solver"
logics = ["QF_LIA"]
[solvers.variable]
path = "$SOLVERS/solver"
logics = ["QF_LIA"]
[solvers.bare]
path = "solver"
logics = ["QF_LIA"]
""")
    config = load_solver_config(path)
    assert config["relative"].path == str(tmp_path / "bin" / "solver")  # relative to the configuration file
    assert config["home"].path == "/home/someone/solver"
    assert config["variable"].path == "/opt/solvers/solver"
    assert config["bare"].path == "solver"


def test_file_selection(tmp_path, monkeypatch):
    from_env = write_config(tmp_path / "env.toml", '[solvers.env]\npath = "a"\nlogics = ["QF_LIA"]\n')
    explicit = write_config(tmp_path / "explicit.toml", '[solvers.explicit]\npath = "a"\nlogics = ["QF_LIA"]\n')
    assert "yices2" in load_solver_config()
    monkeypatch.setenv(ENV_VARIABLE, from_env)
    assert list(load_solver_config()) == ["env"]
    assert list(load_solver_config(explicit)) == ["explicit"]


@pytest.mark.parametrize("text, message", [
    ('[solvers.a]\nlogics = ["QF_LIA"]\n', "'path' must be a non-empty string"),
    ('[solvers.a]\npath = "a"\n', "'logics' must be a list of strings"),
    ('[solvers.a]\npath = "a"\nlogics = ["QF_BV"]\n', "'logics' must be a non-empty list"),
    ('[solvers.a]\npath = "a"\nlogics = []\n', "'logics' must be a non-empty list"),
    ('[solvers.a]\npath = "a"\nlogics = ["QF_LIA"]\nargs = "-v"\n', "'args' must be a list of strings"),
    ('[solvers.a]\npath = "a"\nlogics = ["QF_LIA"]\nportfolio = "no"\n', "'portfolio' must be true or false"),
    ('[solvers.a]\npath = "a"\nlogics = ["QF_LIA"]\nflags = []\n', "unknown key(s) ['flags']"),
    ('[solvers.portfolio]\npath = "a"\nlogics = ["QF_LIA"]\n', "'portfolio' is reserved"),
    ('[solver.a]\npath = "a"\n', "unknown top-level key(s) ['solver']"),
    ('solvers = 1\n', "'solvers' must contain [solvers.NAME] tables"),
    ('[solvers]\na = 1\n', "[solvers.a]: must be a table"),
    ('', "no solvers configured"),
    ('[solvers.a\n', "s.toml: "),  # invalid TOML
])
def test_invalid_config(tmp_path, text, message):
    with pytest.raises(SolverConfigError) as error:
        load_solver_config(write_config(tmp_path / "s.toml", text))
    assert message in str(error.value)


def test_missing_config(tmp_path):
    with pytest.raises(SolverConfigError, match="solver configuration not found"):
        load_solver_config(str(tmp_path / "missing.toml"))


def synthesize(solver, config=None, mode="incremental", representation="FiveTuple"):
    return Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving="smt", solver=solver, mode=mode,
                                   complex_representation=representation, output_qasm="out.qasm", solver_config=config)


@pytest.mark.parametrize("mode", ["incremental", "basic"])
def test_synthesis_with_a_configured_solver(workdir, mode):
    config = write_config(workdir / "s.toml", f"""
[solvers.my-yices]
path = "{YICES}"
incremental_args = ["--incremental"]
logics = ["QF_LIA"]
""")
    res, circuit, _ = synthesize("my-yices", config, mode=mode)
    assert res
    assert circuit.gate_count() == 2


def test_portfolio_skips_excluded_solvers(workdir):
    config = write_config(workdir / "s.toml", f"""
[solvers.yices2]
path = "{YICES}"
logics = ["QF_LIA"]

[solvers.excluded]
path = "{sys.executable}"
args = ["{FAKE}", "unsat", "0"]
logics = ["QF_LIA"]
portfolio = false

[solvers.nra-only]
path = "{sys.executable}"
args = ["{FAKE}", "unsat", "0"]
logics = ["QF_NRA"]
""")
    synthesizer = Synthesizer()
    res, circuit, _ = synthesizer.synthesis(qasm_file=GHZ2, vectors="zero", solving="smt", solver="portfolio", mode="basic",
                                            output_qasm="out.qasm", solver_config=config)
    assert list(synthesizer.gen.solver.solvers) == ["yices2"]
    assert res
    assert circuit.gate_count() == 2


def test_environment_variable_selects_config(workdir, monkeypatch):
    monkeypatch.setenv(ENV_VARIABLE, write_config(workdir / "s.toml", f'[solvers.only]\npath = "{YICES}"\nlogics = ["QF_LIA"]\n'))
    with pytest.raises(SolverConfigError, match="Invalid solver: yices2; .* configures only"):
        synthesize("yices2")
    assert synthesize("only", mode="basic")[0]


def test_solver_without_the_logic(workdir):
    with pytest.raises(SolverConfigError, match="opensmt does not support QF_NRA"):
        synthesize("opensmt", representation="Classic")


def test_portfolio_without_a_solver_for_the_logic(workdir):
    config = write_config(workdir / "s.toml", f'[solvers.yices2]\npath = "{YICES}"\nlogics = ["QF_LIA"]\n')
    with pytest.raises(SolverConfigError, match="no portfolio solver supports QF_NRA"):
        synthesize("portfolio", config, representation="Classic")


@pytest.mark.parametrize("solver", ["yices2", "portfolio"])
def test_pysmt_solving(workdir, solver):
    # the pySMT backend registers the configured solvers as pySMT generic solvers
    res, circuit, _ = Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving="pysmt", solver=solver, mode="basic",
                                              output_qasm="out.qasm")
    assert res
    assert circuit.gate_count() == 2


def test_pysmt_solving_rejects_a_changed_solver(workdir):
    Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving="pysmt", solver="yices2", mode="basic")
    config = write_config(workdir / "s.toml", f'[solvers.yices2]\npath = "{YICES}"\nargs = ["-v", "0"]\nlogics = ["QF_LIA"]\n')
    with pytest.raises(SolverConfigError, match="pySMT already has a solver yices2"):
        Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving="pysmt", solver="yices2", mode="basic",
                                solver_config=config)


def test_pysmt_solving_rejects_unknown_solver(workdir):
    with pytest.raises(SolverConfigError, match="Invalid solver: yices"):
        Synthesizer().synthesis(qasm_file=GHZ2, vectors="zero", solving="pysmt", solver="yices", mode="basic")


def test_cli_reports_config_errors(workdir):
    result = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "milq"), "-s", "smt", "-a", "yices", GHZ2],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert f"milq: error: Invalid solver: yices; {DEFAULT_PATH} configures" in result.stderr


def test_cli_solver_config_option(workdir):
    config = write_config(workdir / "s.toml", f'[solvers.my-yices]\npath = "{YICES}"\nlogics = ["QF_LIA"]\n')
    result = subprocess.run([sys.executable, os.path.join(REPO_ROOT, "milq"), "-v", "zero", "-s", "smt", "-m", "basic",
                             "-a", "my-yices", "--solver-config", config, GHZ2], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "synthesis successful" in result.stdout
