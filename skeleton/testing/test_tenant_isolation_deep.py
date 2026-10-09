from __future__ import annotations

import pytest

from skeleton.ai.runtime.security.tenant_isolation import (
    TenantBoundary,
    TenantIsolationError,
    TenantScope,
    authorize_tenant_access,
)


def scope(**changes: object) -> TenantScope:
    values=dict(
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        subject_id="subject-a",
        resource_prefix="tenant-a:workspace-a:",
    )
    values.update(changes)
    return TenantScope(**values)


def resource(**changes: object) -> TenantBoundary:
    values=dict(
        resource_id="tenant-a:workspace-a:memory:1",
        tenant_id="tenant-a",
        workspace_id="workspace-a",
        classification="internal",
    )
    values.update(changes)
    return TenantBoundary(**values)


def test_same_tenant_workspace_and_resource_scope_is_allowed() -> None:
    decision=authorize_tenant_access(scope(),resource(),operation="read")
    assert decision.allowed is True
    assert decision.reason_code=="authorized"


def test_cross_tenant_access_fails_closed_before_lookup_authority() -> None:
    decision=authorize_tenant_access(
        scope(),
        resource(tenant_id="tenant-b"),
        operation="read",
    )
    assert decision.allowed is False
    assert decision.reason_code=="tenant_mismatch"


def test_cross_workspace_access_fails_closed() -> None:
    decision=authorize_tenant_access(
        scope(),
        resource(workspace_id="workspace-b"),
        operation="read",
    )
    assert decision.allowed is False
    assert decision.reason_code=="workspace_mismatch"


def test_resource_prefix_confusion_is_rejected() -> None:
    decision=authorize_tenant_access(
        scope(),
        resource(resource_id="tenant-a:workspace-b:memory:1"),
        operation="read",
    )
    assert decision.allowed is False
    assert decision.reason_code=="resource_scope_mismatch"


def test_resource_prefix_contract_is_explicit() -> None:
    with pytest.raises(TenantIsolationError,match="terminate"):
        scope(resource_prefix="tenant-a:workspace-a")


def test_scope_prefix_cannot_claim_another_tenant() -> None:
    with pytest.raises(TenantIsolationError, match="bind exact tenant/workspace"):
        scope(resource_prefix="tenant-b:workspace-a:")


def test_scope_prefix_cannot_claim_another_workspace() -> None:
    with pytest.raises(TenantIsolationError, match="bind exact tenant/workspace"):
        scope(resource_prefix="tenant-a:workspace-b:")


def test_tenant_identifiers_must_not_contain_scope_delimiters() -> None:
    with pytest.raises(TenantIsolationError, match="resource delimiters"):
        scope(tenant_id="tenant-a:workspace-b")


def test_resource_key_must_match_tenant_metadata_before_authorization() -> None:
    decision = authorize_tenant_access(
        scope(),
        resource(resource_id="tenant-b:workspace-a:memory:1"),
        operation="read",
    )
    assert decision.allowed is False
    assert decision.reason_code == "resource_scope_mismatch"


def test_narrowed_resource_prefix_limits_access_within_tenant() -> None:
    scoped = scope(resource_prefix="tenant-a:workspace-a:memory:")
    valid = authorize_tenant_access(scoped, resource(), operation="read")
    denied = authorize_tenant_access(
        scoped,
        resource(resource_id="tenant-a:workspace-a:document:1"),
        operation="read",
    )
    assert valid.allowed is True
    assert denied.allowed is False
    assert denied.reason_code == "resource_scope_mismatch"
