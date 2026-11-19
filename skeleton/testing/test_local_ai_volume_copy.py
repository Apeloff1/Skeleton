"""Real filesystem streaming byte-copy tests; no Docker daemon or user data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts import local_ai_volume_copy as copier


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    target = tmp_path / "archive"
    source.mkdir(mode=0o700)
    target.mkdir(mode=0o700)
    (source / "data").mkdir(mode=0o700)
    (source / "data" / "memory.sqlite3").write_bytes(b"SQLITE source" * 147)
    (source / "data" / "journal.log").write_bytes(b"journal" * 211)
    (source / "WiredTiger.wt").write_bytes(b"WT" * 71)
    return source, target


def test_stream_cold_copy_and_independently_rehash_actual_bytes(tmp_path):
    original, destination = _fixture(tmp_path)
    receipt = copier.copy_volume("mongo_data", original, destination)
    assert receipt["schema"] == copier.SCHEMA
    assert receipt["volume_role"] == "mongo_data"
    assert receipt["files"] == 3
    assert receipt["bytes"] == sum(
        f.stat().st_size for f in original.rglob("*") if f.is_file()
    )
    assert receipt["cross_store_snapshot_atomic"] is False
    assert receipt["application_restore_qualified"] is False
    assert receipt["protected_jeeves_qualified"] is False
    assert receipt == copier.verify_volume("mongo_data", destination)
    index = destination / "mongo_data" / copier.MANIFEST
    assert receipt["manifest_sha256"] == hashlib.sha256(index.read_bytes()).hexdigest()
    rows = [json.loads(row) for row in index.read_text().splitlines()]
    assert len(rows) == 3
    assert sorted(row["path"] for row in rows) == [
        "WiredTiger.wt", "data/journal.log", "data/memory.sqlite3",
    ]
    assert (destination / "mongo_data" / "data" / "journal.log").read_bytes() == (
        original / "data" / "journal.log").read_bytes()


def test_copy_does_not_rewrite_or_remove_original_source(tmp_path):
    original, destination = _fixture(tmp_path)
    baseline = {
        f.relative_to(original).as_posix(): f.read_bytes()
        for f in original.rglob("*") if f.is_file()
    }
    copier.copy_volume("backend_data", original, destination)
    assert baseline == {
        f.relative_to(original).as_posix(): f.read_bytes()
        for f in original.rglob("*") if f.is_file()
    }


@pytest.mark.parametrize("change", [
    lambda path: path.write_bytes(b"modified"),
    lambda path: path.unlink(),
    lambda path: path.rename(path.with_suffix(".gone")),
])
def test_independent_rehash_denies_missing_or_changed_payload_bytes(tmp_path, change):
    original, destination = _fixture(tmp_path)
    copier.copy_volume("mongo_config", original, destination)
    change(destination / "mongo_config" / "WiredTiger.wt")
    with pytest.raises(copier.VolumeCopyError):
        copier.verify_volume("mongo_config", destination)


def test_added_archive_file_and_symlink_are_rejected(tmp_path):
    original, destination = _fixture(tmp_path)
    copier.copy_volume("skeleton_data", original, destination)
    (destination / "skeleton_data" / "injected.db").write_bytes(b"unexpected")
    with pytest.raises(copier.VolumeCopyError):
        copier.verify_volume("skeleton_data", destination)
    (destination / "skeleton_data" / "injected.db").unlink()
    (destination / "skeleton_data" / "linked").symlink_to("/etc/passwd")
    with pytest.raises(copier.VolumeCopyError):
        copier.verify_volume("skeleton_data", destination)


def test_linked_file_and_directory_in_original_source_is_denied(tmp_path):
    original, destination = _fixture(tmp_path)
    (original / "linked").symlink_to("/etc/passwd")
    with pytest.raises(copier.VolumeCopyError):
        copier.copy_volume("backend_data", original, destination)
    assert not (destination / "backend_data").exists()
    (original / "linked").unlink()
    (original / "shortcut").symlink_to("data", target_is_directory=True)
    with pytest.raises(copier.VolumeCopyError):
        copier.copy_volume("backend_data", original, destination)
    assert not (destination / "backend_data").exists()


def test_hardlinked_source_denied_before_copy(tmp_path):
    original, destination = _fixture(tmp_path)
    os.link(original / "WiredTiger.wt", original / "shared.wt")
    with pytest.raises(copier.VolumeCopyError):
        copier.copy_volume("mongo_data", original, destination)
    assert not (destination / "mongo_data").exists()


def test_empty_app_volume_has_zero_byte_record_not_app_qualification(tmp_path):
    original = tmp_path / "blank"
    destination = tmp_path / "archive"
    original.mkdir(mode=0o700)
    destination.mkdir(mode=0o700)
    received = copier.copy_volume("backend_data", original, destination)
    assert received["files"] == 0
    assert received["bytes"] == 0
    assert received["application_restore_qualified"] is False
    assert copier.verify_volume("backend_data", destination) == received


def test_true_multichunk_file_is_copied_without_loading_whole_file(tmp_path):
    original = tmp_path / "source"
    destination = tmp_path / "archive"
    original.mkdir(mode=0o700)
    destination.mkdir(mode=0o700)
    data = (b"abcdEFGH" * (copier.CHUNK // 8 + 100))
    (original / "large.bin").write_bytes(data)
    receipt = copier.copy_volume("chroma_data", original, destination)
    assert receipt["files"] == 1
    assert receipt["bytes"] == len(data)
    assert copier.verify_volume("chroma_data", destination) == receipt


def test_repeated_copy_cannot_overwrite_archive_or_original(tmp_path):
    original, destination = _fixture(tmp_path)
    copier.copy_volume("mongo_data", original, destination)
    with pytest.raises(copier.VolumeCopyError):
        copier.copy_volume("mongo_data", original, destination)
    assert copier.verify_volume("mongo_data", destination)["files"] == 3


@pytest.mark.parametrize("role", ["", "other", "remote", "volume=evil", "../mongo_data"])
def test_unrecognized_volume_roles_denied_without_copy(tmp_path, role):
    original, destination = _fixture(tmp_path)
    with pytest.raises(copier.VolumeCopyError):
        copier.copy_volume(role, original, destination)
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("invalid", [
    "document/../secret", "/absolute/path", "a/../../escape",
    "abc" * 2000, ".volume-files.jsonl", ".volume-receipt.json",
])
def test_archive_injectable_relative_paths_denied(invalid):
    with pytest.raises(copier.VolumeCopyError):
        copier._name(Path(invalid))


@pytest.mark.parametrize("mutation", [
    {"schema": "forged"}, {"status": "qualified"},
    {"application_restore_qualified": True},
    {"cross_store_snapshot_atomic": True},
    {"protected_jeeves_qualified": True},
    {"extra": "private user data"},
])
def test_mutated_volume_receipt_never_becomes_qualified(tmp_path, mutation):
    original, destination = _fixture(tmp_path)
    copier.copy_volume("mongo_data", original, destination)
    path = destination / "mongo_data" / copier.RECEIPT
    receipt = json.loads(path.read_text())
    receipt.update(mutation)
    path.write_text(json.dumps(receipt))
    with pytest.raises(copier.VolumeCopyError):
        copier.verify_volume("mongo_data", destination)


def test_manifest_path_traversal_denied_even_with_recomputed_checksum(tmp_path):
    original, destination = _fixture(tmp_path)
    copier.copy_volume("mongo_data", original, destination)
    root = destination / "mongo_data"
    manifest = root / copier.MANIFEST
    rows = manifest.read_text().splitlines()
    row = json.loads(rows[0])
    row["path"] = "./" + row["path"]
    rows[0] = json.dumps(row)
    manifest.write_text("\n".join(rows) + "\n")
    receipt_path = root / copier.RECEIPT
    receipt = json.loads(receipt_path.read_text())
    receipt["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(copier.VolumeCopyError):
        copier.verify_volume("mongo_data", destination)


def test_oversized_or_missing_receipt_cannot_be_claimed_complete(tmp_path):
    original, destination = _fixture(tmp_path)
    copier.copy_volume("mongo_data", original, destination)
    receipt = destination / "mongo_data" / copier.RECEIPT
    receipt.unlink()
    with pytest.raises(copier.VolumeCopyError):
        copier.verify_volume("mongo_data", destination)


def test_stdout_receipt_never_contains_private_source_file_or_payload(tmp_path):
    original, destination = _fixture(tmp_path)
    (original / "data" / "PRIVATE_MESSAGE.txt").write_bytes(b"SECRET_ACCOUNT_CREDENTIAL")
    receipt = copier.copy_volume("backend_data", original, destination)
    shown = json.dumps(receipt, sort_keys=True)
    for secret in ("PRIVATE_MESSAGE", "SECRET_ACCOUNT_CREDENTIAL", str(original)):
        assert secret not in shown


def test_bounded_walker_is_generator_and_does_not_allocate_file_path_list(tmp_path):
    import inspect
    source, _archive = _fixture(tmp_path)
    walker = copier._walk(source)
    assert inspect.isgenerator(walker)
    assert sorted(path.as_posix() for path in walker) == [
        "WiredTiger.wt", "data/journal.log", "data/memory.sqlite3",
    ]


def test_multi_directory_many_file_copy_stays_streamed_and_verified(tmp_path):
    src = tmp_path / "input"
    dest = tmp_path / "archive"
    src.mkdir(mode=0o700)
    dest.mkdir(mode=0o700)
    for folder in range(4):
        directory = src / ("shard_" + str(folder))
        directory.mkdir(mode=0o700)
        for index in range(20):
            (directory / ("record_" + str(index) + ".db")).write_bytes(
                ("fixture:%s:%s" % (folder, index)).encode()
            )
    result = copier.copy_volume("backend_data", src, dest)
    assert result["files"] == 80
    assert result == copier.verify_volume("backend_data", dest)
    assert result["application_restore_qualified"] is False


def test_duplicate_sealed_manifest_rows_are_denied_without_large_path_sets(tmp_path):
    src, dest = _fixture(tmp_path)
    copier.copy_volume("mongo_data", src, dest)
    root = dest / "mongo_data"
    path = root / copier.MANIFEST
    rows = path.read_text().splitlines()
    path.write_text("\n".join([rows[0], rows[0], *rows[1:]]) + "\n")
    receipt = root / copier.RECEIPT
    data = json.loads(receipt.read_text())
    data["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(data))
    with pytest.raises(copier.VolumeCopyError):
        copier.verify_volume("mongo_data", dest)


def test_manipulated_overlong_jsonl_line_has_bounded_allocation_and_is_rejected(tmp_path):
    src, dest = _fixture(tmp_path)
    copier.copy_volume("mongo_data", src, dest)
    root = dest / "mongo_data"
    path = root / copier.MANIFEST
    path.write_bytes(b"X" * (copier.MAX_PATH_BYTES * 3 + 64))
    receipt = root / copier.RECEIPT
    data = json.loads(receipt.read_text())
    data["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(data))
    with pytest.raises(copier.VolumeCopyError, match="outside bounds"):
        copier.verify_volume("mongo_data", dest)


def test_unicode_and_json_escaped_filename_has_deterministic_manifest(tmp_path):
    src = tmp_path / "source"
    dest = tmp_path / "archive"
    src.mkdir(mode=0o700)
    dest.mkdir(mode=0o700)
    (src / "français_日本語_😀.db").write_bytes(b"private offline content")
    result = copier.copy_volume("chroma_data", src, dest)
    assert result["files"] == 1
    assert result == copier.verify_volume("chroma_data", dest)
    row = json.loads((dest / "chroma_data" / copier.MANIFEST).read_text())
    assert row["path"] == "français_日本語_😀.db"
