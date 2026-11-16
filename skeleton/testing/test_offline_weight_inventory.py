"""Canonical offline model inventory with real immutable shard store."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import pytest

from skeleton.ai.model_runtime.flgb_model_runtime import ModelIdentity, WeightLoadPlan, WeightShard
from skeleton.ai.model_runtime.offline_inventory import (
    OfflineInventoryError, inventory_offline_weights, main,
)
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore


def _stage(root: Path, *, payload: bytes = b"real offline weights") -> tuple[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    src = root / "weights.bin"
    src.write_bytes(payload)
    digest = sha256(payload).hexdigest()
    identity = ModelIdentity("offline-test", "revision-1", "tiny", digest, digest, digest)
    shard = WeightShard(0, digest, len(payload), "local")
    plan = WeightLoadPlan(identity.identity_digest, (shard,), len(payload))
    plan_digest = WeightShardStore(root / "store").stage_plan(identity, plan, {0: src})
    return plan_digest, root / "store"


def test_verified_inventory_is_deterministic_and_offline(tmp_path: Path) -> None:
    digest, store = _stage(tmp_path)
    first = inventory_offline_weights(store)
    second = inventory_offline_weights(store)
    assert first == second
    assert first["model_count"] == 1
    assert first["models"][0]["plan_digest"] == digest
    assert first["device_qualification"] == "not_assessed"
    assert first["model_activation"] == "not_performed"
    assert "weights.bin" not in json.dumps(first)


def test_corrupt_object_refuses_partial_success(tmp_path: Path) -> None:
    digest, store = _stage(tmp_path)
    object_path = next((store / "objects").glob("*/*"))
    object_path.write_bytes(b"tampered")
    with pytest.raises(OfflineInventoryError, match="verification failed"):
        inventory_offline_weights(store)


def test_corrupt_manifest_refuses_inventory(tmp_path: Path) -> None:
    digest, store = _stage(tmp_path)
    (store / "manifests" / (digest + ".json")).write_text("{}")
    with pytest.raises(OfflineInventoryError, match="verification failed"):
        inventory_offline_weights(store)


def test_unknown_manifest_file_is_not_silently_ignored(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    (store / "manifests" / "unfinished.tmp").write_text("incomplete")
    with pytest.raises(OfflineInventoryError, match="unexpected"):
        inventory_offline_weights(store)


def test_symlinked_manifest_rejected(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    (store / "manifests" / ("0" * 64 + ".json")).symlink_to("missing")
    with pytest.raises(OfflineInventoryError, match="unexpected"):
        inventory_offline_weights(store)


def test_symlinked_store_directory_rejected(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(store, target_is_directory=True)
    with pytest.raises(OfflineInventoryError, match="real directory"):
        inventory_offline_weights(alias)


def test_inventory_fails_closed_when_entry_budget_exhausted(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    _stage(tmp_path, payload=b"distinct offline weights")
    with pytest.raises(OfflineInventoryError, match="entry budget"):
        inventory_offline_weights(store, max_entries=1)


def test_inventory_rejects_invalid_entry_limit(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    with pytest.raises(OfflineInventoryError, match="entry limit"):
        inventory_offline_weights(store, max_entries=0)


def test_inventory_fails_closed_when_byte_budget_exhausted(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    with pytest.raises(OfflineInventoryError):
        inventory_offline_weights(store, max_weight_bytes=2)


def test_inventory_cli_returns_canonical_receipt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, store = _stage(tmp_path)
    assert main([str(store)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["model_count"] == 1
    assert len(result["digest"]) == 64


def test_missing_store_is_never_created_by_inventory(tmp_path: Path) -> None:
    path = tmp_path / "absent"
    with pytest.raises(OfflineInventoryError):
        inventory_offline_weights(path)
    assert not path.exists()


def test_aggregate_budget_refuses_before_any_object_hashing(tmp_path, monkeypatch):
    _, store = _stage(tmp_path, payload=b"a" * 32)
    _stage(tmp_path, payload=b"b" * 32)

    def refuse(*args, **kwargs):
        pytest.fail("weight objects opened before aggregate budget admission")

    monkeypatch.setattr(WeightShardStore, "verified_paths", refuse)
    with pytest.raises(OfflineInventoryError, match="aggregate"):
        inventory_offline_weights(store, max_weight_bytes=48)


def test_inventory_refuses_a_new_manifest_during_verification(tmp_path, monkeypatch):
    _, store = _stage(tmp_path)
    original = WeightShardStore.verified_paths
    observed = []

    def changing(self, key):
        paths = original(self, key)
        if not observed:
            observed.append(True)
            _stage(tmp_path, payload=b"new concurrent model")
        return paths

    monkeypatch.setattr(WeightShardStore, "verified_paths", changing)
    with pytest.raises(OfflineInventoryError, match="changed during verification"):
        inventory_offline_weights(store)


def test_direct_plan_loader_bounds_sparse_manifest_and_refuses_symlinks(tmp_path):
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    key, root = _stage(tmp_path)
    store = WeightShardStore(root)
    manifest = root / "manifests" / (key + ".json")
    raw = manifest.read_bytes()
    with manifest.open("wb") as handle:
        handle.truncate(16 * 1024 * 1024 + 1)
    with pytest.raises(WeightShardStoreError, match="manifest unavailable"):
        store.load_plan(key)
    manifest.write_bytes(raw)
    alternate = tmp_path / "alternate.json"
    alternate.write_bytes(raw)
    manifest.unlink()
    try:
        manifest.symlink_to(alternate)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(WeightShardStoreError, match="manifest unavailable"):
        store.load_plan(key)


def test_decoder_streams_are_the_actual_verified_descriptors(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_shard_store as module
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    payload = b"real offline weights"
    key, root = _stage(tmp_path, payload=payload)
    checksum = sha256(payload).hexdigest()
    model = ModelIdentity("offline-test", "revision-1", "tiny", checksum, checksum, checksum)
    store = WeightShardStore(root)
    original = module._hash_stream
    verified = []

    def observe(stream, *, maximum):
        verified.append(stream)
        return original(stream, maximum=maximum)

    monkeypatch.setattr(module, "_hash_stream", observe)
    with store.open_verified(key, model_identity=model) as streams:
        assert len(streams) == len(verified) == 1
        assert streams[0] is verified[0]
        assert streams[0].tell() == 0
        assert streams[0].read() == payload
    assert verified[0].closed

    # Replace the pathname after the exact descriptor has been hashed.
    # The consumer must not be handed the substituted object.
    if __import__("os").name != "posix":
        pytest.skip("open-file replacement regression requires POSIX")
    object_path = next((root / "objects").glob("*/*"))
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"x" * len(payload))
    with pytest.raises(WeightShardStoreError, match="changed during inspection"):
        with store.open_verified(key, model_identity=model) as streams:
            replacement.replace(object_path)
            assert streams[0].read() == payload
    assert all(stream.closed for stream in verified)
