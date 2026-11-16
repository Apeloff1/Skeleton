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

    def changing(self, key, **kwargs):
        paths = original(self, key, **kwargs)
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


def test_read_only_store_does_not_create_missing_layout(tmp_path):
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    missing = tmp_path / "missing"
    with pytest.raises(WeightShardStoreError, match="directory unavailable"):
        WeightShardStore(missing, read_only=True)
    assert not missing.exists()
    missing.mkdir()
    with pytest.raises(WeightShardStoreError, match="directory unavailable"):
        WeightShardStore(missing, read_only=True)
    assert list(missing.iterdir()) == []


def test_read_only_store_refuses_staging_before_materializing_any_data(tmp_path):
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    key, root = _stage(tmp_path)
    store = WeightShardStore(root, read_only=True)
    plan = store.load_plan(key)
    checksum = sha256(b"real offline weights").hexdigest()
    model = ModelIdentity("offline-test", "revision-1", "tiny", checksum, checksum, checksum)
    original = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    with pytest.raises(WeightShardStoreError, match="read-only"):
        store.stage_plan(model, plan, {0: tmp_path / "weights.bin"})
    assert sorted(str(path.relative_to(root)) for path in root.rglob("*")) == original
    assert store.verified_paths(key)


def test_missing_managed_directory_not_recreated_during_inspection(tmp_path):
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    key, root = _stage(tmp_path)
    store = WeightShardStore(root, read_only=True)
    directory = root / "objects"
    directory.rename(root / "removed-objects")
    with pytest.raises(WeightShardStoreError, match="directory unavailable"):
        store.verified_paths(key)
    assert not directory.exists()


def test_same_content_directory_substitution_rejected(tmp_path):
    import shutil
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    key, root = _stage(tmp_path)
    store = WeightShardStore(root, read_only=True)
    directory = root / "manifests"
    previous = root / "previous-manifests"
    directory.rename(previous)
    shutil.copytree(previous, directory)
    with pytest.raises(WeightShardStoreError, match="directory identity changed"):
        store.load_plan(key)


def test_symlinked_weight_bucket_cannot_be_used_as_canonical_source(tmp_path):
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    key, root = _stage(tmp_path)
    bucket = next((root / "objects").iterdir())
    elsewhere = tmp_path / "outside-bucket"
    bucket.rename(elsewhere)
    try:
        bucket.symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    store = WeightShardStore(root, read_only=True)
    with pytest.raises(WeightShardStoreError, match="real non-reparse"):
        store.verified_paths(key)
    with pytest.raises(OfflineInventoryError, match="verification failed"):
        inventory_offline_weights(root)


def test_inventory_refuses_managed_directory_replacement_with_same_names(tmp_path, monkeypatch):
    import shutil
    _, root = _stage(tmp_path)
    original = WeightShardStore.verified_paths

    def replacing(self, key, **kwargs):
        verified = original(self, key, **kwargs)
        directory = root / "manifests"
        backup = root / "displaced"
        directory.rename(backup)
        shutil.copytree(backup, directory)
        return verified

    monkeypatch.setattr(WeightShardStore, "verified_paths", replacing)
    with pytest.raises(OfflineInventoryError, match="verification failed"):
        inventory_offline_weights(root)


def test_manifest_boolean_schema_version_is_not_integer_schema(tmp_path):
    from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    key, root = _stage(tmp_path)
    manifest = root / "manifests" / (key + ".json")
    record = json.loads(manifest.read_bytes())
    record["schema_version"] = True
    manifest.write_bytes(canonical_bytes(record))
    with pytest.raises(WeightShardStoreError, match="invalid weight manifest shard declaration"):
        WeightShardStore(root, read_only=True).load_plan(key)


def test_inventory_metadata_and_reference_limits_apply_before_weight_verification(tmp_path, monkeypatch):
    _, root = _stage(tmp_path, payload=b"first weight")
    _stage(tmp_path, payload=b"second weight")
    expected = sum(path.stat().st_size for path in (root / "manifests").glob("*.json"))

    def refuse(*args, **kwargs):
        pytest.fail("opened weight objects before metadata admission")

    monkeypatch.setattr(WeightShardStore, "verified_paths", refuse)
    with pytest.raises(OfflineInventoryError):
        inventory_offline_weights(root, max_manifest_bytes=expected - 1)
    with pytest.raises(OfflineInventoryError, match="shard reference budget"):
        inventory_offline_weights(root, max_shard_references=1)


