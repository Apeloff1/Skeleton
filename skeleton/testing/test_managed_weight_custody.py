"""Real cooperative read/write custody and selected-source integration regressions."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
import sys

import pytest

from skeleton.ai.model_runtime.managed_weight_read import managed_weight_read
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore, WeightShardStoreError
from skeleton.ai.model_runtime.weight_store_disk_owner import DiskAdmissionPolicy, WeightStoreDiskOwner
from skeleton.ai.model_runtime.weight_store_scrub import (
    advance_weight_scrub, start_weight_scrub,
)
from skeleton.app.offline_runtime_preflight import RuntimePolicy, inspect_source, plan_preflight
from skeleton.testing.test_offline_runtime_admission import sample
from skeleton.testing.test_weight_store_disk_owner import prepare

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX managed reader required")


def setup(tmp_path):
    root = tmp_path / "store"
    writer = WeightStoreDiskOwner(WeightShardStore(root),
                                 DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    identity, plan, paths = prepare(tmp_path, b"local committed model bytes")
    writer.stage(identity, plan, paths)
    return root, writer, identity, plan, paths


def test_multiple_reader_slots_exclude_cooperating_writer(tmp_path):
    root, writer, _, _, _ = setup(tmp_path)
    first = WeightShardStore(root, read_only=True)
    second = WeightShardStore(root, read_only=True)
    identity, plan, paths = prepare(tmp_path, b"second model")
    with managed_weight_read(first) as owner:
        assert owner is not None
        with managed_weight_read(second) as other:
            assert owner._policy_sha256 == other._policy_sha256
            with pytest.raises(WeightShardStoreError, match="shared readers"):
                writer.stage(identity, plan, paths)
        with pytest.raises(WeightShardStoreError, match="shared readers"):
            writer.stage(identity, plan, paths)
    assert writer.stage(identity, plan, paths)[0] == plan.digest


def test_writer_slot_excludes_runtime_source_scan(tmp_path):
    root, writer, identity, plan, _ = setup(tmp_path)
    policy = RuntimePolicy(verify_gguf_headers=False)
    with writer._owned():
        with pytest.raises(WeightShardStoreError, match="writer already active"):
            inspect_source(root, plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
                           policy=policy)
    observed = inspect_source(root, plan_digest=plan.digest,
                              model_identity_digest=identity.identity_digest, policy=policy)
    assert observed.managed_policy_sha256 == writer._policy_sha256
    assert observed.manifest_sha256 is not None


def test_decoder_retains_shared_slot_across_consumer_lifetime(tmp_path):
    root, writer, identity, plan, _ = setup(tmp_path)
    decoder = WeightShardStore(root, read_only=True)
    other, next_plan, paths = prepare(tmp_path, b"queued writer")
    with decoder.open_verified(plan.digest, model_identity=identity) as streams:
        assert streams[0].read() == b"local committed model bytes"
        with pytest.raises(WeightShardStoreError, match="shared readers"):
            writer.stage(other, next_plan, paths)
    assert writer.stage(other, next_plan, paths)[0] == next_plan.digest


@pytest.mark.skipif(not sys.platform.startswith("linux") or not hasattr(os, "memfd_create"),
                    reason="Linux memfd required")
def test_sealed_consumer_retains_managed_slot_and_exact_bytes(tmp_path):
    root, writer, identity, plan, _ = setup(tmp_path)
    decoder = WeightShardStore(root, read_only=True)
    other, next_plan, paths = prepare(tmp_path, b"queued writer")
    with decoder.open_sealed_pages(plan.digest, model_identity=identity, max_bytes=4096) as pages:
        assert bytes(pages[0]) == b"local committed model bytes"
        with pytest.raises(WeightShardStoreError, match="shared readers"):
            writer.stage(other, next_plan, paths)
    assert writer.stage(other, next_plan, paths)[0] == next_plan.digest


def test_interrupted_stage_blocks_existing_managed_source_admission(tmp_path):
    root, writer, identity, plan, _ = setup(tmp_path)
    other, next_plan, paths = prepare(tmp_path, b"pending model")
    paths[0].write_bytes(b"x" * paths[0].stat().st_size)
    with pytest.raises(WeightShardStoreError):
        writer.stage(other, next_plan, paths)
    assert writer.inspect()["active_intent"] is not None
    store = WeightShardStore(root, read_only=True)
    with pytest.raises(WeightShardStoreError, match="unresolved staging intent"):
        with store.open_verified(plan.digest, model_identity=identity):
            pytest.fail("decoder opened under interrupted transaction")
    with pytest.raises(WeightShardStoreError, match="unresolved staging intent"):
        inspect_source(root, plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
                       policy=RuntimePolicy(verify_gguf_headers=False))
    assert writer.inspect()["active_intent"] is not None


def test_independent_completed_scrub_pin_required_and_bound_to_runtime_policy(tmp_path):
    root, writer, identity, plan, _ = setup(tmp_path)
    initial = start_weight_scrub(writer)
    policy = RuntimePolicy(verify_gguf_headers=False, required_scrub_digest=initial["digest"])
    with pytest.raises(WeightShardStoreError, match="completed scrub"):
        inspect_source(root, plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
                       policy=policy)
    completed = advance_weight_scrub(writer, campaign_digest=initial["digest"],
                                     maximum_bytes=4096)["campaign"]
    policy = replace(policy, required_scrub_digest=completed["digest"])
    source = inspect_source(root, plan_digest=plan.digest,
                            model_identity_digest=identity.identity_digest, policy=policy)
    assert source.scrub_campaign_digest == completed["digest"]
    assert source.scrub_observation_digest is not None
    reading = sample()
    plan_preflight(source, reading, policy, now_ns=reading.finished_ns)
    with pytest.raises(ValueError, match="required scrub evidence"):
        plan_preflight(source, reading, replace(policy, required_scrub_digest="0" * 64),
                       now_ns=reading.finished_ns)
    other, next_plan, paths = prepare(tmp_path, b"new retained model")
    writer.stage(other, next_plan, paths)
    with pytest.raises(WeightShardStoreError, match="metadata no longer matches"):
        inspect_source(root, plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
                       policy=policy)


def test_legacy_source_stays_noncreating_but_cannot_claim_scrub_evidence(tmp_path):
    root = tmp_path / "store"
    store = WeightShardStore(root)
    identity, plan, paths = prepare(tmp_path)
    store.stage_plan(identity, plan, paths)
    with managed_weight_read(WeightShardStore(root, read_only=True)) as owner:
        assert owner is None
    assert not (root / ".weight-stage.lock").exists()
    with pytest.raises(ValueError, match="needs a managed store"):
        inspect_source(root, plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
                       policy=RuntimePolicy(verify_gguf_headers=False, required_scrub_digest="a" * 64))


def test_corrupt_or_missing_persisted_policy_never_reprovisions_during_read(tmp_path):
    root, _, _, _, _ = setup(tmp_path)
    path = root / ".weight-stage-policy.json"
    path.unlink()
    with pytest.raises(WeightShardStoreError):
        with managed_weight_read(WeightShardStore(root, read_only=True)):
            pytest.fail("missing persisted policy silently repaired")
    assert not path.exists()


def test_managed_read_detects_changed_root_permissions(tmp_path):
    root, writer, _, _, _ = setup(tmp_path)
    with writer.read_guard():
        root.chmod(0o755)
        with pytest.raises(WeightShardStoreError, match="private service-owned"):
            WeightStoreDiskOwner.open_existing(WeightShardStore(root, read_only=True))
        root.chmod(0o700)


def test_existing_managed_writer_final_hash_failure_leaves_intent(tmp_path, monkeypatch):
    root, writer, _, _, _ = setup(tmp_path)
    identity, plan, paths = prepare(tmp_path, b"new model")
    original = writer._store.verified_paths

    def mutate(key, **kwargs):
        target = writer._store.objects / plan.shards[0].digest[:2] / plan.shards[0].digest
        target.write_bytes(b"x" * target.stat().st_size)
        return original(key, **kwargs)

    monkeypatch.setattr(writer._store, "verified_paths", mutate)
    with pytest.raises(WeightShardStoreError, match="changed since admission"):
        writer.stage(identity, plan, paths)
    assert writer.inspect()["active_intent"]["plan_digest"] == plan.digest
    assert (root / "manifests" / (plan.digest + ".json")).exists()


def test_live_session_revokes_pending_grant_after_managed_transaction_interrupt(tmp_path, monkeypatch):
    import time
    from skeleton.app.offline_runtime_session import OfflineRuntimeSession
    from skeleton.app.offline_energy_hysteresis import HysteresisPolicy
    from skeleton.testing.test_offline_runtime_admission import POLICY, work
    root, writer, identity, plan, _ = setup(tmp_path)
    monkeypatch.setattr("skeleton.app.offline_runtime_session.sample_hardware",
                        lambda: sample(start=time.monotonic_ns() - 1000, origin="local_probe"))
    session = OfflineRuntimeSession(
        root, plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
        policy=POLICY, hysteresis=HysteresisPolicy(recovery_samples=2, recovery_cooldown_ns=0,
                                                max_sample_age_ns=POLICY.sample_age_ns))
    try:
        session.offer(work())
        grant = session.offer(work())["admission"]
        assert grant["status"] == "candidate"
        assert session.status()["last_metadata_fence_digest"]
        other, next_plan, paths = prepare(tmp_path, b"interrupted")
        paths[0].write_bytes(b"x" * paths[0].stat().st_size)
        with pytest.raises(WeightShardStoreError):
            writer.stage(other, next_plan, paths)
        with pytest.raises(WeightShardStoreError, match="unresolved staging intent"):
            session.consume(grant)
        assert not session.status()["admission"]["pending"]
        assert session.status()["last_metadata_fence_digest"] is None
    finally:
        session.close()


def test_runtime_metadata_fence_detects_selected_manifest_substitution(tmp_path):
    import json
    from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
    from skeleton.app.offline_runtime_preflight import revalidate_source_metadata
    root, _, identity, plan, _ = setup(tmp_path)
    policy = RuntimePolicy(verify_gguf_headers=False)
    source = inspect_source(root, plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
                            policy=policy)
    evidence = revalidate_source_metadata(root, source, policy)
    assert evidence["scope"] == "managed_manifest_metadata"
    assert not evidence["current_weight_bytes_rehashed"]
    manifest = root / "manifests" / (plan.digest + ".json")
    row = json.loads(manifest.read_bytes())
    row["weights_digest"] = "0" * 64
    manifest.write_bytes(canonical_bytes(row))
    with pytest.raises(ValueError, match="managed source manifest changed"):
        revalidate_source_metadata(root, source, policy)


def test_runtime_metadata_fence_rejects_legacy_to_managed_transition(tmp_path):
    from skeleton.app.offline_runtime_preflight import revalidate_source_metadata
    root = tmp_path / "legacy"
    store = WeightShardStore(root)
    identity, plan, paths = prepare(tmp_path)
    store.stage_plan(identity, plan, paths)
    policy = RuntimePolicy(verify_gguf_headers=False)
    source = inspect_source(root, plan_digest=plan.digest, model_identity_digest=identity.identity_digest,
                            policy=policy)
    WeightStoreDiskOwner(store, DiskAdmissionPolicy(1 << 20, minimum_free_bytes=0))
    with pytest.raises(ValueError, match="managed source policy changed"):
        revalidate_source_metadata(root, source, policy)
