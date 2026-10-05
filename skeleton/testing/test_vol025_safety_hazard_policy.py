from __future__ import annotations

import hashlib

import pytest

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.contracts.safety_hazards import (
    DEFAULT_SAFETY_HAZARD_MANIFEST,
    DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST,
    DEFAULT_SAFETY_POLICY_ID,
    DEFAULT_SAFETY_POLICY_VERSION,
    SafetyHazardClass,
    SafetyHazardError,
    SafetyHazardManifest,
    SafetyHazardSeverity,
)


def _hazard_id(kind: SafetyHazardClass) -> str:
    return next(
        item.hazard_id
        for item in DEFAULT_SAFETY_HAZARD_MANIFEST.hazards
        if item.hazard_class is kind
    )


def test_default_manifest_is_complete_versioned_and_non_authoritative() -> None:
    expected = {
        SafetyHazardClass.AUTHORITY_ESCALATION,
        SafetyHazardClass.IRREVERSIBLE_SIDE_EFFECT,
        SafetyHazardClass.CROSS_TENANT_IMPACT,
        SafetyHazardClass.SENSITIVE_DATA_EXPOSURE,
        SafetyHazardClass.POLICY_CONFLICT,
        SafetyHazardClass.SPECIFICATION_GAMING,
        SafetyHazardClass.DECEPTIVE_BEHAVIOR,
        SafetyHazardClass.GOAL_DRIFT,
        SafetyHazardClass.RECOVERY_FAILURE,
        SafetyHazardClass.UNRESOLVED_COUNTEREXAMPLE,
    }

    assert DEFAULT_SAFETY_HAZARD_MANIFEST.policy_id == DEFAULT_SAFETY_POLICY_ID
    assert (
        DEFAULT_SAFETY_HAZARD_MANIFEST.policy_version
        == DEFAULT_SAFETY_POLICY_VERSION
    )
    assert {
        item.hazard_class
        for item in DEFAULT_SAFETY_HAZARD_MANIFEST.hazards
    } == expected
    assert DEFAULT_SAFETY_HAZARD_MANIFEST.authority_scope == "safety-policy-only"
    assert all(item.blocking for item in DEFAULT_SAFETY_HAZARD_MANIFEST.hazards)
    assert all(
        item.severity in {SafetyHazardSeverity.HIGH, SafetyHazardSeverity.CRITICAL}
        for item in DEFAULT_SAFETY_HAZARD_MANIFEST.hazards
    )
    assert DEFAULT_SAFETY_HAZARD_MANIFEST.payload()["production_authority"] is False


def test_manifest_identity_uses_shared_canonical_contract_bytes() -> None:
    expected = hashlib.sha256(
        canonical_json_bytes(DEFAULT_SAFETY_HAZARD_MANIFEST.payload())
    ).hexdigest()

    assert DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST == expected
    assert DEFAULT_SAFETY_HAZARD_MANIFEST.manifest_digest == expected


def test_hazard_identity_is_content_addressed() -> None:
    hazard = DEFAULT_SAFETY_HAZARD_MANIFEST.hazards[0]
    expected = hashlib.sha256(canonical_json_bytes(hazard.payload())).hexdigest()

    assert hazard.hazard_digest == expected
    assert hazard.hazard_id.startswith("HZ-")


def test_runtime_signal_projection_returns_only_declared_hazards() -> None:
    observed = DEFAULT_SAFETY_HAZARD_MANIFEST.hazards_for_signals(
        (
            "action.privileged",
            "alignment.goal_drift",
            "scope.cross_tenant",
        )
    )

    assert observed == tuple(sorted(observed))
    assert _hazard_id(SafetyHazardClass.AUTHORITY_ESCALATION) in observed
    assert _hazard_id(SafetyHazardClass.GOAL_DRIFT) in observed
    assert _hazard_id(SafetyHazardClass.CROSS_TENANT_IMPACT) in observed
    assert _hazard_id(SafetyHazardClass.SENSITIVE_DATA_EXPOSURE) not in observed


def test_unrelated_signal_does_not_invent_hazard() -> None:
    assert DEFAULT_SAFETY_HAZARD_MANIFEST.hazards_for_signals(
        ("runtime.unrelated",)
    ) == ()


def test_signal_set_must_be_canonical() -> None:
    with pytest.raises(SafetyHazardError, match="sorted unique"):
        DEFAULT_SAFETY_HAZARD_MANIFEST.hazards_for_signals(
            ("scope.cross_tenant", "action.privileged")
        )
    with pytest.raises(SafetyHazardError, match="sorted unique"):
        DEFAULT_SAFETY_HAZARD_MANIFEST.hazards_for_signals(
            ("action.privileged", "action.privileged")
        )


def test_manifest_hazard_order_is_fail_closed() -> None:
    with pytest.raises(SafetyHazardError, match="sorted by unique hazard_id"):
        SafetyHazardManifest(
            policy_id=DEFAULT_SAFETY_POLICY_ID,
            policy_version=DEFAULT_SAFETY_POLICY_VERSION,
            hazards=tuple(reversed(DEFAULT_SAFETY_HAZARD_MANIFEST.hazards)),
        )


def test_manifest_cannot_grant_execution_authority() -> None:
    with pytest.raises(SafetyHazardError, match="cannot grant execution authority"):
        SafetyHazardManifest(
            policy_id=DEFAULT_SAFETY_POLICY_ID,
            policy_version=DEFAULT_SAFETY_POLICY_VERSION,
            hazards=DEFAULT_SAFETY_HAZARD_MANIFEST.hazards,
            authority_scope="execution-authority",
        )


def test_policy_version_changes_manifest_identity() -> None:
    next_version = SafetyHazardManifest(
        policy_id=DEFAULT_SAFETY_POLICY_ID,
        policy_version=DEFAULT_SAFETY_POLICY_VERSION + 1,
        hazards=DEFAULT_SAFETY_HAZARD_MANIFEST.hazards,
    )

    assert next_version.manifest_digest != DEFAULT_SAFETY_HAZARD_MANIFEST_DIGEST


def test_safety_hazard_source_and_ai_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/contracts/safety_hazards.py"
    mirror = root / "skeleton/ai/runtime/contracts/safety_hazards.py"

    assert source.read_bytes() == mirror.read_bytes()


def test_contract_init_source_and_ai_mirror_remain_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/contracts/__init__.py"
    mirror = root / "skeleton/ai/runtime/contracts/__init__.py"

    assert source.read_bytes() == mirror.read_bytes()
