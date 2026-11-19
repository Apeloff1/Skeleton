"""Physical weight scrub regressions using real small files and durable controls."""
from __future__ import annotations

import os
from hashlib import sha256

import pytest

from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore, WeightShardStoreError
from skeleton.ai.model_runtime.weight_store_disk_owner import DiskAdmissionPolicy, WeightStoreDiskOwner
from skeleton.ai.model_runtime.weight_store_scrub import (
    ScrubPolicy, advance_weight_scrub, require_completed_weight_scrub,
    start_weight_scrub, weight_scrub_status,
)
from skeleton.testing.test_weight_store_disk_owner import prepare

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX managed writer required")


def owner_at(tmp_path):
    return WeightStoreDiskOwner(WeightShardStore(tmp_path / "store"),
                                DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))


def staged(owner, tmp_path, payload):
    identity, plan, paths = prepare(tmp_path, payload)
    owner.stage(identity, plan, paths)
    return identity, plan, paths


def advance(owner, state, *, maximum_bytes=1024, maximum_objects=1):
    return advance_weight_scrub(owner, campaign_digest=state["digest"],
                                maximum_bytes=maximum_bytes, maximum_objects=maximum_objects)


def test_durable_scrub_counts_distinct_objects_including_unreferenced(tmp_path):
    owner = owner_at(tmp_path)
    _, first, _ = staged(owner, tmp_path, b"alpha")
    _, second, _ = staged(owner, tmp_path, b"beta")
    _, third, _ = staged(owner, tmp_path, b"unreferenced")
    (owner._store.manifests / (third.digest + ".json")).unlink()
    state = start_weight_scrub(owner)
    assert state["object_count"] == 3 and state["manifest_count"] == 2
    assert state["unreferenced_count"] == 1
    assert state["total_bytes"] == len(b"alpha" + b"beta" + b"unreferenced")
    assert state["verified_objects"] == 0
    one = advance(owner, state)
    assert one["verified_this_tranche"] == 1 and one["status"] == "active"
    reopened = WeightStoreDiskOwner.open_existing(WeightShardStore(owner._store.root, create=False))
    assert weight_scrub_status(reopened)["campaign"] == one["campaign"]
    with pytest.raises(WeightShardStoreError, match="exact active cursor"):
        advance(reopened, state)
    two = advance(reopened, one["campaign"])
    three = advance(reopened, two["campaign"])
    result = three["campaign"]
    assert result["status"] == "completed"
    assert result["verified_objects"] == 3 and result["tranches"] == 3
    assert result["verified_bytes"] == result["total_bytes"]
    assert result["chain_digest"] != state["chain_digest"]
    observation = require_completed_weight_scrub(reopened, campaign_digest=result["digest"])
    assert observation["current_metadata_revalidated"]
    assert not observation["current_bytes_revalidated"]
    assert owner._store.verified_paths(first.digest) and owner._store.verified_paths(second.digest)


def test_large_object_requires_explicit_larger_tranche_without_cursor_mutation(tmp_path):
    owner = owner_at(tmp_path)
    staged(owner, tmp_path, b"12345678")
    state = start_weight_scrub(owner)
    result = advance(owner, state, maximum_bytes=7)
    assert result["status"] == "larger_tranche_required"
    assert result["required_bytes"] == 8 and result["campaign"] == state
    assert weight_scrub_status(owner)["campaign"] == state
    result = advance(owner, state, maximum_bytes=8)
    assert result["status"] == "completed" and result["bytes_this_tranche"] == 8


def test_same_size_corruption_is_persistently_blocked(tmp_path):
    owner = owner_at(tmp_path)
    _, plan, _ = staged(owner, tmp_path, b"verified")
    target = owner._store.verified_paths(plan.digest)[0]
    target.write_bytes(b"corrupt!")
    state = start_weight_scrub(owner)
    result = advance(owner, state)
    assert result["status"] == "blocked"
    assert result["reason"] == "object_content_mismatch"
    assert result["campaign"]["failure_object_digest"] == plan.shards[0].digest
    assert result["campaign"]["verified_objects"] == 0
    assert weight_scrub_status(owner)["campaign"]["failure_reason"] == "object_content_mismatch"
    with pytest.raises(WeightShardStoreError, match="exact active cursor"):
        advance(owner, result["campaign"])
    with pytest.raises(WeightShardStoreError, match="required completed"):
        require_completed_weight_scrub(owner, campaign_digest=result["campaign"]["digest"])
    assert target.read_bytes() == b"corrupt!"


def test_new_model_invalidates_prior_campaign_snapshot(tmp_path):
    owner = owner_at(tmp_path)
    staged(owner, tmp_path, b"first")
    state = start_weight_scrub(owner)
    staged(owner, tmp_path, b"new model")
    result = advance(owner, state)
    assert result["reason"] == "catalog_identity_changed"
    with pytest.raises(WeightShardStoreError, match="prior campaign"):
        start_weight_scrub(owner)
    restarted = start_weight_scrub(owner, prior_campaign_digest=result["campaign"]["digest"])
    assert restarted["prior_campaign_digest"] == result["campaign"]["digest"]
    assert restarted["object_count"] == 2
    assert restarted["verified_objects"] == 0


