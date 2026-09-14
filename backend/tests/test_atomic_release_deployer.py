from __future__ import annotations

import hashlib
import json

import pytest

from core.canonical_json import canonical_json_sha256, canonical_json_text
from core.atomic_release_deployer import AtomicReleaseDeployer, ReleaseDeploymentError
from core.deployment_authorization import DeploymentConsumption, plan_digest
from core.deployment_planner import compile_deployment_plan


def _consumption(plan: dict, *, authorization_id: str = "auth-1", consumed_at: str = "2026-09-14T12:00:00+00:00") -> DeploymentConsumption:
    return DeploymentConsumption(
        authorization_id=authorization_id,
        consumed_at=consumed_at,
        system_root_sha256="a" * 64,
        plan_sha256=plan_digest(plan),
        consume_event_sha256="b" * 64,
    )


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _rehash(plan: dict) -> dict:
    forged = dict(plan)
    forged.pop("plan_sha256", None)
    forged["plan_sha256"] = hashlib.sha256(_canonical(forged)).hexdigest()
    return forged


def _rehash_record(row: dict) -> dict:
    forged = dict(row)
    payload = {key: value for key, value in forged.items() if key != "sha256"}
    forged["sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return forged


def _activated(tmp_path):
    deployer = AtomicReleaseDeployer(tmp_path)
    plan = compile_deployment_plan({"artifact": "sha256:a", "target": "runtime", "environment": "staging"})
    record = deployer.activate(plan, _consumption(plan), activated_at="2026-09-14T12:00:01+00:00")
    history_path = next(tmp_path.glob("*/releases.jsonl"))
    current_path = next(tmp_path.glob("*/current.json"))
    return deployer, plan, record, history_path, current_path


def test_activation_is_atomic_persistent_and_replay_safe(tmp_path):
    deployer = AtomicReleaseDeployer(tmp_path)
    plan = compile_deployment_plan({
        "artifact": "sha256:release-a",
        "target": "runtime",
        "environment": "production",
        "strategy": "canary",
    })
    consumption = _consumption(plan)

    first = deployer.activate(plan, consumption, activated_at="2026-09-14T12:00:01+00:00")
    replay = deployer.activate(plan, consumption, activated_at="2026-09-14T12:00:02+00:00")

    assert replay == first
    assert first.sequence == 1
    assert first.authorization_id == "auth-1"
    assert first.plan_sha256 == plan_digest(plan)
    assert deployer.current(target="runtime", environment="production") == first
    assert AtomicReleaseDeployer(tmp_path).snapshot() == (first,)


def test_second_release_links_to_previous_release(tmp_path):
    deployer = AtomicReleaseDeployer(tmp_path)
    plan_a = compile_deployment_plan({"artifact": "sha256:a", "target": "runtime", "environment": "staging"})
    plan_b = compile_deployment_plan({"artifact": "sha256:b", "target": "runtime", "environment": "staging"})
    first = deployer.activate(plan_a, _consumption(plan_a, authorization_id="auth-a"), activated_at="2026-09-14T12:00:01+00:00")
    second = deployer.activate(plan_b, _consumption(plan_b, authorization_id="auth-b"), activated_at="2026-09-14T12:00:02+00:00")

    assert second.sequence == 2
    assert second.previous_release_id == first.release_id
    assert second.previous_sha256 == first.sha256
    assert deployer.current(target="runtime", environment="staging") == second


def test_self_hashed_but_semantically_forged_plan_cannot_activate(tmp_path):
    deployer = AtomicReleaseDeployer(tmp_path)
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    plan["rollback"] = dict(plan["rollback"])
    plan["rollback"]["automatic"] = False
    forged = _rehash(plan)

    with pytest.raises(ReleaseDeploymentError, match="plan integrity"):
        deployer.activate(forged, _consumption(forged), activated_at="2026-09-14T12:00:01+00:00")
    assert deployer.snapshot() == ()


def test_activation_cannot_precede_consumption(tmp_path):
    deployer = AtomicReleaseDeployer(tmp_path)
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    consumption = _consumption(plan, consumed_at="2026-09-14T12:00:05+00:00")

    with pytest.raises(ReleaseDeploymentError, match="before authorization consumption"):
        deployer.activate(plan, consumption, activated_at="2026-09-14T12:00:04+00:00")
    assert deployer.snapshot() == ()


def test_explicit_empty_activation_timestamp_is_not_replaced_with_now(tmp_path):
    deployer = AtomicReleaseDeployer(tmp_path)
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    with pytest.raises(ReleaseDeploymentError, match="timestamp"):
        deployer.activate(plan, _consumption(plan), activated_at="")
    assert deployer.snapshot() == ()


@pytest.mark.parametrize(
    "consumption",
    [
        DeploymentConsumption("", "2026-09-14T12:00:00+00:00", "a" * 64, "c" * 64, "b" * 64),
        DeploymentConsumption("auth", "not-a-time", "a" * 64, "c" * 64, "b" * 64),
        DeploymentConsumption("auth", "2026-09-14T12:00:00+00:00", "bad-root", "c" * 64, "b" * 64),
        DeploymentConsumption("auth", "2026-09-14T12:00:00+00:00", "a" * 64, "c" * 64, "bad-event"),
    ],
)
def test_malformed_consumption_evidence_fails_before_append(tmp_path, consumption):
    deployer = AtomicReleaseDeployer(tmp_path)
    plan = compile_deployment_plan({"artifact": "sha256:a", "environment": "staging"})
    if consumption.plan_sha256 == "c" * 64:
        consumption = DeploymentConsumption(
            consumption.authorization_id,
            consumption.consumed_at,
            consumption.system_root_sha256,
            plan_digest(plan),
            consumption.consume_event_sha256,
        )

    with pytest.raises(ReleaseDeploymentError):
        deployer.activate(plan, consumption, activated_at="2026-09-14T12:00:01+00:00")
    assert deployer.snapshot() == ()


def test_current_pointer_tampering_is_detected(tmp_path):
    deployer, _, _, _, current_path = _activated(tmp_path)
    envelope = json.loads(current_path.read_text(encoding="utf-8"))
    envelope["release"]["artifact"] = "sha256:tampered"
    current_path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ReleaseDeploymentError, match="checksum"):
        deployer.current(target="runtime", environment="staging")


