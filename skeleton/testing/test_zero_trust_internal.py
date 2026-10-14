from __future__ import annotations

import hashlib

import pytest

from skeleton.security.zero_trust import (
    InternalGrant,
    TrustDecision,
    TrustError,
    WorkloadIdentity,
    authorize,
    revalidate,
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


IDENTITY = WorkloadIdentity("WORKLOAD.API", "INSTANCE.1", sha("attest"))
GRANT = InternalGrant(
    "GRANT.1",
    "WORKLOAD.API",
    "INSTANCE.1",
    IDENTITY.attestation_digest,
    frozenset({"read", "write"}),
    "tenant/a/",
    0,
    100,
)


def test_exact_workload_identity_and_least_privilege_grant() -> None:
    decision = authorize(IDENTITY, GRANT, "read", "tenant/a/item", 10)
    assert decision.allowed
    assert decision.action == "read"
    assert decision.resource == "tenant/a/item"


def test_instance_identity_cannot_be_replayed() -> None:
    other = WorkloadIdentity("WORKLOAD.API", "INSTANCE.2", sha("attest2"))
    assert not authorize(other, GRANT, "read", "tenant/a/item", 10).allowed


def test_action_and_resource_scope_fail_closed() -> None:
    assert not authorize(IDENTITY, GRANT, "delete", "tenant/a/item", 10).allowed
    assert not authorize(IDENTITY, GRANT, "read", "tenant/b/item", 10).allowed


def test_long_running_authority_has_revalidation_deadline() -> None:
    decision = authorize(
        IDENTITY,
        GRANT,
        "read",
        "tenant/a/item",
        10,
        revalidation_interval=7,
    )
    assert decision.revalidate_at == 17


def test_expired_grant_denied() -> None:
    assert not authorize(IDENTITY, GRANT, "read", "tenant/a/item", 100).allowed


def test_revalidation_preserves_exact_action_and_resource() -> None:
    original = authorize(IDENTITY, GRANT, "write", "tenant/a/item/42", 10)
    refreshed = revalidate(IDENTITY, GRANT, original, 15, revalidation_interval=7)
    assert refreshed.allowed
    assert refreshed.action == "write"
    assert refreshed.resource == "tenant/a/item/42"
    assert refreshed.revalidate_at == 22


def test_revalidation_fails_closed_when_grant_scope_changes() -> None:
    original = authorize(IDENTITY, GRANT, "write", "tenant/a/item", 10)
    reduced = InternalGrant(
        "GRANT.1",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read"}),
        "tenant/a/",
        0,
        100,
    )
    refreshed = revalidate(IDENTITY, reduced, original, 15)
    assert not refreshed.allowed
    assert refreshed.reason == "least_privilege_denied"
    assert refreshed.action is None
    assert refreshed.resource is None


def test_revalidation_rejects_different_grant_identity() -> None:
    original = authorize(IDENTITY, GRANT, "read", "tenant/a/item", 10)
    replacement = InternalGrant(
        "GRANT.2",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read"}),
        "tenant/a/",
        0,
        100,
    )
    with pytest.raises(TrustError, match="invalid prior decision"):
        revalidate(IDENTITY, replacement, original, 15)


def test_denied_decision_cannot_smuggle_authority() -> None:
    with pytest.raises(TrustError, match="denied decision cannot carry authority"):
        TrustDecision(False, "denied", "GRANT.1", IDENTITY.attestation_digest, "read", "tenant/a/item", 20)


def test_boolean_ticks_and_unbounded_actions_are_rejected() -> None:
    with pytest.raises(TrustError, match="now must be bounded"):
        authorize(IDENTITY, GRANT, "read", "tenant/a/item", True)
    with pytest.raises(TrustError, match="grant action"):
        InternalGrant(
            "GRANT.2",
            "WORKLOAD.API",
            "INSTANCE.1",
            IDENTITY.attestation_digest,
            frozenset(f"action{i}" for i in range(257)),
            "tenant/a/",
            0,
            100,
        )


def test_resource_prefix_requires_path_boundary() -> None:
    scoped = InternalGrant(
        "GRANT.PATH",
        "WORKLOAD.API",
        "INSTANCE.1",
        IDENTITY.attestation_digest,
        frozenset({"read"}),
        "tenant/a",
        0,
        100,
    )
    assert authorize(IDENTITY, scoped, "read", "tenant/a", 10).allowed
    assert authorize(IDENTITY, scoped, "read", "tenant/a/item", 10).allowed
    denied = authorize(IDENTITY, scoped, "read", "tenant/a-evil/item", 10)
    assert not denied.allowed
    assert denied.reason == "least_privilege_denied"


def test_rotated_attestation_cannot_reuse_existing_grant() -> None:
    rotated = WorkloadIdentity("WORKLOAD.API", "INSTANCE.1", sha("rotated-attestation"))
    denied = authorize(rotated, GRANT, "read", "tenant/a/item", 10)
    assert not denied.allowed
    assert denied.reason == "attestation_mismatch"


def test_revalidation_detects_attestation_rotation() -> None:
    original = authorize(IDENTITY, GRANT, "read", "tenant/a/item", 10)
    rotated = WorkloadIdentity("WORKLOAD.API", "INSTANCE.1", sha("rotated-attestation"))
    denied = revalidate(rotated, GRANT, original, 15)
    assert not denied.allowed
    assert denied.reason == "attestation_mismatch"
    assert denied.grant_id is None
