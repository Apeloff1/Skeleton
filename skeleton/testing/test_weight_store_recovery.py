"""Filesystem-level recovery review and exact intent acknowledgement regressions."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore, WeightShardStoreError
from skeleton.ai.model_runtime.weight_store_disk_owner import DiskAdmissionPolicy, WeightStoreDiskOwner
from skeleton.ai.model_runtime.weight_store_recovery import (
    RecoveryReviewPolicy, acknowledge_weight_store_recovery, review_weight_store,
)
from skeleton.testing.test_weight_store_disk_owner import prepare

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX cooperating writer required")


def make_owner(tmp_path):
    return WeightStoreDiskOwner(WeightShardStore(tmp_path / "store"),
                                DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))


def failed_intent(tmp_path):
    owner = make_owner(tmp_path)
    identity, plan, paths = prepare(tmp_path)
    good = paths[0].read_bytes()
    paths[0].write_bytes(b"x" * len(good))
    with pytest.raises(WeightShardStoreError):
        owner.stage(identity, plan, paths)
    paths[0].write_bytes(good)
    return owner, identity, plan, paths


def ack(owner, review):
    return acknowledge_weight_store_recovery(
        owner, intent_digest=review["active_intent"]["digest"], review_digest=review["digest"],
        maximum_verified_weight_bytes=1 << 20,
    )


def test_failed_intent_reconciliation_allows_retry_without_weight_deletion(tmp_path):
    owner, identity, plan, paths = failed_intent(tmp_path)
    review = review_weight_store(owner)
    assert review == review_weight_store(owner)
    assert review["counts"] == {"unresolved_staging_intent": 1}
    result = ack(owner, review)
    assert result["outcome"] == "recovery_reconciled"
    assert result["evidence"]["disposition"] == "manifest_not_published"
    assert not result["evidence"]["weight_mutation_performed"]
    assert owner.inspect()["active_intent"] is None
    assert owner.stage(identity, plan, paths)[0] == plan.digest


def test_interrupted_after_publication_is_verified_before_acknowledgement(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_store_disk_owner as module
    owner = make_owner(tmp_path)
    identity, plan, paths = prepare(tmp_path)

    def interrupt(*args, **kwargs):
        raise RuntimeError("interrupted before outcome publication")

    with monkeypatch.context() as patch:
        patch.setattr(module, "finish_intent", interrupt)
        with pytest.raises(RuntimeError, match="interrupted"):
            owner.stage(identity, plan, paths)
    review = review_weight_store(owner)
    assert review["valid_manifests"] == 1
    result = ack(owner, review)
    assert result["evidence"]["disposition"] == "committed_manifest_verified"
    assert owner._store.verified_paths(plan.digest)
    assert owner.inspect()["active_intent"] is None


def test_recovery_review_rejects_changed_evidence_even_with_truncated_details(tmp_path):
    owner, _, _, _ = failed_intent(tmp_path)
    policy = RecoveryReviewPolicy(maximum_details=1)
    review = review_weight_store(owner, policy)
    bucket = next(owner._store.objects.iterdir())
    object_digest = sha256(b"orphan").hexdigest()
    other = owner._store.objects / object_digest[:2]
    other.mkdir(exist_ok=True)
    candidate = other / object_digest
    candidate.write_bytes(b"orphan")
    changed = review_weight_store(owner, policy)
    assert changed["details_truncated"]
    assert changed["digest"] != review["digest"]
    with pytest.raises(WeightShardStoreError, match="evidence no longer matches"):
        acknowledge_weight_store_recovery(
            owner, intent_digest=review["active_intent"]["digest"], review_digest=review["digest"],
            maximum_verified_weight_bytes=1 << 20, policy=policy,
        )
    assert candidate.exists() and bucket.exists()


def test_unreferenced_object_candidate_requires_complete_manifest_scan(tmp_path):
    owner = make_owner(tmp_path)
    identity, plan, paths = prepare(tmp_path)
    owner.stage(identity, plan, paths)
    manifest = owner._store.manifests / (plan.digest + ".json")
    manifest.unlink()
    review = review_weight_store(owner)
    assert review["unreferenced_candidates"] == 1
    assert review["counts"]["unreferenced_object_candidate"] == 1
    manifest.write_bytes(b"{}")
    changed = review_weight_store(owner)
    assert changed["unreferenced_candidates"] is None
    assert "invalid_committed_manifest" in changed["counts"]


def test_abandoned_linked_temporary_is_distinguished_and_never_removed(tmp_path):
    owner = make_owner(tmp_path)
    identity, plan, paths = prepare(tmp_path)
    owner.stage(identity, plan, paths)
    target = owner._store.verified_paths(plan.digest)[0]
    temporary = target.with_name("." + target.name + "." + "a" * 32 + ".tmp")
    os.link(target, temporary)
    review = review_weight_store(owner)
    assert review["counts"]["interrupted_linked_publication"] == 1
    assert review["counts"]["nonexclusive_object_inode"] == 1
    assert temporary.exists() and target.exists()
    assert not review["deletion_authorized"]


def test_recovery_requires_actual_content_hash_not_size_only(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_store_disk_owner as module
    owner = make_owner(tmp_path)
    identity, plan, paths = prepare(tmp_path)
    with monkeypatch.context() as patch:
        def interrupt(*args, **kwargs):
            raise RuntimeError("interrupted")
        patch.setattr(module, "finish_intent", interrupt)
        with pytest.raises(RuntimeError):
            owner.stage(identity, plan, paths)
    target = owner._store.verified_paths(plan.digest)[0]
    target.write_bytes(b"x" * target.stat().st_size)
    review = review_weight_store(owner)
    assert review["counts"] == {"unresolved_staging_intent": 1}
    with pytest.raises(ValueError):
        ack(owner, review)
    assert owner.inspect()["active_intent"] is not None


def test_recovery_does_not_acknowledge_manifest_identity_substitution(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_store_disk_owner as module
    owner = make_owner(tmp_path)
    identity, plan, paths = prepare(tmp_path)
    with monkeypatch.context() as patch:
        def interrupt(*args, **kwargs):
            raise RuntimeError("interrupted")
        patch.setattr(module, "finish_intent", interrupt)
        with pytest.raises(RuntimeError):
            owner.stage(identity, plan, paths)
    manifest = owner._store.manifests / (plan.digest + ".json")
    record = json.loads(manifest.read_bytes())
    record["weights_digest"] = "0" * 64
    manifest.write_bytes(canonical_bytes(record))
    review = review_weight_store(owner)
    with pytest.raises(WeightShardStoreError, match="differs from intent"):
        ack(owner, review)
    assert owner.inspect()["active_intent"] is not None


def test_control_temporary_holds_acknowledgement_and_future_stage(tmp_path):
    owner, identity, plan, paths = failed_intent(tmp_path)
    abandoned = owner._store.root / ("..weight-stage-last.json." + "a" * 32 + ".tmp")
    abandoned.write_bytes(b"interrupted")
    review = review_weight_store(owner)
    assert review["counts"]["interrupted_control_publication"] == 1
    with pytest.raises(WeightShardStoreError, match="filesystem anomalies"):
        ack(owner, review)
    with pytest.raises(WeightShardStoreError, match="control publication"):
        owner.stage(identity, plan, paths)
    assert abandoned.read_bytes() == b"interrupted"


def test_review_bounds_references_and_metadata(tmp_path):
    owner = make_owner(tmp_path)
    identity, plan, paths = prepare(tmp_path)
    owner.stage(identity, plan, paths)
    with pytest.raises(WeightShardStoreError, match="metadata ceiling"):
        review_weight_store(owner, RecoveryReviewPolicy(maximum_metadata_bytes=1))
    with pytest.raises(WeightShardStoreError, match="entry ceiling"):
        review_weight_store(owner, RecoveryReviewPolicy(maximum_entries=1))


def test_recovery_acknowledgement_hashes_unreferenced_objects(tmp_path):
    owner, _, _, _ = failed_intent(tmp_path)
    payload = b"retained orphan"
    key = sha256(payload).hexdigest()
    bucket = owner._store.objects / key[:2]
    bucket.mkdir(exist_ok=True)
    target = bucket / key
    target.write_bytes(b"x" * len(payload))
    review = review_weight_store(owner)
    assert review["unreferenced_candidates"] == 1
    with pytest.raises(WeightShardStoreError, match="catalog object content mismatch"):
        ack(owner, review)
    assert owner.inspect()["active_intent"] is not None
    # Explicit local fixture repair, then obtain new review evidence.
    target.write_bytes(payload)
    updated = review_weight_store(owner)
    outcome = ack(owner, updated)
    assert outcome["evidence"]["verified_physical_objects"] == 1
    assert outcome["evidence"]["verified_physical_bytes"] == len(payload)
    assert target.read_bytes() == payload
    assert owner.inspect()["active_intent"] is None


def test_recovery_physical_budget_admits_orphans_before_hashing(tmp_path, monkeypatch):
    owner, _, _, _ = failed_intent(tmp_path)
    payload = b"retained orphan"
    key = sha256(payload).hexdigest()
    bucket = owner._store.objects / key[:2]
    bucket.mkdir(exist_ok=True)
    (bucket / key).write_bytes(payload)
    review = review_weight_store(owner)
    from skeleton.ai.model_runtime import weight_store_scrub as module
    monkeypatch.setattr(module, "_hash_stream", lambda *a, **k: pytest.fail("hash before admission"))
    with pytest.raises(WeightShardStoreError, match="catalog byte ceiling"):
        acknowledge_weight_store_recovery(
            owner, intent_digest=review["active_intent"]["digest"],
            review_digest=review["digest"], maximum_verified_weight_bytes=len(payload) - 1,
        )
    assert owner.inspect()["active_intent"] is not None


def test_recovery_synchronization_failure_does_not_clear_intent(tmp_path, monkeypatch):
    from skeleton.ai.model_runtime import weight_store_scrub as scrub

    owner, _, _, _ = failed_intent(tmp_path)
    payload = b"retained valid object"
    digest = sha256(payload).hexdigest()
    bucket = owner._store.objects / digest[:2]
    bucket.mkdir(exist_ok=True)
    target = bucket / digest
    target.write_bytes(payload)
    review = review_weight_store(owner)
    original = scrub.sync_verified_recovery_catalog

    def fail(owner, catalog, policy):
        with monkeypatch.context() as patch:
            def reject(fd):
                raise OSError("injected recovery sync failure")
            patch.setattr(scrub.os, "fsync", reject)
            return original(owner, catalog, policy)

    with monkeypatch.context() as patch:
        patch.setattr(scrub, "sync_verified_recovery_catalog", fail)
        with pytest.raises((WeightShardStoreError, OSError)):
            ack(owner, review)
    assert owner.inspect()["active_intent"]["digest"] == review["active_intent"]["digest"]
    assert target.read_bytes() == payload
    # No namespace/content mutation occurred during the failed fence.
    observed = review_weight_store(owner)
    assert observed["digest"] == review["digest"]
    result = ack(owner, observed)
    assert result["evidence"]["fsync_completed"]
    assert result["evidence"]["physical_power_loss_qualified"] is False
    assert result["evidence"]["verified_physical_bytes"] == len(payload)
    assert owner.inspect()["active_intent"] is None