def test_inventory_binds_non_plan_manifest_fields(tmp_path):
    from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
    key, root = _stage(tmp_path)
    manifest = root / "manifests" / (key + ".json")
    before = inventory_offline_weights(root)
    assert before["models"][0]["manifest_sha256"] == sha256(manifest.read_bytes()).hexdigest()
    record = json.loads(manifest.read_bytes())
    record["weights_digest"] = "0" * 64
    manifest.write_bytes(canonical_bytes(record))
    after = inventory_offline_weights(root)
    # The load-plan digest does not contain the independent weights field.
    assert after["models"][0]["plan_digest"] == key
    assert before["digest"] != after["digest"]


def test_inventory_detects_earlier_manifest_mutation_during_later_verification(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
    _, root = _stage(tmp_path, payload=b"first weight")
    _stage(tmp_path, payload=b"second weight")
    manifests = sorted((root / "manifests").glob("*.json"))
    original = WeightShardStore.verified_paths

    def changing(self, key, **kwargs):
        paths = original(self, key, **kwargs)
        if key == manifests[1].stem:
            record = json.loads(manifests[0].read_bytes())
            record["weights_digest"] = "0" * 64
            manifests[0].write_bytes(canonical_bytes(record))
        return paths

    monkeypatch.setattr(WeightShardStore, "verified_paths", changing)
    with pytest.raises(OfflineInventoryError, match="manifest identity changed"):
        inventory_offline_weights(root)


def test_new_byte_budget_counts_distinct_absent_objects_before_ingestion(tmp_path):
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    store = WeightShardStore(tmp_path / "store")
    payload = b"deduplicated weight"
    path = tmp_path / "input"
    path.write_bytes(payload)
    checksum = sha256(payload).hexdigest()
    model = ModelIdentity("model", "r1", "tiny", checksum, checksum, checksum)
    plan = WeightLoadPlan(model.identity_digest, (
        WeightShard(0, checksum, len(payload), "local"),
        WeightShard(1, checksum, len(payload), "local"),
    ), len(payload) * 2)
    with pytest.raises(WeightShardStoreError, match="operation budget"):
        store.stage_plan(model, plan, {0: path, 1: path}, maximum_new_bytes=len(payload) - 1)
    assert not list(store.objects.rglob("*"))
    assert not list(store.manifests.iterdir())
    key = store.stage_plan(model, plan, {0: path, 1: path}, maximum_new_bytes=len(payload))
    assert store.stage_plan(model, plan, {0: path, 1: path}, maximum_new_bytes=0) == key
    assert len(list(store.objects.glob("*/*"))) == 1
    assert store.verified_paths(key)[0] == store.verified_paths(key)[1]


def test_ingest_rejects_conflicting_duplicate_digest_before_writes(tmp_path):
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
    store = WeightShardStore(tmp_path / "store")
    checksum = sha256(b"x").hexdigest()
    model = ModelIdentity("model", "r1", "tiny", checksum, checksum, checksum)
    plan = WeightLoadPlan(model.identity_digest, (
        WeightShard(0, checksum, 1, "local"),
        WeightShard(1, checksum, 2, "local"),
    ), 3)
    with pytest.raises(WeightShardStoreError, match="conflicting byte"):
        store.stage_plan(model, plan, {0: tmp_path / "a", 1: tmp_path / "b"})
    assert not list(store.objects.rglob("*"))


def test_ingest_refuses_manifest_overflow_before_object_writes(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_shard_store as owner
    store = WeightShardStore(tmp_path / "store")
    checksum = sha256(b"x").hexdigest()
    model = ModelIdentity("model", "r1", "tiny", checksum, checksum, checksum)
    plan = WeightLoadPlan(model.identity_digest, (
        WeightShard(0, checksum, 1, "local"),
    ), 1)
    monkeypatch.setattr(owner, "_MAX_MANIFEST_BYTES", 16)
    monkeypatch.setattr(store, "_ingest", lambda *args: pytest.fail("ingest before manifest admission"))
    with pytest.raises(owner.WeightShardStoreError, match="manifest exceeds"):
        store.stage_plan(model, plan, {0: tmp_path / "absent"})


def _stage_shared_objects(tmp_path):
    from dataclasses import replace
    payload = b"shared weights"
    checksum = sha256(payload).hexdigest()
    model = ModelIdentity("shared-model", "revision-1", "tiny", checksum, checksum, checksum)
    source = tmp_path / "source"
    source.write_bytes(payload)
    store = WeightShardStore(tmp_path / "store")
    shard = WeightShard(0, checksum, len(payload), "local")
    first = WeightLoadPlan(model.identity_digest, (shard,), len(payload))
    other = replace(model, revision="revision-2")
    second = WeightLoadPlan(other.identity_digest, (shard,), len(payload))
    store.stage_plan(model, first, {0: source})
    store.stage_plan(other, second, {0: source})
    return store, first, second, payload


def test_inventory_hashes_shared_objects_once_and_separates_physical_bytes(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_shard_store as module
    store, first, second, payload = _stage_shared_objects(tmp_path)
    original = module._hash_stream
    observed = []

    def capture(stream, *, maximum):
        observed.append(maximum)
        return original(stream, maximum=maximum)

    monkeypatch.setattr(module, "_hash_stream", capture)
    result = inventory_offline_weights(store.root, max_weight_bytes=len(payload) * 2,
                                       max_physical_weight_bytes=len(payload))
    assert result["model_count"] == 2
    assert result["total_shard_references"] == 2
    assert result["total_weight_bytes"] == 2 * len(payload)
    assert result["distinct_weight_objects"] == 1
    assert result["verified_physical_weight_bytes"] == len(payload)
    assert observed == [len(payload)]
    assert {row["plan_digest"] for row in result["models"]} == {first.digest, second.digest}
    # A subsequent invocation must physically verify rather than trusting
    # the previous invocation's metadata or process-local cache.
    assert inventory_offline_weights(store.root)["digest"] == result["digest"]
    assert observed == [len(payload), len(payload)]


def test_physical_weight_read_budget_rejects_before_any_hashing(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_shard_store as module
    store, _, _, payload = _stage_shared_objects(tmp_path)
    monkeypatch.setattr(module, "_hash_stream", lambda *a, **k: pytest.fail("hashed before admission"))
    with pytest.raises(OfflineInventoryError, match="distinct physical weights"):
        inventory_offline_weights(store.root, max_physical_weight_bytes=len(payload) - 1)
    with pytest.raises(OfflineInventoryError, match="aggregate offline weights"):
        inventory_offline_weights(store.root, max_weight_bytes=len(payload) * 2 - 1)


def test_deduplicated_inventory_detects_object_drift_between_references(tmp_path, monkeypatch):
    store, first, _, payload = _stage_shared_objects(tmp_path)
    target = store.verified_paths(first.digest)[0]
    original = WeightShardStore.verified_paths
    calls = []

    def mutate(self, key, **kwargs):
        result = original(self, key, **kwargs)
        calls.append(key)
        if len(calls) == 1:
            target.write_bytes(b"x" * len(payload))
        return result

    monkeypatch.setattr(WeightShardStore, "verified_paths", mutate)
    with pytest.raises(OfflineInventoryError, match="verification failed"):
        inventory_offline_weights(store.root)


def test_final_identity_fence_detects_last_verified_object_replacement(tmp_path, monkeypatch):
    store, first, _, payload = _stage_shared_objects(tmp_path)
    target = store.verified_paths(first.digest)[0]
    original = WeightShardStore.verified_paths
    calls = []

    def mutate(self, key, **kwargs):
        result = original(self, key, **kwargs)
        calls.append(key)
        if len(calls) == 2:
            replacement = target.with_name("replacement")
            replacement.write_bytes(payload)
            replacement.replace(target)
        return result

    monkeypatch.setattr(WeightShardStore, "verified_paths", mutate)
    with pytest.raises(OfflineInventoryError, match="verification failed"):
        inventory_offline_weights(store.root)


def test_weight_load_plan_detaches_mutable_shard_declaration():
    checksum = sha256(b"x").hexdigest()
    source = [WeightShard(0, checksum, 1, "local")]
    plan = WeightLoadPlan("a" * 64, source, 1)
    pin = plan.digest
    source[0] = WeightShard(0, "b" * 64, 1, "local")
    source.clear()
    assert len(plan.shards) == 1
    assert isinstance(plan.shards, tuple)
    assert plan.digest == pin
