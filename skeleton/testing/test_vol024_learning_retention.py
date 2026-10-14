from __future__ import annotations

import hashlib

import pytest

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.eval.failure_knowledge import LearningSignal, LearningSignalKind
from skeleton.eval.learning_retention import (
    LearningRetentionError,
    LearningSignalRetentionPolicy,
    register_learning_signal_lifecycle,
)
from skeleton.vault.data_governance import DataClass
from skeleton.vault.data_lifecycle import DataLifecycleRegistry


def _signal() -> LearningSignal:
    return LearningSignal(
        record_digest="1" * 64,
        failure_fingerprint="2" * 64,
        risk_obligation_digest="3" * 64,
        signal_kind=LearningSignalKind.REGRESSION_REINFORCEMENT,
        target_regression_case_digest="4" * 64,
        non_applicability_digest=None,
    )


def _policy(**overrides) -> LearningSignalRetentionPolicy:
    values = {
        "policy_id": "learn24-default",
        "data_class": DataClass.CONFIDENTIAL,
        "retention_seconds": 3600,
        "deletion_targets": ("evaluation-cache", "failure-knowledge"),
        "region": "EEA",
        "exportable": False,
    }
    values.update(overrides)
    return LearningSignalRetentionPolicy(**values)


def test_learning_signal_is_registered_as_metadata_only() -> None:
    registry = DataLifecycleRegistry()
    signal = _signal()
    policy = _policy()

    binding = register_learning_signal_lifecycle(
        registry=registry,
        signal=signal,
        tenant_id="tenant-a",
        policy=policy,
        created_at=100.0,
    )

    row = registry.get(binding.record_id)
    assert row["tenant_id"] == "tenant-a"
    assert row["data_class"] == "confidential"
    assert row["retention_until"] == 3700.0
    assert row["exportable"] is False
    assert row["source_ref"] == f"learning-signal://{signal.signal_digest}"
    assert "payload" not in row
    assert binding.payload_persisted is False


def test_retention_expiry_uses_existing_lifecycle_deletion_plane() -> None:
    registry = DataLifecycleRegistry()
    binding = register_learning_signal_lifecycle(
        registry=registry,
        signal=_signal(),
        tenant_id="tenant-a",
        policy=_policy(retention_seconds=10),
        created_at=100.0,
    )

    assert registry.plan_retention_expiry(now=109.0) == ()
    plans = registry.plan_retention_expiry(now=110.0)

    assert len(plans) == 1
    assert plans[0].tenant_id == "tenant-a"
    assert {
        (action.record_id, action.target)
        for action in plans[0].actions
    } == {
        (binding.record_id, "evaluation-cache"),
        (binding.record_id, "failure-knowledge"),
    }


def test_policy_identity_uses_shared_canonical_contract_bytes() -> None:
    policy = _policy()
    assert policy.policy_digest == hashlib.sha256(
        canonical_json_bytes(policy.payload())
    ).hexdigest()


def test_restricted_learning_signal_cannot_be_exportable() -> None:
    with pytest.raises(
        LearningRetentionError,
        match="restricted learning signals cannot be exportable",
    ):
        _policy(data_class=DataClass.RESTRICTED, exportable=True)


@pytest.mark.parametrize("seconds", [0, -1, 315360001])
def test_retention_must_be_finite_and_bounded(seconds: int) -> None:
    with pytest.raises(LearningRetentionError, match="outside bounded policy"):
        _policy(retention_seconds=seconds)


def test_region_must_resolve_to_registered_privacy_policy() -> None:
    with pytest.raises(LearningRetentionError, match="region is not governed"):
        _policy(region="unknown")


def test_deletion_targets_must_be_sorted_unique_canonical_tuple() -> None:
    with pytest.raises(LearningRetentionError, match="canonical"):
        _policy(deletion_targets=("failure-knowledge", "evaluation-cache"))
    with pytest.raises(LearningRetentionError, match="sorted unique"):
        _policy(deletion_targets=("evaluation-cache", "evaluation-cache"))


def test_registration_is_tenant_scoped() -> None:
    registry = DataLifecycleRegistry()
    first = register_learning_signal_lifecycle(
        registry=registry,
        signal=_signal(),
        tenant_id="tenant-a",
        policy=_policy(),
        created_at=100.0,
    )

    assert registry.inventory("tenant-a")[0]["record_id"] == first.record_id
    assert registry.inventory("tenant-b") == ()


def test_learning_retention_source_and_ai_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/eval/learning_retention.py"
    mirror = root / "skeleton/ai/evaluation/learning_retention.py"

    assert source.read_bytes() == mirror.read_bytes()


def test_eval_init_source_and_ai_mirror_remain_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/eval/__init__.py"
    mirror = root / "skeleton/ai/evaluation/__init__.py"

    assert source.read_bytes() == mirror.read_bytes()


def test_learning_signal_lifecycle_survives_registry_restart(tmp_path) -> None:
    path = tmp_path / "learning-retention.sqlite3"
    first = DataLifecycleRegistry(path)
    binding = register_learning_signal_lifecycle(
        registry=first,
        signal=_signal(),
        tenant_id="tenant-a",
        policy=_policy(retention_seconds=10),
        created_at=100.0,
    )
    first.close()

    restarted = DataLifecycleRegistry(path)
    row = restarted.get(binding.record_id)
    assert row["tenant_id"] == "tenant-a"
    assert row["retention_until"] == 110.0
    assert row["source_ref"] == f"learning-signal://{binding.signal_digest}"

    plans = restarted.plan_retention_expiry(now=110.0)
    assert len(plans) == 1
    assert plans[0].tenant_id == "tenant-a"
    restarted.close()
