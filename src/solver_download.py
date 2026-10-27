"""
@file: solver_download.py
@brief: download of SMT solver release binaries (configure-solvers --download); the releases are listed
        with the known solvers in solver_detection.py
"""

import hashlib
import os
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

import solver_detection
from solver_detection import KnownSolver, Release

DEFAULT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "solvers"))


class DownloadError(Exception):
    """a solver could not be downloaded or unpacked"""


def platform_name() -> str:
    # the keys of KnownSolver.releases, e.g. linux-x86_64 or darwin-arm64
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{sys.platform}-{machine}"


def downloadable(platform_key: str | None = None) -> dict[str, tuple[KnownSolver, Release]]:
    # the known solvers that have a release for the platform (default: this one), by name
    platform_key = platform_key or platform_name()
    return {solver.name: (solver, solver.releases[platform_key])
            for solver in solver_detection.KNOWN_SOLVERS if platform_key in solver.releases}


def bin_dir(directory: str = DEFAULT_DIR) -> str:
    # where the downloaded executables are linked; configure-solvers looks there
    return os.path.join(directory, "bin")


def _unpack(archive: str, destination: str) -> None:
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            z.extractall(destination)
    else:
        with tarfile.open(archive) as t:
            if hasattr(tarfile, "data_filter"):  # Python 3.11.4+
                t.extractall(destination, filter="data")
            else:
                t.extractall(destination)


def _find(directory: str, name: str) -> str | None:
    for root, _, files in sorted(os.walk(directory)):
        if name in files:
            return os.path.join(root, name)
    return None


def download(solver: KnownSolver, release: Release, directory: str = DEFAULT_DIR, force: bool = False) -> str:
    # downloads and unpacks the release into directory/NAME-VERSION, links its executable into directory/bin,
    # and returns the link; a release that is already there is kept unless force
    executable_name = solver.executables[0]
    target = os.path.join(directory, f"{solver.name}-{release.version}")
    link = os.path.join(bin_dir(directory), executable_name)
    if os.path.isdir(target) and not force and os.path.realpath(link).startswith(os.path.realpath(target) + os.sep):
        return link
    os.makedirs(directory, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        archive = os.path.join(tmp, os.path.basename(release.url))
        try:
            with urllib.request.urlopen(release.url, timeout=60) as response, open(archive, "wb") as f:
                shutil.copyfileobj(response, f)
        except OSError as e:
            raise DownloadError(f"{release.url}: {e}") from None
        with open(archive, "rb") as f:
            digest = hashlib.file_digest(f, "sha256").hexdigest()
        if digest != release.sha256:
            raise DownloadError(f"{release.url}: sha256 {digest}, expected {release.sha256}")
        unpacked = os.path.join(tmp, "unpacked")
        try:
            _unpack(archive, unpacked)
        except (tarfile.TarError, zipfile.BadZipFile, OSError) as e:
            raise DownloadError(f"{release.url}: cannot unpack: {e}") from None
        if _find(unpacked, executable_name) is None:
            raise DownloadError(f"{release.url}: no {executable_name} in the archive")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(unpacked, target)
    executable = _find(target, executable_name)
    os.chmod(executable, os.stat(executable).st_mode | 0o111)  # zip files keep no permissions
    os.makedirs(bin_dir(directory), exist_ok=True)
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(os.path.relpath(executable, bin_dir(directory)), link)
    return link
