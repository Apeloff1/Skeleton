"""Installed weight-store command boundaries and raw/semantic input custody."""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import io
import json
import os

import pytest

from skeleton.ai.model_runtime.weight_store_cli import main, read_stage_request
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStoreError
from skeleton.testing.test_weight_store_disk_owner import prepare

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX cooperating writer required")


def authored(tmp_path):
    identity, plan, paths = prepare(tmp_path)
    body = {"schema": "skeleton.weight-stage-request.v1",
            "identity": asdict(identity),
            "shards": [asdict(row) for row in plan.shards],
            "expected_total_bytes": plan.expected_total_bytes,
            "source_paths": [str(paths[index].absolute()) for index in range(len(paths))]}
    raw = json.dumps(body).encode("utf-8")
    pins = ["--request-sha256", sha256(raw).hexdigest(),
            "--model-identity-sha256", identity.identity_digest,
            "--plan-sha256", plan.digest]
    return raw, pins, identity, plan, paths


def common(tmp_path):
    return ["--store", str(tmp_path / "store"), "--maximum-store-bytes", str(1 << 20),
            "--minimum-free-bytes", "0"]


def invoke(args, raw=b""):
    out, err = io.StringIO(), io.StringIO()
    code = main(args, stdin=io.BytesIO(raw), stdout=out, stderr=err)
    return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()


def test_installed_stage_inspect_and_review_commands(tmp_path):
    raw, pins, identity, plan, _ = authored(tmp_path)
    code, result, error = invoke(["stage", *common(tmp_path), *pins], raw)
    assert code == 0 and not error
    assert result["plan_digest"] == plan.digest
    assert result["model_identity_digest"] == identity.identity_digest
    assert str(tmp_path) not in json.dumps(result)
    code, observation, _ = invoke(["inspect", *common(tmp_path)])
    assert code == 0 and observation["active_intent"] is None
    assert observation["last_outcome"]["outcome"] == "committed"
    code, review, _ = invoke(["recovery-review", *common(tmp_path), "--require-clean"])
    assert code == 0 and review["status"] == "no_anomalies_observed"


def test_bad_raw_pin_never_creates_store(tmp_path):
    raw, pins, _, _, _ = authored(tmp_path)
    code, _, error = invoke(["stage", *common(tmp_path), *pins], raw + b" ")
    assert code == 2 and str(tmp_path) not in error
    assert not (tmp_path / "store").exists()


def test_semantic_pin_rejection_and_duplicate_json(tmp_path):
    raw, _, identity, plan, _ = authored(tmp_path)
    with pytest.raises(WeightShardStoreError, match="model identity"):
        read_stage_request(io.BytesIO(raw), request_sha256=sha256(raw).hexdigest(),
                           model_identity_sha256="0" * 64, plan_sha256=plan.digest)
    duplicate = raw[:-1] + b', "schema": "skeleton.weight-stage-request.v1"}'
    with pytest.raises(WeightShardStoreError, match="duplicate"):
        read_stage_request(io.BytesIO(duplicate), request_sha256=sha256(duplicate).hexdigest(),
                           model_identity_sha256=identity.identity_digest, plan_sha256=plan.digest)


def test_relative_source_path_rejected_before_store_creation(tmp_path):
    raw, _, identity, plan, _ = authored(tmp_path)
    document = json.loads(raw)
    document["source_paths"][0] = "relative.bin"
    raw = json.dumps(document).encode("utf-8")
    with pytest.raises(WeightShardStoreError, match="absolute"):
        read_stage_request(io.BytesIO(raw), request_sha256=sha256(raw).hexdigest(),
                           model_identity_sha256=identity.identity_digest, plan_sha256=plan.digest)


def test_inspection_does_not_provision_missing_store_or_lock(tmp_path):
    code, _, _ = invoke(["inspect", *common(tmp_path)])
    assert code == 2 and not (tmp_path / "store").exists()
    from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore
    store = WeightShardStore(tmp_path / "store")
    code, _, _ = invoke(["recovery-review", *common(tmp_path)])
    assert code == 2 and not (store.root / ".weight-stage.lock").exists()


