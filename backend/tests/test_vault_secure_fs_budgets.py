"""Enforce compressed output and snapshot size limits before writing to disk.

These tests intentionally use real directory descriptors, private files, and a
source that grows *after* the caller's initial size admission decision.
"""
from __future__ import annotations

from contextlib import contextmanager
import io
from pathlib import Path

import pytest

from core import vault_secure_fs as secure_fs


def test_atomic_output_budget_rejects_before_writing_and_preserves_destination(
    tmp_path: Path,
):
    with secure_fs.anchored_directory(tmp_path) as directory:
        assert secure_fs.atomic_write(
            directory, "shard", lambda output: output.write(b"prior"), max_bytes=5
        ) == 5
        with pytest.raises(secure_fs.VaultPathError, match="output exceeds"):
            secure_fs.atomic_write(
                directory, "shard", lambda output: output.write(b"new-too-long"),
                max_bytes=5,
            )
    assert (tmp_path / "shard").read_bytes() == b"prior"
    assert list(tmp_path.glob(".vault-part-*")) == []


def test_atomic_output_budget_counts_multiple_writes(tmp_path: Path):
    def write_two_chunks(output):
        assert output.write(b"abc") == 3
        output.write(b"def")

    with secure_fs.anchored_directory(tmp_path) as directory:
        with pytest.raises(secure_fs.VaultPathError, match="output exceeds"):
            secure_fs.atomic_write(directory, "shard", write_two_chunks, max_bytes=5)
        assert secure_fs.atomic_write(
            directory, "shard", write_two_chunks, max_bytes=6
        ) == 6
    assert (tmp_path / "shard").read_bytes() == b"abcdef"


class _GrowingSource:
    def __init__(self):
        self.parts = iter((b"abc", b"def", b""))

    def read(self, _count: int):
        return next(self.parts)


def test_bounded_snapshot_copy_refuses_growth_without_writing_excess():
    output = io.BytesIO()
    with pytest.raises(secure_fs.VaultPathError, match="backup exceeds"):
        secure_fs._copy_bounded(_GrowingSource(), output, max_bytes=4)
    assert output.getvalue() == b"abc"


def test_snapshot_of_growing_source_cleans_private_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "shard"
    target.write_bytes(b"prior")

    @contextmanager
    def growing_read(_fd, _name, *, max_bytes=None):
        assert max_bytes == 4
        yield _GrowingSource()

    monkeypatch.setattr(secure_fs, "read_regular", growing_read)
    with secure_fs.anchored_directory(tmp_path) as directory:
        with pytest.raises(secure_fs.VaultPathError, match="backup exceeds"):
            secure_fs.snapshot_regular(directory, "shard", max_bytes=4)

    assert target.read_bytes() == b"prior"
    assert list(tmp_path.glob(".vault-backup-*")) == []
    assert list(tmp_path.glob(".vault-part-*")) == []


@pytest.mark.parametrize("budget", [-1, True, 1.5])
def test_invalid_copy_budgets_rejected(budget):
    with pytest.raises(secure_fs.VaultPathError, match="invalid vault backup"):
        secure_fs._copy_bounded(io.BytesIO(b"abc"), io.BytesIO(), max_bytes=budget)


@pytest.mark.parametrize("budget", [-1, True, 1.5])
def test_invalid_output_budgets_rejected(tmp_path: Path, budget):
    with secure_fs.anchored_directory(tmp_path) as directory:
        with pytest.raises(secure_fs.VaultPathError, match="invalid vault output"):
            secure_fs.atomic_write(
                directory, "shard", lambda output: output.write(b"x"),
                max_bytes=budget,
            )
    assert not (tmp_path / "shard").exists()



def test_atomic_writelines_cannot_bypass_byte_budget(tmp_path: Path):
    with secure_fs.anchored_directory(tmp_path) as directory:
        with pytest.raises(secure_fs.VaultPathError, match="output exceeds"):
            secure_fs.atomic_write(
                directory,
                "shard",
                lambda output: output.writelines([b"abcd", b"efgh"]),
                max_bytes=7,
            )
        assert secure_fs.atomic_write(
            directory,
            "shard",
            lambda output: output.writelines([b"abcd", b"efgh"]),
            max_bytes=8,
        ) == 8
    assert (tmp_path / "shard").read_bytes() == b"abcdefgh"


@pytest.mark.parametrize("bypass", ["raw", "buffer", "detach"])
def test_atomic_sink_refuses_unmetered_file_interfaces(tmp_path: Path, bypass):
    def reject_unmetered(output):
        getattr(output, bypass)

    with secure_fs.anchored_directory(tmp_path) as directory:
        with pytest.raises(AttributeError):
            secure_fs.atomic_write(
                directory, "shard", reject_unmetered, max_bytes=1,
            )
    assert not (tmp_path / "shard").exists()



def test_failed_backup_publication_is_not_silently_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "shard"
    target.write_bytes(b"prior")
    original = secure_fs.atomic_write

    def missing_during_backup(fd, name, writer, **kwargs):
        if name.startswith(".vault-backup-"):
            raise FileNotFoundError("simulated backup publication failure")
        return original(fd, name, writer, **kwargs)

    monkeypatch.setattr(secure_fs, "atomic_write", missing_during_backup)
    with secure_fs.anchored_directory(tmp_path) as directory:
        with pytest.raises(FileNotFoundError, match="backup publication"):
            secure_fs.snapshot_regular(directory, "shard", max_bytes=8)
    assert target.read_bytes() == b"prior"
    assert not list(tmp_path.glob(".vault-backup-*"))
