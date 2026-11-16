"""Real filesystem and cooperating writer regressions; no disk quota claims."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil

import pytest

from skeleton.ai.model_runtime.flgb_model_runtime import (
    ModelIdentity, WeightLoadPlan, WeightShard,
)
from skeleton.ai.model_runtime.weight_shard_store import (
    WeightShardStore, WeightShardStoreError,
)
from skeleton.ai.model_runtime.weight_store_disk_owner import (
    DiskAdmissionPolicy, WeightStoreDiskOwner,
)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX cooperating writer required")


def prepare(tmp_path: Path, payload: bytes = b"weight object"):
    checksum = sha256(payload).hexdigest()
    identity = ModelIdentity("model", "r1", "tiny", checksum, checksum, checksum)
    plan = WeightLoadPlan(identity.identity_digest,
                          (WeightShard(0, checksum, len(payload), "local"),), len(payload))
    source = tmp_path / ("source-" + checksum)
    source.write_bytes(payload)
    return identity, plan, {0: source}


def test_stage_counts_objects_manifests_and_idempotent_reuse(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    identity, plan, paths = prepare(tmp_path)
    key, receipt = owner.stage(identity, plan, paths)
    assert key == plan.digest
    assert receipt["before"]["accounted_bytes"] == 0
    assert receipt["after"]["object_bytes"] == plan.expected_total_bytes
    assert receipt["after"]["manifest_bytes"] > 0
    assert receipt["charged_bytes"] == receipt["after"]["accounted_bytes"]
    assert receipt["hard_quota"] is False
    _, repeated = owner.stage(identity, plan, paths)
    assert repeated["charged_bytes"] == repeated["admitted_new_bytes"] == 0
    assert repeated["after"] == receipt["after"]
    assert owner.inspect()["inventory"] == receipt["after"]


def test_unreferenced_objects_are_counted_against_store_cap(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    identity, plan, paths = prepare(tmp_path, b"unreferenced data")
    key = store.stage_plan(identity, plan, paths)
    (store.manifests / (key + ".json")).unlink()
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(32, minimum_free_bytes=0))
    before = owner.inspect()["inventory"]
    assert before["object_bytes"] == plan.expected_total_bytes and before["manifests"] == 0
    other, next_plan, sources = prepare(tmp_path, b"additional model")
    with pytest.raises(WeightShardStoreError, match="byte ceiling"):
        owner.stage(other, next_plan, sources)
    assert owner.inspect()["inventory"] == before


def test_cooperating_writer_contention_does_not_enter_stage(tmp_path, monkeypatch):
    store = WeightShardStore(tmp_path / "store")
    policy = DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0)
    first = WeightStoreDiskOwner(store, policy)
    second = WeightStoreDiskOwner(WeightShardStore(store.root), policy)
    identity, plan, paths = prepare(tmp_path)
    with first._owned():
        with pytest.raises(WeightShardStoreError, match="already active"):
            second.stage(identity, plan, paths)
    assert second.stage(identity, plan, paths)[0] == plan.digest


def test_space_reserve_and_entry_budget_refuse_before_ingestion(tmp_path, monkeypatch):
    store = WeightShardStore(tmp_path / "store")
    identity, plan, paths = prepare(tmp_path)
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=4096))
    monkeypatch.setattr(shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(8192, 4096, 4096))
    with pytest.raises(WeightShardStoreError, match="free-byte reserve"):
        owner.stage(identity, plan, paths)
    assert not list(store.objects.iterdir())
    separate = WeightShardStore(tmp_path / "entry-store")
    entries = WeightStoreDiskOwner(separate, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0, maximum_entries=2))
    with pytest.raises(WeightShardStoreError, match="prospective"):
        entries.stage(identity, plan, paths)
    assert not list(separate.manifests.iterdir())


def test_interrupted_temporary_file_requires_explicit_operator_review(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    bucket = store.objects / "aa"
    bucket.mkdir()
    abandoned = bucket / ".interrupted.tmp"
    abandoned.write_bytes(b"partially staged")
    with pytest.raises(WeightShardStoreError, match="recovery review"):
        owner.inspect()
    assert abandoned.read_bytes() == b"partially staged"


def test_lock_inode_replacement_refuses_operation(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    lock = store.root / ".weight-stage.lock"
    replacement = store.root / "replacement"
    replacement.touch(mode=0o600)
    replacement.replace(lock)
    with pytest.raises(WeightShardStoreError, match="inode changed"):
        owner.inspect()


def test_actual_write_budget_denies_vanished_preexisting_object(tmp_path, monkeypatch):
    store = WeightShardStore(tmp_path / "store")
    identity, plan, paths = prepare(tmp_path)
    store.stage_plan(identity, plan, paths)
    original = store._ingest

    def vanished(shard, source, **kwargs):
        store._object_path(shard.digest).unlink()
        return original(shard, source, **kwargs)

    monkeypatch.setattr(store, "_ingest", vanished)
    with pytest.raises(WeightShardStoreError, match="actual new weight writes"):
        store.stage_plan(identity, plan, paths, maximum_new_bytes=0)
    assert not list(store.objects.glob("*/*"))


def test_failed_source_leaves_no_published_manifest(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    identity, plan, paths = prepare(tmp_path)
    paths[0].write_bytes(b"incorrect bytes")
    with pytest.raises(WeightShardStoreError):
        owner.stage(identity, plan, paths)
    assert not list(store.manifests.iterdir())
    assert owner.inspect()["inventory"]["object_bytes"] == 0


def test_provisioned_store_refuses_legacy_write_and_mismatched_policy(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    policy = DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0)
    owner = WeightStoreDiskOwner(store, policy)
    identity, plan, paths = prepare(tmp_path)
    with pytest.raises(WeightShardStoreError, match="cooperative disk owner"):
        WeightShardStore(store.root).stage_plan(identity, plan, paths)
    with pytest.raises(WeightShardStoreError, match="differs from persisted"):
        WeightStoreDiskOwner(WeightShardStore(store.root),
                             DiskAdmissionPolicy(2 << 20, minimum_free_bytes=0))
    assert owner.stage(identity, plan, paths)[0] == plan.digest
    reopened = WeightStoreDiskOwner(WeightShardStore(store.root, read_only=True),
                                    policy, initialize=False)
    assert reopened.inspect()["active_intent"] is None
    assert reopened.inspect()["last_outcome"]["outcome"] == "committed"


def test_lock_replacement_is_refused_even_by_a_new_owner(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    policy = DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0)
    WeightStoreDiskOwner(store, policy)
    old = store.root / ".weight-stage.lock"
    replacement = store.root / "replacement"
    replacement.touch(mode=0o600)
    replacement.replace(old)
    with pytest.raises(WeightShardStoreError, match="differs from persisted"):
        WeightStoreDiskOwner(WeightShardStore(store.root), policy)


def test_missing_provisioned_lock_is_not_recreated(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    policy = DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0)
    WeightStoreDiskOwner(store, policy)
    lock = store.root / ".weight-stage.lock"
    lock.unlink()
    with pytest.raises((WeightShardStoreError, FileNotFoundError)):
        WeightStoreDiskOwner(WeightShardStore(store.root), policy)
    assert not lock.exists()
    identity, plan, paths = prepare(tmp_path)
    with pytest.raises(WeightShardStoreError, match="cooperative disk owner"):
        store.stage_plan(identity, plan, paths)


def test_invalid_declaration_is_refused_before_intent(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    identity, plan, _ = prepare(tmp_path)
    with pytest.raises(WeightShardStoreError, match="source index"):
        owner.stage(identity, plan, {})
    assert owner.inspect()["active_intent"] is None


def test_later_staging_error_leaves_exact_durable_intent(tmp_path):
    store = WeightShardStore(tmp_path / "store")
    policy = DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0)
    owner = WeightStoreDiskOwner(store, policy)
    identity, plan, paths = prepare(tmp_path)
    good = paths[0].read_bytes()
    paths[0].write_bytes(b"x" * len(good))
    with pytest.raises(WeightShardStoreError):
        owner.stage(identity, plan, paths)
    intent = owner.inspect()["active_intent"]
    assert intent["plan_digest"] == plan.digest
    assert intent["model_identity_digest"] == identity.identity_digest
    paths[0].write_bytes(good)
    another = WeightStoreDiskOwner(WeightShardStore(store.root), policy)
    assert another.inspect()["active_intent"] == intent
    with pytest.raises(WeightShardStoreError, match="unresolved staging intent"):
        another.stage(identity, plan, paths)

 
def test_stage_requires_verified_descriptor_durability_before_outcome(tmp_path, monkeypatch):
    import stat
    from skeleton.ai.model_runtime import weight_shard_store as module

    store = WeightShardStore(tmp_path / "store")
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    identity, plan, paths = prepare(tmp_path)
    original = os.fsync
    synced_files = set()
    synced_directories = set()

    def capture(fd):
        info = os.fstat(fd)
        if stat.S_ISREG(info.st_mode):
            synced_files.add((info.st_dev, info.st_ino))
        elif stat.S_ISDIR(info.st_mode):
            synced_directories.add((info.st_dev, info.st_ino))
        return original(fd)

    monkeypatch.setattr(module.os, "fsync", capture)
    key, receipt = owner.stage(identity, plan, paths)
    target = store.verified_paths(key)[0]
    manifest = store.manifests / (key + ".json")
    assert receipt["durable_outcome_digest"] == owner.inspect()["last_outcome"]["digest"]
    for path in (target, manifest):
        info = path.stat()
        assert (info.st_dev, info.st_ino) in synced_files
    for path in (target.parent, store.objects, store.manifests, store.root):
        info = path.stat()
        assert (info.st_dev, info.st_ino) in synced_directories
    assert not list(target.parent.glob("*.tmp"))
    assert owner.inspect()["active_intent"] is None


def test_failed_durability_barrier_retains_exact_intent(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_shard_store as module

    store = WeightShardStore(tmp_path / "store")
    owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    identity, plan, paths = prepare(tmp_path)
    original = store.verified_paths

    def fail_at_final_verification(key, **kwargs):
        assert kwargs["_durable"] is True
        with monkeypatch.context() as patch:
            patch.setattr(module.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("fixture sync failure")))
            return original(key, **kwargs)

    monkeypatch.setattr(store, "verified_paths", fail_at_final_verification)
    with pytest.raises(WeightShardStoreError):
        owner.stage(identity, plan, paths)
    observed = owner.inspect()
    assert observed["active_intent"]["plan_digest"] == plan.digest
    assert observed["last_outcome"] is None
    assert (store.manifests / (plan.digest + ".json")).exists()