def test_rehashed_extra_release_field_is_rejected(tmp_path):
    _, _, _, history_path, _ = _activated(tmp_path)
    row = json.loads(history_path.read_text(encoding="utf-8"))
    row["operator_override"] = True
    row = _rehash_record(row)
    history_path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseDeploymentError, match="schema mismatch"):
        AtomicReleaseDeployer(tmp_path).snapshot()


def test_rehashed_boolean_sequence_is_not_coerced_to_one(tmp_path):
    _, _, _, history_path, _ = _activated(tmp_path)
    row = json.loads(history_path.read_text(encoding="utf-8"))
    row["sequence"] = True
    row = _rehash_record(row)
    history_path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseDeploymentError, match="sequence malformed"):
        AtomicReleaseDeployer(tmp_path).snapshot()


def test_rehashed_boolean_version_is_not_coerced_to_one(tmp_path):
    _, _, _, history_path, _ = _activated(tmp_path)
    row = json.loads(history_path.read_text(encoding="utf-8"))
    row["version"] = True
    payload = {key: value for key, value in row.items() if key != "sha256"}
    row["sha256"] = canonical_json_sha256(payload)
    history_path.write_text(canonical_json_text(row) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseDeploymentError, match="version malformed"):
        AtomicReleaseDeployer(tmp_path).snapshot()


def test_rehashed_nonfinite_release_value_is_rejected(tmp_path):
    _, _, _, history_path, _ = _activated(tmp_path)
    row = json.loads(history_path.read_text(encoding="utf-8"))
    row["forged_metric"] = float("nan")
    row = _rehash_record(row)
    history_path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(ReleaseDeploymentError, match="schema mismatch"):
        AtomicReleaseDeployer(tmp_path).snapshot()


def test_resealed_current_envelope_extension_is_rejected(tmp_path):
    deployer, _, _, _, current_path = _activated(tmp_path)
    envelope = json.loads(current_path.read_text(encoding="utf-8"))
    envelope["operator_override"] = "force"
    payload = {"version": envelope["version"], "release": envelope["release"]}
    envelope["sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    current_path.write_text(json.dumps(envelope, sort_keys=True, separators=(",", ":")), encoding="utf-8")

    with pytest.raises(ReleaseDeploymentError, match="envelope schema mismatch"):
        deployer.current(target="runtime", environment="staging")


def test_boolean_current_envelope_version_is_rejected_even_if_resealed(tmp_path):
    deployer, _, _, _, current_path = _activated(tmp_path)
    envelope = json.loads(current_path.read_text(encoding="utf-8"))
    envelope["version"] = True
    payload = {"version": envelope["version"], "release": envelope["release"]}
    envelope["sha256"] = canonical_json_sha256(payload)
    current_path.write_text(canonical_json_text(envelope), encoding="utf-8")

    with pytest.raises(ReleaseDeploymentError, match="version malformed"):
        deployer.current(target="runtime", environment="staging")


def test_current_lookup_rejects_whitespace_aliases(tmp_path):
    deployer, _, _, _, _ = _activated(tmp_path)
    with pytest.raises(ValueError, match="canonical"):
        deployer.current(target=" runtime", environment="staging")
    with pytest.raises(ValueError, match="canonical"):
        deployer.current(target="runtime", environment="staging ")
