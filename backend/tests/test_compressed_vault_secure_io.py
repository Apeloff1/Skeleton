"""Focused security and correctness tests for compressed-vault descriptor custody."""
from __future__ import annotations

from contextlib import nullcontext
import os
import json
from pathlib import Path

import pytest

from core import compressed_vault as storage
from core.vault_secure_fs import VaultPathError


class PassThroughCodec:
    """Exercise actual secure filesystem and JSONL logic without zstd/network."""
    def stream_writer(self, handle):
        return nullcontext(handle)

    def stream_reader(self, handle):
        return nullcontext(handle)


@pytest.fixture
def isolated_storage(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(storage, "VAULT_ROOT", tmp_path / "vault")
    monkeypatch.setattr(storage, "SCRATCH_ROOT", tmp_path / "scratch")
    monkeypatch.setattr(storage, "_MANIFEST_FILE", tmp_path / "vault" / "_manifest.json")
    monkeypatch.setattr(storage, "_STORAGE_READY", False)
    monkeypatch.setattr(storage, "_STORAGE_IDENTITY", {})
    monkeypatch.setattr(storage, "_MANIFEST", {})
    monkeypatch.setattr(storage, "_CACHE", {})
    monkeypatch.setattr(storage, "_CACHE_SIZE_EST", {})
    monkeypatch.setattr(storage, "_COMPRESSOR", PassThroughCodec())
    monkeypatch.setattr(storage, "_DECOMPRESSOR", PassThroughCodec())
    return storage


def test_roundtrip_pagination_and_restart_safe_manifest(isolated_storage):
    vault = isolated_storage
    rows = [{"i": index} for index in range(6)]
    entry = vault.write_shard("safe", rows, domain="testing")
    assert entry["rows"] == 6
    assert vault.read_shard("safe", limit=2, offset=2) == rows[2:4]
    assert list(vault.iter_shard("safe")) == rows
    assert vault.get_shard_entry("safe")["name"] == "safe"
    vault._MANIFEST = {}
    vault._load_manifest()
    assert vault.read_shard("safe", limit=1, offset=5) == [{"i": 5}]


def test_failed_compression_never_truncates_an_existing_shard(isolated_storage):
    vault = isolated_storage
    vault.write_shard("stable", [{"value": "before"}], domain="testing")
    target = vault.VAULT_ROOT / "stable.jsonl.zst"
    original = target.read_bytes()

    def interrupted():
        yield {"value": "partial"}
        raise RuntimeError("generator interrupted after first row")

    with pytest.raises(RuntimeError, match="interrupted"):
        vault.write_shard("stable", interrupted(), domain="testing")
    assert target.read_bytes() == original
    assert vault.read_shard("stable") == [{"value": "before"}]
    assert not list(vault.VAULT_ROOT.glob(".vault-part-*"))


def test_symlink_or_hardlink_shard_is_rejected_without_following_it(isolated_storage, tmp_path):
    vault = isolated_storage
    vault.write_shard("safe", [{"value": 1}], domain="testing")
    target = vault.VAULT_ROOT / "safe.jsonl.zst"
    outside = tmp_path / "outside"
    outside.write_bytes(b'{"value":9}\n')
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises((VaultPathError, OSError)):
        vault.read_shard("safe")
    with pytest.raises((VaultPathError, OSError)):
        vault.write_shard("safe", [{"value": 2}], domain="testing")
    assert outside.read_bytes() == b'{"value":9}\n'

    target.unlink()
    os.link(outside, target)
    with pytest.raises(VaultPathError, match="private regular"):
        vault.read_shard("safe")
    assert outside.read_bytes() == b'{"value":9}\n'


def test_replacing_root_with_symlink_or_unrelated_directory_is_rejected(isolated_storage, tmp_path):
    vault = isolated_storage
    vault.write_shard("safe", [{"value": 1}], domain="testing")
    original_root = vault.VAULT_ROOT
    original_root.rename(tmp_path / "original")
    original_root.mkdir()
    with pytest.raises(VaultPathError, match="identity changed"):
        vault.read_shard("safe")
    original_root.rmdir()
    original_root.symlink_to(tmp_path / "original", target_is_directory=True)
    with pytest.raises((VaultPathError, OSError)):
        vault.read_shard("safe")


def test_corrupt_jsonl_and_duplicate_manifest_keys_fail_closed(isolated_storage):
    vault = isolated_storage
    vault.write_shard("safe", [{"value": 1}], domain="testing")
    (vault.VAULT_ROOT / "safe.jsonl.zst").write_bytes(b'{"value":1}\n{"value":NaN}\n')
    with pytest.raises(ValueError, match="corrupt row"):
        vault.read_shard("safe", limit=5)
    (vault.VAULT_ROOT / "_manifest.json").write_bytes(b'{"safe":{},"safe":{}}')
    with pytest.raises(ValueError, match="duplicate"):
        vault.vault_stats()


def test_byte_limits_reject_oversized_rows_and_scans(isolated_storage, monkeypatch):
    vault = isolated_storage
    monkeypatch.setattr(vault, "_MAX_ROW_CHARS", 32)
    with pytest.raises(ValueError, match="row exceeds"):
        vault.write_shard("oversize", [{"text": "X" * 256}], domain="testing")
    assert not (vault.VAULT_ROOT / "oversize.jsonl.zst").exists()
    vault.write_shard("safe", [{"x": 123456}], domain="testing")
    monkeypatch.setattr(vault, "_MAX_SHARD_SCAN_BYTES", 8)
    with pytest.raises(ValueError, match="decompressed byte budget"):
        vault.read_shard("safe", limit=5)


@pytest.mark.parametrize("limit,offset", [(True, 0), (1001, 0), (-1, 0), (1, -1), (1, 1_000_001)])
def test_invalid_paging_is_rejected(isolated_storage, limit, offset):
    with pytest.raises(ValueError):
        isolated_storage.read_shard("safe", limit=limit, offset=offset)



def _reject_manifest_write():
    raise RuntimeError("manifest publication interrupted")


def test_failed_manifest_write_restores_previous_shard_bytes(isolated_storage, monkeypatch):
    vault = isolated_storage
    vault.write_shard("stable", [{"value": "before"}], domain="testing")
    target = vault.VAULT_ROOT / "stable.jsonl.zst"
    before = target.read_bytes()
    original_manifest = (vault.VAULT_ROOT / "_manifest.json").read_bytes()
    monkeypatch.setattr(vault, "_save_manifest", _reject_manifest_write)

    with pytest.raises(RuntimeError, match="manifest publication interrupted"):
        vault.write_shard("stable", [{"value": "after"}], domain="testing")

    assert target.read_bytes() == before
    assert (vault.VAULT_ROOT / "_manifest.json").read_bytes() == original_manifest
    assert vault.read_shard("stable") == [{"value": "before"}]
    assert not list(vault.VAULT_ROOT.glob(".vault-backup-*"))
    assert not list(vault.VAULT_ROOT.glob(".vault-part-*"))


def test_failed_manifest_on_new_shard_removes_unreferenced_file(isolated_storage, monkeypatch):
    vault = isolated_storage
    vault.list_shards()
    monkeypatch.setattr(vault, "_save_manifest", _reject_manifest_write)
    with pytest.raises(RuntimeError, match="manifest publication interrupted"):
        vault.write_shard("never", [{"value": 1}], domain="testing")
    assert not (vault.VAULT_ROOT / "never.jsonl.zst").exists()
    assert vault.get_shard_entry("never") is None


def test_failed_delete_manifest_preserves_original_shard(isolated_storage, monkeypatch):
    vault = isolated_storage
    vault.write_shard("stable", [{"value": "before"}], domain="testing")
    target = vault.VAULT_ROOT / "stable.jsonl.zst"
    before = target.read_bytes()
    original_manifest = (vault.VAULT_ROOT / "_manifest.json").read_bytes()
    monkeypatch.setattr(vault, "_save_manifest", _reject_manifest_write)

    with pytest.raises(RuntimeError, match="manifest publication interrupted"):
        vault.delete_shard("stable")

    assert target.read_bytes() == before
    assert (vault.VAULT_ROOT / "_manifest.json").read_bytes() == original_manifest
    assert vault.read_shard("stable") == [{"value": "before"}]


def test_successful_overwrite_and_delete_reconcile_bytes_and_manifest(isolated_storage):
    vault = isolated_storage
    vault.write_shard("stable", [{"value": "before"}], domain="testing")
    vault.write_shard("stable", [{"value": "after"}], domain="testing")
    assert vault.read_shard("stable") == [{"value": "after"}]
    assert not list(vault.VAULT_ROOT.glob(".vault-backup-*"))
    assert vault.delete_shard("stable") is True
    assert vault.get_shard_entry("stable") is None
    assert not (vault.VAULT_ROOT / "stable.jsonl.zst").exists()



def test_late_manifest_fsync_failure_preserves_consistent_overwrite(isolated_storage, monkeypatch):
    vault = isolated_storage
    vault.write_shard("stable", [{"value": "before"}], domain="testing")
    save = vault._save_manifest

    def fail_after_commit():
        save()
        raise OSError("fsync failure after manifest publication")

    monkeypatch.setattr(vault, "_save_manifest", fail_after_commit)
    with pytest.raises(OSError, match="fsync failure"):
        vault.write_shard("stable", [{"value": "after"}], domain="testing")

    on_disk = json.loads((vault.VAULT_ROOT / "_manifest.json").read_text())
    assert vault._MANIFEST == on_disk
    assert vault.read_shard("stable") == [{"value": "after"}]


def test_late_manifest_fsync_failure_preserves_consistent_delete(isolated_storage, monkeypatch):
    vault = isolated_storage
    vault.write_shard("stable", [{"value": "before"}], domain="testing")
    save = vault._save_manifest

    def fail_after_commit():
        save()
        raise OSError("fsync failure after manifest publication")

    monkeypatch.setattr(vault, "_save_manifest", fail_after_commit)
    with pytest.raises(OSError, match="fsync failure"):
        vault.delete_shard("stable")

    on_disk = json.loads((vault.VAULT_ROOT / "_manifest.json").read_text())
    assert vault._MANIFEST == on_disk
    assert vault.get_shard_entry("stable") is None
    # After uncertain publication, the data is conservatively retained for
    # recovery rather than deleted while the caller sees an error.
    assert (vault.VAULT_ROOT / "stable.jsonl.zst").exists()



def test_post_replace_fsync_error_restores_prior_shard(isolated_storage, monkeypatch):
    vault = isolated_storage
    vault.write_shard("stable", [{"value": "before"}], domain="testing")
    shard = vault.VAULT_ROOT / "stable.jsonl.zst"
    original_data = shard.read_bytes()
    original_manifest = (vault.VAULT_ROOT / "_manifest.json").read_bytes()
    write_atomically = vault.atomic_write

    def fail_after_replace(fd, name, writer, **options):
        result = write_atomically(fd, name, writer, **options)
        if name == "stable.jsonl.zst":
            raise OSError("directory fsync failed after replace")
        return result

    monkeypatch.setattr(vault, "atomic_write", fail_after_replace)
    with pytest.raises(OSError, match="fsync failed"):
        vault.write_shard("stable", [{"value": "after"}], domain="testing")
    assert shard.read_bytes() == original_data
    assert (vault.VAULT_ROOT / "_manifest.json").read_bytes() == original_manifest
    assert vault.read_shard("stable") == [{"value": "before"}]
    assert not list(vault.VAULT_ROOT.glob(".vault-backup-*"))


def test_post_unlink_fsync_error_does_not_revive_dangling_manifest(isolated_storage, monkeypatch):
    vault = isolated_storage
    vault.write_shard("stable", [{"value": "before"}], domain="testing")
    unlink = vault.unlink_regular

    def fail_after_unlink(fd, name):
        unlink(fd, name)
        raise OSError("directory fsync failed after unlink")

    monkeypatch.setattr(vault, "unlink_regular", fail_after_unlink)
    with pytest.raises(OSError, match="fsync failed"):
        vault.delete_shard("stable")
    assert not (vault.VAULT_ROOT / "stable.jsonl.zst").exists()
    assert vault.get_shard_entry("stable") is None
    assert "stable" not in json.loads((vault.VAULT_ROOT / "_manifest.json").read_text())
