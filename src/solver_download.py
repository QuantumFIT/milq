"""
@file: solver_download.py
@brief: download of SMT solver release binaries (configure-solvers --download)
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
from dataclasses import dataclass

DEFAULT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "solvers"))


class DownloadError(Exception):
    """a solver could not be downloaded or unpacked"""


@dataclass(frozen=True)
class Release:
    solver: str  # name in KNOWN_SOLVERS
    version: str
    url: str
    sha256: str
    executable: str  # name of the executable in the archive


def _platform() -> str:
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{sys.platform}-{machine}"


_YICES = "https://github.com/SRI-CSL/yices2/releases/download/yices-2.7.0/"
_CVC5 = "https://github.com/cvc5/cvc5/releases/download/cvc5-1.3.1/"
_OPENSMT = "https://github.com/usi-verification-and-security/opensmt/releases/download/v2.9.2/"

# release binaries by platform, with the sha256 that GitHub reports for them
RELEASES = {
    "linux-x86_64": (
        Release("yices2", "2.7.0", _YICES + "yices-2.7.0-x86_64-pc-linux-gnu-static-gmp.tar.gz",
                "49566b6f817692820538df78fe406878400d79810631c9372b2495bc81d3e00a", "yices-smt2"),
        Release("cvc5", "1.3.1", _CVC5 + "cvc5-Linux-x86_64-static.zip",
                "1a1cda20d2df4938fa4944a69f33ddc9172e319ece0eed0aa09c4d7abede3ed1", "cvc5"),
        Release("opensmt", "2.9.2", _OPENSMT + "opensmt-x64-linux-static.tar.bz2",
                "be4767bf5d6c08bc7f4f49ae1480f2ae2ac8f38a277d0ec39d56badd974b84bd", "opensmt"),
    ),
    "linux-arm64": (
        Release("cvc5", "1.3.1", _CVC5 + "cvc5-Linux-arm64-static.zip",
                "fe2b661834a82fd8830f7a757c340f0e20041fa41e19b038fa02ace0eaf1c6f2", "cvc5"),
    ),
    "darwin-arm64": (
        Release("yices2", "2.7.0", _YICES + "yices-2.7.0-arm-apple-darwin24.5.0-static-gmp.tar.gz",
                "5682fedf13add7818e8d05796b9133e67844fce2bb72fd1ecc75dcb73167c7ac", "yices-smt2"),
        Release("cvc5", "1.3.1", _CVC5 + "cvc5-macOS-arm64-static.zip",
                "a0e7f5b03b1bc4284fbfff7cdfb08c704801701cf7ece83a13f8a505e7581215", "cvc5"),
        Release("opensmt", "2.9.2", _OPENSMT + "opensmt-arm-osx.tar.bz2",
                "6c8605db38e0f62ea040cffc670e65bd5f47e4fb65ecd65c6aaf4170cd19c51c", "opensmt"),
    ),
    "darwin-x86_64": (
        Release("yices2", "2.7.0", _YICES + "yices-2.7.0-x86_64-apple-darwin21.6.0-static-gmp.tar.gz",
                "dff40838ae5674abed2c08c383d702c1358ad64627c15799d2a15e67d1b4495a", "yices-smt2"),
        Release("cvc5", "1.3.1", _CVC5 + "cvc5-macOS-x86_64-static.zip",
                "e7fe4af9491bd7c0db7591c0a483775735bd1a98b23933fd337a73ae39c10ff9", "cvc5"),
        Release("opensmt", "2.9.2", _OPENSMT + "opensmt-x64-osx.tar.bz2",
                "b376e0339793f1ed5c546155f865de10fb39d1346d1788b57c80dfb538375ada", "opensmt"),
    ),
}


def releases(platform_name: str | None = None) -> tuple[Release, ...]:
    return RELEASES.get(platform_name or _platform(), ())


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


def download(release: Release, directory: str = DEFAULT_DIR, force: bool = False) -> str:
    # downloads and unpacks the release into directory/NAME-VERSION, links its executable into directory/bin,
    # and returns the link; a release that is already there is kept unless force
    target = os.path.join(directory, f"{release.solver}-{release.version}")
    link = os.path.join(bin_dir(directory), release.executable)
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
        if _find(unpacked, release.executable) is None:
            raise DownloadError(f"{release.url}: no {release.executable} in the archive")
        shutil.rmtree(target, ignore_errors=True)
        os.replace(unpacked, target)
    executable = _find(target, release.executable)
    os.chmod(executable, os.stat(executable).st_mode | 0o111)  # zip files keep no permissions
    os.makedirs(bin_dir(directory), exist_ok=True)
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(os.path.relpath(executable, bin_dir(directory)), link)
    return link
