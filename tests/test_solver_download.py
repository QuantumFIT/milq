"""Download of solver release binaries (configure-solvers --download), from local archives."""

import hashlib
import io
import os
import tarfile
import zipfile

import pytest

from solver_detection import KNOWN_SOLVERS, KnownSolver, Release
from solver_download import DownloadError, bin_dir, download, downloadable

SOLVER = "#!/bin/sh\necho sat\n"


def tar_archive(path, members):
    with tarfile.open(path, "w:bz2") as t:
        for name, text in members.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            t.addfile(info, io.BytesIO(data))
    return path


def zip_archive(path, members):
    with zipfile.ZipFile(path, "w") as z:  # without permissions, like the cvc5 release zips
        for name, text in members.items():
            z.writestr(name, text)
    return path


CVC5 = KnownSolver("cvc5", ("cvc5",), ("QF_LIA",))


def release(archive, sha256=None):
    return Release("1.0", archive.as_uri(), sha256 or hashlib.sha256(archive.read_bytes()).hexdigest())


@pytest.mark.parametrize("archive", [tar_archive, zip_archive])
def test_download_links_the_executable(tmp_path, archive):
    path = archive(tmp_path / "cvc5.archive", {"cvc5-Linux/bin/cvc5": SOLVER, "cvc5-Linux/README": "readme"})
    link = download(CVC5, release(path), str(tmp_path / "solvers"))
    assert link == os.path.join(bin_dir(str(tmp_path / "solvers")), "cvc5")
    assert os.path.realpath(link) == str(tmp_path / "solvers" / "cvc5-1.0" / "cvc5-Linux" / "bin" / "cvc5")
    assert os.access(link, os.X_OK)
    assert not os.path.isabs(os.readlink(link))  # the directory can be moved


def test_download_keeps_an_existing_download(tmp_path):
    path = tar_archive(tmp_path / "cvc5.tar.bz2", {"bin/cvc5": SOLVER})
    solvers = str(tmp_path / "solvers")
    first = release(path)
    download(CVC5, first, solvers)
    path.unlink()  # a second download would fail
    assert download(CVC5, first, solvers) == os.path.join(bin_dir(solvers), "cvc5")
    with pytest.raises(DownloadError):
        download(CVC5, first, solvers, force=True)


def test_download_checks_the_sha256(tmp_path):
    path = tar_archive(tmp_path / "cvc5.tar.bz2", {"bin/cvc5": SOLVER})
    with pytest.raises(DownloadError, match="sha256 .*, expected 0000"):
        download(CVC5, release(path, sha256="0000"), str(tmp_path / "solvers"))
    assert not (tmp_path / "solvers" / "cvc5-1.0").exists()
    assert not (tmp_path / "solvers" / "bin").exists()


def test_download_needs_the_executable(tmp_path):
    path = tar_archive(tmp_path / "cvc5.tar.bz2", {"bin/other": SOLVER})
    with pytest.raises(DownloadError, match="no cvc5 in the archive"):
        download(CVC5, release(path), str(tmp_path / "solvers"))


def test_download_reports_unreachable_urls(tmp_path):
    with pytest.raises(DownloadError, match="missing.zip"):
        download(CVC5, Release("1.0", (tmp_path / "missing.zip").as_uri(), "0"), str(tmp_path / "solvers"))


def test_download_rejects_paths_outside_the_archive(tmp_path):
    if not hasattr(tarfile, "data_filter"):
        pytest.skip("tarfile filters need Python 3.11.4")
    path = tar_archive(tmp_path / "cvc5.tar.bz2", {"../evil": "x", "bin/cvc5": SOLVER})
    with pytest.raises(DownloadError, match="cannot unpack"):
        download(CVC5, release(path), str(tmp_path / "solvers"))
    assert not (tmp_path / "evil").exists()


def test_releases_by_platform():
    assert list(downloadable("linux-x86_64")) == ["yices2", "cvc5", "opensmt"]
    assert list(downloadable("linux-arm64")) == ["cvc5"]
    assert downloadable("sunos-sparc") == {}
    for solver in KNOWN_SOLVERS:
        for r in solver.releases.values():
            assert r.url.startswith("https://github.com/") and len(r.sha256) == 64
            assert r.version in r.url
