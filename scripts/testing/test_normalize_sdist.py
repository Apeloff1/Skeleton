from __future__ import annotations

import gzip
import importlib.util
import io
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "normalize_sdist.py"
SPEC = importlib.util.spec_from_file_location("normalize_sdist", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
normalize_sdist = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(normalize_sdist)


def _write_archive(path: Path, *, tar_mtime: int, gzip_mtime: int) -> None:
    payload = b"deterministic\n"
    with path.open("wb") as raw:
        with gzip.GzipFile(filename=path.name, mode="wb", fileobj=raw, mtime=gzip_mtime) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                member = tarfile.TarInfo("skeleton-16.0.0/example.txt")
                member.size = len(payload)
                member.mtime = tar_mtime
                member.uid = 1000
                member.gid = 1000
                member.uname = "builder"
                member.gname = "builder"
                archive.addfile(member, io.BytesIO(payload))


def test_normalization_removes_tar_and_gzip_timestamp_variance(tmp_path: Path) -> None:
    left = tmp_path / "left.tar.gz"
    right = tmp_path / "right.tar.gz"
    _write_archive(left, tar_mtime=100, gzip_mtime=200)
    _write_archive(right, tar_mtime=300, gzip_mtime=400)

    epoch = 1_700_000_000
    normalize_sdist.normalize_sdist(left, source_date_epoch=epoch)
    normalize_sdist.normalize_sdist(right, source_date_epoch=epoch)

    assert left.read_bytes() == right.read_bytes()
    with tarfile.open(left, mode="r:gz") as archive:
        member = archive.getmember("skeleton-16.0.0/example.txt")
        assert member.mtime == epoch
        assert member.uid == 0
        assert member.gid == 0
        assert member.uname == ""
        assert member.gname == ""
        assert archive.extractfile(member).read() == b"deterministic\n"
