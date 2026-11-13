from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gzip
import json
from pathlib import Path
import threading
import zipfile

import pytest
import zstandard as zstd

from core import build_vault as vault


@pytest.fixture(autouse=True)
def isolated_vault(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, "BUILDS_ROOT", tmp_path)
    monkeypatch.setattr(vault, "_zctx", lambda: zstd.ZstdCompressor(level=1, threads=0))
    return tmp_path


def test_overwritten_paths_and_pending_paths_count_once():
    vault.append_files("build", {"old.txt": "old", "other.txt": "other"})
    result = vault.append_files("build", {"old.txt": "new"})

    assert result["file_count"] == vault.get_file_count("build") == 2
    assert set(vault.get_file_paths("build")) == {"old.txt", "other.txt"}
    assert vault.get_file_count("build", pending_paths=("old.txt", "new.txt", "new.txt")) == 3
    assert vault.get_file("build", "old.txt") == "new"
    assert vault.list_file_paths("build", limit=1) == [
        {"path": "other.txt", "size": 5, "lines": 1, "type": "txt"}
    ]
    assert dict(vault.iter_files("build")) == {"old.txt": "new", "other.txt": "other"}


def test_append_to_swept_manifest_does_not_reuse_stale_metadata(isolated_vault):
    vault.append_files("build", {"first.txt": "first"})
    manifest = isolated_vault / "build" / "manifest.json"
    swept = manifest.with_suffix(".json.gz")
    swept.write_bytes(gzip.compress(manifest.read_bytes()))
    manifest.unlink()

    vault.append_files("build", {"second.txt": "second"})
    assert vault.get_file_count("build") == 2
    vault.append_files("build", {"third.txt": "third"})

    assert vault.get_file_count("build") == 3
    assert dict(vault.iter_files("build")) == {
        "first.txt": "first", "second.txt": "second", "third.txt": "third",
    }
    assert len(list(manifest.parent.glob("shard_*.jsonl.zst"))) == 3


def test_failed_shard_attempt_cannot_publish_its_valid_prefix(isolated_vault):
    vault.append_files("build", {"retained.txt": "retained"})
    directory = isolated_vault / "build"
    before = {path.name for path in directory.iterdir()}

    with pytest.raises(UnicodeEncodeError):
        vault.append_files("build", {"prefix.txt": "prefix", "invalid.txt": "\ud800"})

    assert {path.name for path in directory.iterdir()} == before
    assert vault.get_file_count("build") == 1
    assert vault.get_file("build", "prefix.txt") is None
    assert vault.get_file("build", "retained.txt") == "retained"


def test_manifest_failure_preserves_complete_source_and_other_attempts(isolated_vault, monkeypatch):
    vault.append_files("build", {"first.txt": "first"})
    directory = isolated_vault / "build"
    unrelated = directory / ".manifest-other-attempt.tmp"
    unrelated.write_bytes(b"another attempt")
    original_replace = Path.replace

    def fail_manifest_publish(path, target):
        if path.name.startswith(".manifest-"):
            raise OSError("publication interrupted")
        return original_replace(path, target)

    with monkeypatch.context() as failure:
        failure.setattr(Path, "replace", fail_manifest_publish)
        with pytest.raises(OSError, match="publication interrupted"):
            vault.append_files("build", {"interrupted.txt": "preserved source"})

    assert unrelated.read_bytes() == b"another attempt"
    assert sorted(path.name for path in directory.glob("*.tmp")) == [unrelated.name]
    assert (directory / "shard_00001.jsonl.zst").exists()
    vault.append_files("build", {"third.txt": "third"})
    manifest = json.loads((directory / "manifest.json").read_text())
    assert [shard["idx"] for shard in manifest["shards"]] == [0, 2]
    assert (directory / "shard_00001.jsonl.zst").exists()

    (directory / "manifest.json").write_text("interrupted manifest")
    assert vault.get_file_count("build") == 3
    assert vault.get_file("build", "interrupted.txt") == "preserved source"


