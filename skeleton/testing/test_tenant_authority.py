from __future__ import annotations

import pytest

from skeleton.security.tenant_authority import (
    ArtifactAuthority,
    DeadLetterEnvelope,
    TenantAuthorityError,
    payload_digest,
    tenant_cache_key,
)


def test_cache_key_changes_across_tenant_and_workspace_boundaries() -> None:
    base = tenant_cache_key(
        tenant_id="tenant-a",
        workspace_id="workspace-1",
        namespace="retrieval",
        logical_key="query-42",
    )
    other_tenant = tenant_cache_key(
        tenant_id="tenant-b",
        workspace_id="workspace-1",
        namespace="retrieval",
        logical_key="query-42",
    )
    other_workspace = tenant_cache_key(
        tenant_id="tenant-a",
        workspace_id="workspace-2",
        namespace="retrieval",
        logical_key="query-42",
    )

    assert base != other_tenant
    assert base != other_workspace
    assert other_tenant != other_workspace


def test_dead_letter_replay_requires_exact_tenant_workspace_and_payload() -> None:
    digest = payload_digest({"operation": "retry", "value": 7})
    envelope = DeadLetterEnvelope(
        "message-1",
        "tenant-a",
        "workspace-1",
        digest,
    )

    envelope.authorize_replay(
        tenant_id="tenant-a",
        workspace_id="workspace-1",
        payload_digest=digest,
    )

    with pytest.raises(TenantAuthorityError, match="tenant mismatch"):
        envelope.authorize_replay(
            tenant_id="tenant-b",
            workspace_id="workspace-1",
            payload_digest=digest,
        )
    with pytest.raises(TenantAuthorityError, match="workspace mismatch"):
        envelope.authorize_replay(
            tenant_id="tenant-a",
            workspace_id="workspace-2",
            payload_digest=digest,
        )
    with pytest.raises(TenantAuthorityError, match="payload identity"):
        envelope.authorize_replay(
            tenant_id="tenant-a",
            workspace_id="workspace-1",
            payload_digest="0" * 64,
        )


def test_artifact_acl_is_tenant_and_workspace_scoped() -> None:
    authority = ArtifactAuthority(
        "artifact-1",
        "tenant-a",
        "workspace-1",
        "a" * 64,
    )

    assert authority.authorize(
        tenant_id="tenant-a",
        workspace_id="workspace-1",
    ) == "a" * 64

    with pytest.raises(TenantAuthorityError, match="tenant mismatch"):
        authority.authorize(
            tenant_id="tenant-b",
            workspace_id="workspace-1",
        )
    with pytest.raises(TenantAuthorityError, match="workspace mismatch"):
        authority.authorize(
            tenant_id="tenant-a",
            workspace_id="workspace-2",
        )


def test_payload_digest_is_canonical_and_fails_closed_on_nan() -> None:
    assert payload_digest({"b": 2, "a": 1}) == payload_digest({"a": 1, "b": 2})
    with pytest.raises(ValueError, match="finite canonical JSON"):
        payload_digest({"value": float("nan")})


def test_same_logical_key_cannot_collide_across_authority_boundaries() -> None:
    keys = {
        tenant_cache_key(
            tenant_id=f"tenant-{tenant}",
            workspace_id=f"workspace-{workspace}",
            namespace="cache",
            logical_key="same",
        )
        for tenant in range(8)
        for workspace in range(8)
    }
    assert len(keys) == 64


@pytest.mark.parametrize(
    "field",
    ["tenant_id", "workspace_id", "namespace", "logical_key"],
)
def test_cache_key_rejects_noncanonical_identity(field: str) -> None:
    kwargs = {
        "tenant_id": "tenant-a",
        "workspace_id": "workspace-a",
        "namespace": "cache",
        "logical_key": "key",
    }
    kwargs[field] = " bad "
    with pytest.raises(ValueError):
        tenant_cache_key(**kwargs)
