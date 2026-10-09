from __future__ import annotations

import pytest

from skeleton.ai.runtime.security.boundaries import (
    BoundaryCrossing,
    SecurityBoundary,
    SecurityBoundaryError,
    evaluate_boundary,
)


def boundary() -> SecurityBoundary:
    return SecurityBoundary(
        boundary_id="BOUNDARY.TOOL",
        source_zone="planner",
        target_zone="tool-runtime",
        required_authn="workload-identity",
        required_scopes=("tool:invoke", "resource:repo"),
    )


def crossing(**changes: object) -> BoundaryCrossing:
    values = dict(
        crossing_id="cross-1",
        boundary_id="BOUNDARY.TOOL",
        subject_id="subject-a",
        workload_id="worker-a",
        resource_id="repo:Skeleton",
        authenticated_identity="spiffe://skeleton/worker-a",
        granted_scopes=("tool:invoke", "resource:repo", "trace:write"),
        requested_action="repo.read",
    )
    values.update(changes)
    return BoundaryCrossing(**values)


def test_authenticated_authorized_crossing_is_allowed() -> None:
    decision=evaluate_boundary(boundary(),crossing())
    assert decision.allowed is True
    assert decision.reason_code=="authorized"
    assert decision.effective_scopes==("resource:repo","tool:invoke")


def test_missing_authentication_fails_closed() -> None:
    decision=evaluate_boundary(boundary(),crossing(authenticated_identity=None))
    assert decision.allowed is False
    assert decision.reason_code=="authentication_missing"
    assert decision.effective_scopes==()


def test_missing_scope_fails_closed_without_scope_retention() -> None:
    decision=evaluate_boundary(
        boundary(),
        crossing(granted_scopes=("tool:invoke",)),
    )
    assert decision.allowed is False
    assert decision.reason_code=="scope_missing"
    assert decision.effective_scopes==()


def test_boundary_identity_mismatch_fails_closed() -> None:
    decision=evaluate_boundary(boundary(),crossing(boundary_id="BOUNDARY.OTHER"))
    assert decision.allowed is False
    assert decision.reason_code=="boundary_mismatch"


def test_allow_by_default_boundary_is_forbidden() -> None:
    with pytest.raises(SecurityBoundaryError,match="default action"):
        SecurityBoundary(
            "unsafe",
            "a",
            "b",
            "authn",
            ("scope",),
            default_action="allow",
        )


def test_presented_workload_identity_must_match_crossing_workload() -> None:
    decision = evaluate_boundary(
        boundary(), crossing(authenticated_identity="spiffe://skeleton/worker-b")
    )
    assert decision.allowed is False
    assert decision.reason_code == "authentication_identity_mismatch"
    assert decision.effective_scopes == ()


def test_changed_workload_id_cannot_reuse_other_workload_identity() -> None:
    decision = evaluate_boundary(boundary(), crossing(workload_id="worker-b"))
    assert decision.allowed is False
    assert decision.reason_code == "authentication_identity_mismatch"


def test_unsupported_authentication_methods_do_not_default_to_allow() -> None:
    unsupported = SecurityBoundary(
        boundary_id="BOUNDARY.TOOL",
        source_zone="planner",
        target_zone="tool-runtime",
        required_authn="unverified-header",
        required_scopes=("tool:invoke", "resource:repo"),
    )
    decision = evaluate_boundary(unsupported, crossing())
    assert decision.allowed is False
    assert decision.reason_code == "authentication_method_unsupported"
    assert decision.effective_scopes == ()