def test_exact_recovery_acknowledgement_cli(tmp_path):
    raw, pins, _, plan, paths = authored(tmp_path)
    good = paths[0].read_bytes()
    paths[0].write_bytes(b"x" * len(good))
    code, _, _ = invoke(["stage", *common(tmp_path), *pins], raw)
    assert code == 2
    paths[0].write_bytes(good)
    code, review, _ = invoke(["recovery-review", *common(tmp_path), "--require-clean"])
    assert code == 3 and review["active_intent"]["plan_digest"] == plan.digest
    command = ["acknowledge-recovery", *common(tmp_path),
               "--intent-sha256", review["active_intent"]["digest"],
               "--maximum-verified-weight-bytes", str(1 << 20)]
    code, _, _ = invoke([*command, "--review-sha256", "0" * 64])
    assert code == 2
    code, result, _ = invoke([*command, "--review-sha256", review["digest"]])
    assert code == 0 and result["outcome"] == "recovery_reconciled"
    code, result, _ = invoke(["stage", *common(tmp_path), *pins], raw)
    assert code == 0 and result["plan_digest"] == plan.digest


def test_scrub_commands_require_exact_cursor_and_verify_completed_snapshot(tmp_path):
    raw, pins, _, _, _ = authored(tmp_path)
    code, _, _ = invoke(["stage", *common(tmp_path), *pins], raw)
    assert code == 0
    code, initial, _ = invoke(["scrub-status", *common(tmp_path)])
    assert code == 0 and initial["status"] == "not_started"
    code, started, _ = invoke(["scrub-start", *common(tmp_path)])
    assert code == 0 and started["status"] == "active"
    command = ["scrub-step", *common(tmp_path), "--scrub-campaign-sha256", started["digest"]]
    code, _, _ = invoke(["scrub-step", *common(tmp_path)])
    assert code == 2
    code, larger, _ = invoke([*command, "--scrub-tranche-bytes", "1"])
    assert code == 3 and larger["status"] == "larger_tranche_required"
    code, completed, _ = invoke([*command, "--scrub-tranche-bytes", "4096"])
    assert code == 0 and completed["status"] == "completed"
    final = completed["campaign"]["digest"]
    code, _, _ = invoke(command)
    assert code == 2
    code, observation, _ = invoke(["scrub-check", *common(tmp_path),
                                   "--scrub-campaign-sha256", final])
    assert code == 0 and observation["current_metadata_revalidated"]
    assert not observation["current_bytes_revalidated"]
    assert str(tmp_path) not in json.dumps(observation)
    code, _, _ = invoke(["scrub-start", *common(tmp_path)])
    assert code == 2
    code, next_campaign, _ = invoke(["scrub-start", *common(tmp_path), "--scrub-prior-sha256", final])
    assert code == 0 and next_campaign["prior_campaign_digest"] == final
    assert next_campaign["verified_objects"] == 0


def test_installed_range_commands_resume_with_independent_index(tmp_path):
    from skeleton.ai.model_runtime.flgb_model_runtime import canonical_bytes
    raw, pins, _, plan, _ = authored(tmp_path)
    assert invoke(["stage", *common(tmp_path), *pins], raw)[0] == 0
    shard = plan.shards[0]
    code, index, _ = invoke(["range-index", *common(tmp_path),
                             "--range-object-sha256", shard.digest,
                             "--range-object-bytes", str(shard.bytes),
                             "--range-index-max-bytes", str(shard.bytes)])
    assert code == 0
    index_bytes = canonical_bytes(index) + b"\n"
    args = ["--range-index-sha256", index["digest"]]
    assert invoke(["range-start", *common(tmp_path), "--range-index-sha256", "0" * 64],
                  index_bytes)[0] == 2
    code, started, _ = invoke(["range-start", *common(tmp_path), *args], index_bytes)
    assert code == 0 and started["status"] == "active"
    code, _, _ = invoke(["range-status", *common(tmp_path)])
    assert code == 0
    advancement = ["range-step", *common(tmp_path), *args,
                   "--range-campaign-sha256", started["digest"]]
    code, _, _ = invoke([*advancement, "--range-tranche-bytes", "1"], index_bytes)
    assert code == 3
    code, result, _ = invoke(advancement, index_bytes)
    assert code == 0 and result["status"] == "completed"
    code, check, _ = invoke(["range-check", *common(tmp_path), *args,
                             "--range-campaign-sha256", result["campaign"]["digest"]], index_bytes)
    assert code == 0 and check["current_metadata_revalidated"]
    assert not check["raw_sha256_recomputed"]