def test_completed_campaign_check_refuses_later_object_mutation(tmp_path):
    owner = owner_at(tmp_path)
    _, plan, _ = staged(owner, tmp_path, b"first")
    state = start_weight_scrub(owner)
    finished = advance(owner, state)["campaign"]
    assert finished["status"] == "completed"
    target = owner._store.verified_paths(plan.digest)[0]
    target.write_bytes(b"other")
    with pytest.raises(WeightShardStoreError, match="metadata no longer matches"):
        require_completed_weight_scrub(owner, campaign_digest=finished["digest"])


def test_campaign_fails_before_hashing_if_inventory_bounds_exceeded(tmp_path, monkeypatch):
    owner = owner_at(tmp_path)
    staged(owner, tmp_path, b"five!")
    from skeleton.ai.model_runtime import weight_store_scrub as module
    monkeypatch.setattr(module, "_hash_stream", lambda *a, **k: pytest.fail("unexpected hash"))
    with pytest.raises(WeightShardStoreError, match="catalog byte ceiling"):
        start_weight_scrub(owner, ScrubPolicy(maximum_total_bytes=4))
    with pytest.raises(WeightShardStoreError, match="entry ceiling"):
        start_weight_scrub(owner, ScrubPolicy(maximum_entries=1))
    with pytest.raises(WeightShardStoreError, match="manifest byte ceiling"):
        start_weight_scrub(owner, ScrubPolicy(maximum_manifest_bytes=1))
    assert weight_scrub_status(owner)["campaign"] is None


def test_interrupted_checkpoint_does_not_advance_cursor(tmp_path, monkeypatch):
    owner = owner_at(tmp_path)
    staged(owner, tmp_path, b"first")
    staged(owner, tmp_path, b"second")
    state = start_weight_scrub(owner)
    from skeleton.ai.model_runtime import weight_store_scrub as module
    original = module._hash_stream
    checked = []

    def interrupt(stream, *, maximum):
        checked.append(maximum)
        if len(checked) == 2:
            raise KeyboardInterrupt("interrupted hash")
        return original(stream, maximum=maximum)

    with monkeypatch.context() as patch:
        patch.setattr(module, "_hash_stream", interrupt)
        with pytest.raises(KeyboardInterrupt):
            advance(owner, state, maximum_objects=2)
    assert weight_scrub_status(owner)["campaign"] == state
    finished = advance(owner, state, maximum_objects=2)
    assert finished["status"] == "completed"
    assert finished["verified_this_tranche"] == 2


def test_scrub_never_acknowledges_unresolved_stage_or_corrupt_reference(tmp_path):
    owner = owner_at(tmp_path)
    identity, plan, paths = prepare(tmp_path, b"original")
    paths[0].write_bytes(b"corrupt!")
    with pytest.raises(WeightShardStoreError):
        owner.stage(identity, plan, paths)
    with pytest.raises(WeightShardStoreError, match="resolve staging intent"):
        start_weight_scrub(owner)
    assert owner.inspect()["active_intent"] is not None


def test_unreferenced_object_content_is_hashed_not_only_committed_refs(tmp_path):
    owner = owner_at(tmp_path)
    _, plan, _ = staged(owner, tmp_path, b"orphan")
    (owner._store.manifests / (plan.digest + ".json")).unlink()
    target = owner._store.objects / plan.shards[0].digest[:2] / plan.shards[0].digest
    target.write_bytes(b"broken")
    state = start_weight_scrub(owner)
    assert state["unreferenced_count"] == 1
    failed = advance(owner, state)
    assert failed["reason"] == "object_content_mismatch"
    assert failed["object_digest"] == plan.shards[0].digest


def test_forged_self_digest_is_not_accepted_as_completed_cursor(tmp_path):
    import json
    from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
    owner = owner_at(tmp_path)
    staged(owner, tmp_path, b"first")
    state = start_weight_scrub(owner)
    path = owner._store.root / ".weight-stage-scrub.json"
    altered = json.loads(path.read_bytes())
    altered["status"] = "completed"
    # Keep the old digest: internal record integrity must reject this.
    path.write_bytes(canonical_bytes(altered))
    with pytest.raises(WeightShardStoreError, match="control digest mismatch"):
        weight_scrub_status(owner)
    with pytest.raises(WeightShardStoreError):
        require_completed_weight_scrub(owner, campaign_digest=state["digest"])


def test_empty_store_campaign_is_explicitly_completed_without_byte_claim(tmp_path):
    owner = owner_at(tmp_path)
    state = start_weight_scrub(owner)
    assert state["status"] == "completed" and state["total_bytes"] == 0
    assert state["tranches"] == 0
    observed = require_completed_weight_scrub(owner, campaign_digest=state["digest"])
    assert observed["objects"] == 0 and not observed["native_qualified"]