def test_missing_manifest_recovers_only_complete_published_shards(isolated_vault):
    vault.append_files("build", {"retained.txt": "retained"})
    vault.append_files("build", {"prefix.txt": "prefix", "tail.txt": "tail" * 100})
    directory = isolated_vault / "build"
    broken = directory / "shard_00001.jsonl.zst"
    broken.write_bytes(broken.read_bytes()[:-1])
    (directory / ".shard-another-attempt.tmp").write_bytes(b"not a published shard")
    (directory / "manifest.json").unlink()

    assert vault.get_file_count("build") == 1
    assert vault.get_file("build", "retained.txt") == "retained"
    assert vault.get_file("build", "prefix.txt") is None
    assert broken.exists()


@pytest.mark.parametrize("indexed", [True, False])
def test_file_lookup_validates_footer_before_returning_match(isolated_vault, indexed):
    vault.append_files("build", {"match.txt": "matched content", "tail.txt": "tail" * 100})
    directory = isolated_vault / "build"
    manifest_path = directory / "manifest.json"
    if not indexed:
        manifest = json.loads(manifest_path.read_text())
        manifest["path_index"].pop("match.txt")
        manifest_path.write_text(json.dumps(manifest))
    shard = directory / "shard_00000.jsonl.zst"
    shard.write_bytes(shard.read_bytes()[:-1])

    with pytest.raises((ValueError, zstd.ZstdError)):
        vault.get_file("build", "match.txt")
    with pytest.raises((ValueError, zstd.ZstdError)):
        vault.list_file_paths("build", limit=1)


def test_corrupt_source_cannot_replace_last_valid_zip(isolated_vault):
    vault.append_files("build", {"match.txt": "matched", "tail.txt": "tail" * 100})
    published = vault.package_zip("build")
    previous_bytes = published.read_bytes()
    shard = isolated_vault / "build" / "shard_00000.jsonl.zst"
    shard.write_bytes(shard.read_bytes()[:-1])

    with pytest.raises((ValueError, zstd.ZstdError)):
        vault.package_zip("build")

    assert published.read_bytes() == previous_bytes
    assert not list(published.parent.glob(".package-*.tmp"))


def test_repackaging_keeps_open_previous_inode_complete():
    vault.append_files("build", {"first.txt": "first"})
    published = vault.package_zip("build")
    previous_bytes = published.read_bytes()
    with published.open("rb") as reader:
        vault.append_files("build", {"second.txt": "second"})
        assert vault.package_zip("build") == published
        assert reader.read() == previous_bytes
    with zipfile.ZipFile(published) as archive:
        assert set(archive.namelist()) == {"first.txt", "second.txt"}


def test_read_repair_waits_for_complete_append(isolated_vault, monkeypatch):
    writing = threading.Event()
    release = threading.Event()
    reading = threading.Event()
    returned = threading.Event()

    class BlockingWriter:
        def __init__(self, writer):
            self.writer = writer

        def __enter__(self):
            self.writer.__enter__()
            return self

        def __exit__(self, *args):
            return self.writer.__exit__(*args)

        def write(self, data):
            result = self.writer.write(data)
            writing.set()
            assert release.wait(5), "test did not release blocked shard writer"
            return result

    class BlockingCompressor:
        def stream_writer(self, handle, **kwargs):
            return BlockingWriter(zstd.ZstdCompressor(level=1, threads=0).stream_writer(handle, **kwargs))

    monkeypatch.setattr(vault, "_zctx", BlockingCompressor)

    def read_count():
        reading.set()
        try:
            return vault.get_file_count("build")
        finally:
            returned.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(vault.append_files, "build", {"file.txt": "complete"})
        try:
            assert writing.wait(5)
            assert not list((isolated_vault / "build").glob("shard_*.jsonl.zst"))
            reader = pool.submit(read_count)
            assert reading.wait(5)
            assert not returned.wait(0.05)
        finally:
            release.set()
        assert writer.result(timeout=5)["file_count"] == 1
        assert reader.result(timeout=5) == 1


def test_parallel_build_reads_have_independent_decoder_state():
    vault.append_files("first", {"file.txt": "first" * 1000})
    vault.append_files("second", {"file.txt": "second" * 1000})
    barrier = threading.Barrier(2)

    def read(build):
        barrier.wait(timeout=5)
        return vault.get_file(build, "file.txt")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(read, "first")
        second = pool.submit(read, "second")
        assert first.result(timeout=5) == "first" * 1000
        assert second.result(timeout=5) == "second" * 1000
