"""Generation of the solver configuration from the installed solvers (configure-solvers)."""

import hashlib
import io
import os
import subprocess
import sys
import tarfile

import pytest

from conftest import REPO_ROOT
from solver_config import load_solver_config
from solver_detection import KNOWN_SOLVERS, check, detect, render

SOLVER = {solver.name: solver for solver in KNOWN_SOLVERS}
CONFIGURE = os.path.join(REPO_ROOT, "configure-solvers")


def fake_solver(directory, name, script="echo sat"):
    # an executable that stands in for a solver
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(f"#!/bin/sh\n{script}\n")
    path.chmod(0o755)
    return str(path)


def detected(detections):
    return {d.solver.name: d for d in detections}


def test_detect_looks_in_search_dirs_then_path(tmp_path):
    yices = fake_solver(tmp_path / "yices" / "bin", "yices-smt2")
    cvc5 = fake_solver(tmp_path / "path", "cvc5")
    found = detected(detect([str(tmp_path / "yices")], path=str(tmp_path / "path")))
    assert found["yices2"].path == yices  # DIR/bin
    assert found["cvc5"].path == cvc5
    assert found["opensmt"].path is None
    assert found["z3"].path is None


def test_detect_skips_solvers_that_do_not_work(tmp_path):
    broken = fake_solver(tmp_path / "search", "yices-smt2", "echo 'java: not found' >&2; exit 127")
    working = fake_solver(tmp_path / "path", "yices_smt2")  # the name in the SMT-COMP builds
    found = detected(detect([str(tmp_path / "search")], path=str(tmp_path / "path")))
    assert found["yices2"].path == working
    assert found["yices2"].rejected == ((broken, "exit code 127: java: not found"),)


def test_detect_finds_nothing(tmp_path):
    found = detected(detect(path=str(tmp_path)))
    assert all(found[name].path is None for name in ("yices2", "cvc5", "opensmt", "smtinterpol", "z3"))


@pytest.mark.parametrize("script, problem", [
    ("echo unsat", "exit code 0: unsat"),
    ("exit 3", "exit code 3, no output"),
    ("sleep 5", "no answer within 0.5 s"),
])
def test_check_reports_why_a_solver_does_not_work(tmp_path, script, problem):
    assert check(SOLVER["z3"], fake_solver(tmp_path, "z3", script), timeout=0.5) == problem


@pytest.mark.parametrize("script", ["echo sat", "echo success; echo success; echo sat", "echo 'delta-sat with delta = 0.001'"])
def test_check_accepts_sat(tmp_path, script):
    assert check(SOLVER["dreal"], fake_solver(tmp_path, "dreal", script)) is None


def test_check_passes_the_arguments_and_a_formula_of_the_first_logic(tmp_path):
    arguments = tmp_path / "arguments"
    solver = fake_solver(tmp_path, "dreal", f'echo "$@" > {arguments}; cat "$4" >> {arguments}; echo sat')
    assert check(SOLVER["dreal"], solver) is None
    text = arguments.read_text()
    assert text.startswith("--precision 1e-9 --produce-models ")
    assert "(set-logic QF_NRA)" in text


def test_render_round_trip(tmp_path):
    fake_solver(tmp_path / "path", "cvc5")
    fake_solver(tmp_path / "path", "smtinterpol")
    detections = detect(path=str(tmp_path / "path"))
    text = render(detections)
    (tmp_path / "solvers.toml").write_text(text)
    config = load_solver_config(str(tmp_path / "solvers.toml"))
    assert config == {d.solver.name: d.config() for d in detections if d.path}
    assert list(config) == ["cvc5", "smtinterpol"]
    assert config["cvc5"].command(incremental=True) == [str(tmp_path / "path" / "cvc5"), "--produce-models", "--incremental"]
    assert "# no QF_NRA: SMTInterpol" in text
    assert "# not found: yices2, opensmt, z3" in text


def configure(*args, path):
    # --download-dir: not the solvers the user downloaded
    return subprocess.run([sys.executable, CONFIGURE, "--download-dir", str(path / "downloads"), *args],
                          capture_output=True, text=True, env={**os.environ, "PATH": str(path)})


def test_configure_solvers_writes_the_config(tmp_path):
    cvc5 = fake_solver(tmp_path / "path", "cvc5")
    output = tmp_path / "solvers.toml"
    result = configure("-o", str(output), path=tmp_path / "path")
    assert result.returncode == 0, result.stderr
    assert f"cvc5: {cvc5}\n" in result.stderr
    assert "yices2: not found\n" in result.stderr
    assert list(load_solver_config(str(output))) == ["cvc5"]

    # an existing file is kept without --force
    result = configure("-o", str(output), path=tmp_path)
    assert result.returncode == 2
    assert "exists, use --force" in result.stderr
    assert list(load_solver_config(str(output))) == ["cvc5"]


def test_configure_solvers_to_stdout(tmp_path):
    fake_solver(tmp_path / "path", "z3")
    result = configure("-o", "-", "-s", str(tmp_path / "extra"), path=tmp_path / "path")
    assert result.returncode == 0, result.stderr
    assert "[solvers.z3]" in result.stdout


def test_configure_solvers_reports_broken_solvers(tmp_path):
    broken = fake_solver(tmp_path / "path", "opensmt", "exit 1")
    fake_solver(tmp_path / "path", "z3")
    result = configure("-o", "-", path=tmp_path / "path")
    assert f"opensmt: {broken} does not work (exit code 1, no output)\nopensmt: not found\n" in result.stderr


def test_configure_solvers_without_solvers(tmp_path):
    result = configure("-o", str(tmp_path / "solvers.toml"), path=tmp_path)
    assert result.returncode == 1
    assert "no SMT solver found" in result.stderr
    assert not (tmp_path / "solvers.toml").exists()


def test_configure_solvers_downloads(tmp_path, monkeypatch):
    # the releases of this platform replaced by a local archive, through a sitecustomize module
    archive = tmp_path / "cvc5.tar.bz2"
    with tarfile.open(archive, "w:bz2") as t:
        data = b"#!/bin/sh\necho sat\n"
        info = tarfile.TarInfo("cvc5/bin/cvc5")
        info.size, info.mode = len(data), 0o755
        t.addfile(info, io.BytesIO(data))
    sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(f"""
import sys
sys.path.insert(0, {os.path.join(REPO_ROOT, "src")!r})
import solver_download
release = solver_download.Release("cvc5", "1.0", {archive.as_uri()!r}, {sha256!r}, "cvc5")
solver_download.releases = lambda platform_name=None: (release,)
""")
    monkeypatch.setenv("PYTHONPATH", str(site))
    result = configure("-o", "-", "--download", path=tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"cvc5: {tmp_path}/downloads/bin/cvc5\n" in result.stderr
    assert f'path = "{tmp_path}/downloads/bin/cvc5"' in result.stdout

    result = configure("-o", "-", "--download", "yices2", path=tmp_path)
    assert result.returncode == 2
    assert "no download of yices2 for this platform (available: cvc5)" in result.stderr
