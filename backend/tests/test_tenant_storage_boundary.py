from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.operation_projection import (
    resync_projection,
    verify_projection_authority,
)
from core.tenant_storage_boundary import (
    StorageDataClass,
    StoragePermission,
    StorageSurface,
    TenantStorageBoundaryError,
    TenantStorageContext,
    evaluate_tenant_storage,
    require_tenant_storage,
    tenant_storage_namespace,
)
from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.persistence.operation_store import StoredOperation


def _context(
    *,
    tenant_id: str = "tenant-a",
    data_class: StorageDataClass = StorageDataClass.TENANT_CACHE,
    surface: StorageSurface = StorageSurface.DEVICE_CACHE,
    permissions: tuple[str, ...] = ("read", "write", "delete"),
) -> TenantStorageContext:
    return TenantStorageContext(
        tenant_id=tenant_id,
        principal_id="principal-a",
        granted_permissions=permissions,
        data_class=data_class,
        surface=surface,
        purpose="jeeves-workspace",
    )


def test_device_cache_allows_tenant_bound_workspace_cache() -> None:
    context = _context()

    decision = require_tenant_storage(
        context=context,
        verified_tenant_id="tenant-a",
        requested_permission=StoragePermission.WRITE,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.namespace == context.namespace
    assert decision.context_digest == context.context_digest
    assert decision.accepted_evidence_ref().category == (
        "tenant_storage_boundary"
    )


def test_verified_tenant_mismatch_fails_closed() -> None:
    context = _context()

    decision = evaluate_tenant_storage(
        context=context,
        verified_tenant_id="tenant-b",
        requested_permission=StoragePermission.READ,
    )

    assert decision.accepted is False
    assert "verified-tenant-mismatch" in decision.reasons
    with pytest.raises(
        TenantStorageBoundaryError,
        match="cannot become evidence",
    ):
        decision.accepted_evidence_ref()


def test_ungranted_permission_fails_closed() -> None:
    context = _context(permissions=("read",))

    decision = evaluate_tenant_storage(
        context=context,
        verified_tenant_id=context.tenant_id,
        requested_permission=StoragePermission.WRITE,
    )

    assert decision.accepted is False
    assert "permission-not-granted" in decision.reasons


@pytest.mark.parametrize(
    "data_class",
    (
        StorageDataClass.ATTACHMENT_BYTES,
        StorageDataClass.CREDENTIAL,
    ),
)
def test_device_cache_rejects_sensitive_transient_classes(
    data_class: StorageDataClass,
) -> None:
    context = _context(data_class=data_class)

    decision = evaluate_tenant_storage(
        context=context,
        verified_tenant_id=context.tenant_id,
        requested_permission=StoragePermission.WRITE,
    )

    assert decision.accepted is False
    assert any(
        reason.startswith("data-class-not-allowed-on-surface:")
        for reason in decision.reasons
    )


def test_credential_is_rejected_even_from_generic_memory_contract() -> None:
    context = _context(
        data_class=StorageDataClass.CREDENTIAL,
        surface=StorageSurface.MEMORY,
    )

    decision = evaluate_tenant_storage(
        context=context,
        verified_tenant_id=context.tenant_id,
        requested_permission=StoragePermission.WRITE,
    )

    assert decision.accepted is False
    assert "credential-requires-dedicated-secure-store" in decision.reasons


def test_attachment_bytes_may_use_memory_or_explicit_server_flow() -> None:
    for surface in (
        StorageSurface.MEMORY,
        StorageSurface.CANONICAL_SERVER,
    ):
        context = _context(
            data_class=StorageDataClass.ATTACHMENT_BYTES,
            surface=surface,
        )
        decision = evaluate_tenant_storage(
            context=context,
            verified_tenant_id=context.tenant_id,
            requested_permission=StoragePermission.WRITE,
        )
        assert decision.accepted is True


def test_canonical_reference_is_allowed_in_rebuildable_device_cache() -> None:
    context = _context(
        data_class=StorageDataClass.CANONICAL_REFERENCE,
        surface=StorageSurface.DEVICE_CACHE,
    )

    decision = require_tenant_storage(
        context=context,
        verified_tenant_id=context.tenant_id,
        requested_permission=StoragePermission.WRITE,
    )

    assert decision.accepted is True


def test_namespace_is_stable_per_tenant_and_purpose() -> None:
    one = tenant_storage_namespace(
        "tenant-a",
        purpose="operation-cursor",
    )
    two = tenant_storage_namespace(
        "tenant-a",
        purpose="operation-cursor",
    )
    other_tenant = tenant_storage_namespace(
        "tenant-b",
        purpose="operation-cursor",
    )
    other_purpose = tenant_storage_namespace(
        "tenant-a",
        purpose="workspace",
    )

    assert one == two
    assert one != other_tenant
    assert one != other_purpose
    assert "tenant-a" not in one


def test_context_digest_changes_with_boundary_identity() -> None:
    context = _context()

    assert (
        replace(context, tenant_id="tenant-b").context_digest
        != context.context_digest
    )
    assert (
        replace(
            context,
            data_class=StorageDataClass.USER_DRAFT,
        ).context_digest
        != context.context_digest
    )
    assert (
        replace(
            context,
            surface=StorageSurface.CANONICAL_SERVER,
        ).context_digest
        != context.context_digest
    )


def test_require_tenant_storage_raises_with_explicit_reasons() -> None:
    context = _context(
        data_class=StorageDataClass.ATTACHMENT_BYTES,
        permissions=("read",),
    )

    with pytest.raises(
        TenantStorageBoundaryError,
        match="permission-not-granted",
    ):
        require_tenant_storage(
            context=context,
            verified_tenant_id="tenant-b",
            requested_permission=StoragePermission.WRITE,
        )

def test_storage_boundary_binds_to_durable_operation_tenant() -> None:
    now = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)
    stored = StoredOperation(
        envelope=OperationEnvelope(
            operation_id="00000000-0000-4000-8000-000000000055",
            tenant_id="tenant-a",
            actor_id="actor-a",
            capability="chat",
            created_at=now,
            deadline=now + timedelta(minutes=10),
            idempotency_key="prod-05-tenant-boundary",
            trace_id="trace-prod-05",
            state=OperationState.RUNNING,
        ),
        version=5,
        updated_at=now + timedelta(seconds=5),
    )
    projection = resync_projection(
        stored,
        stream_latest_sequence=stored.version,
    )
    authority = verify_projection_authority(projection, stored)
    assert authority.accepted is True

    accepted = require_tenant_storage(
        context=_context(tenant_id=projection.tenant_id),
        verified_tenant_id=projection.tenant_id,
        requested_permission=StoragePermission.WRITE,
    )
    assert accepted.accepted is True

    forged = evaluate_tenant_storage(
        context=_context(tenant_id="tenant-b"),
        verified_tenant_id=projection.tenant_id,
        requested_permission=StoragePermission.WRITE,
    )
    assert forged.accepted is False
    assert "verified-tenant-mismatch" in forged.reasons
