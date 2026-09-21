from __future__ import annotations

import pytest

from skeleton.vault.data_governance import DataGovernanceDenied
from skeleton.vault.data_lifecycle import (
    DataLifecycleRegistry,
    GovernedDataRecord,
)
from skeleton.vault.governance_registry import GovernanceRegistry


def _record(
    record_id: str,
    *,
    tenant: str = "tenant-a",
    data_class: str = "internal",
    purposes: tuple[str, ...] = ("model-inference",),
    targets: tuple[str, ...] = ("memory",),
) -> GovernedDataRecord:
    return GovernedDataRecord(
        record_id=record_id,
        tenant_id=tenant,
        owner_plane="memory",
        source_ref=f"memory:{record_id}",
        data_class=data_class,
        purposes=purposes,
        deletion_targets=targets,
        created_at=10.0,
    )


def test_registry_uses_most_restrictive_classification() -> None:
    registry = GovernanceRegistry()
    registry.register(_record("internal", data_class="internal"))
    registry.register(_record("confidential", data_class="confidential"))

    context = registry.context_for(
        ("internal", "confidential"),
        tenant_id="tenant-a",
        purpose="model-inference",
    )

    assert context.data_class.label == "confidential"
    assert context.routing_privacy == "sensitive"
    assert context.record_ids == ("internal", "confidential")


def test_registry_denies_cross_tenant_record_mixing() -> None:
    registry = GovernanceRegistry()
    registry.register(_record("a", tenant="tenant-a"))
    registry.register(_record("b", tenant="tenant-b"))

    with pytest.raises(DataGovernanceDenied, match="cross-tenant"):
        registry.context_for(
            ("a", "b"),
            tenant_id="tenant-a",
            purpose="model-inference",
        )


def test_registry_requires_purpose_registered_on_every_record() -> None:
    registry = GovernanceRegistry()
    registry.register(
        _record(
            "retrieval",
            purposes=("retrieval-synthesis",),
        )
    )

    with pytest.raises(DataGovernanceDenied, match="purpose_not_registered"):
        registry.context_for(
            ("retrieval",),
            tenant_id="tenant-a",
            purpose="model-inference",
        )


def test_registry_denies_restricted_external_provider_transfer() -> None:
    registry = GovernanceRegistry()
    registry.register(_record("secret", data_class="restricted"))

    decision = registry.evaluate_provider_transfer(
        "openai",
        record_ids=("secret",),
        tenant_id="tenant-a",
        purpose="model-inference",
    )

    assert decision.permitted is False
    assert decision.data_class == "restricted"
    assert decision.routing_privacy == "local-only"
    assert decision.reason_code == "restricted_external_transfer_denied"

    with pytest.raises(
        DataGovernanceDenied,
        match="restricted_external_transfer_denied",
    ):
        registry.require_provider_transfer(
            "openai",
            record_ids=("secret",),
            tenant_id="tenant-a",
            purpose="model-inference",
        )


def test_registry_provider_receipt_is_stable_and_record_bound() -> None:
    registry = GovernanceRegistry()
    registry.register(_record("a"))
    registry.register(_record("b"))

    first = registry.require_provider_transfer(
        "openai",
        record_ids=("a", "b"),
        tenant_id="tenant-a",
        purpose="model-inference",
    )
    second = registry.require_provider_transfer(
        "openai",
        record_ids=("a", "b"),
        tenant_id="tenant-a",
        purpose="model-inference",
    )

    assert first == second
    assert first.permitted is True
    assert first.record_ids == ("a", "b")
    assert first.decision_id.startswith("govr-")


def test_registry_refuses_pending_or_deleted_record_transfer() -> None:
    lifecycle = DataLifecycleRegistry()
    registry = GovernanceRegistry(lifecycle)
    registry.register(_record("a"))

    plan = registry.request_deletion(
        "tenant-a",
        record_ids=("a",),
        now=20.0,
    )

    with pytest.raises(DataGovernanceDenied, match="not active"):
        registry.context_for(
            ("a",),
            tenant_id="tenant-a",
            purpose="model-inference",
        )

    registry.acknowledge_deletion(
        plan.plan_id,
        "a",
        "memory",
        now=21.0,
    )

    with pytest.raises(DataGovernanceDenied, match="not active"):
        registry.context_for(
            ("a",),
            tenant_id="tenant-a",
            purpose="model-inference",
        )


def test_registry_inventory_and_retention_are_same_authority() -> None:
    registry = GovernanceRegistry()
    registry.register(
        GovernedDataRecord(
            record_id="expires",
            tenant_id="tenant-a",
            owner_plane="retrieval",
            source_ref="retrieval:expires",
            data_class="confidential",
            purposes=("retrieval-synthesis",),
            deletion_targets=("memory", "artifact"),
            created_at=10.0,
            retention_until=15.0,
        )
    )

    assert registry.export_inventory("tenant-a")["count"] == 1
    plans = registry.plan_retention_expiry(now=20.0)
    assert len(plans) == 1
    assert plans[0].tenant_id == "tenant-a"
    assert {action.target for action in plans[0].actions} == {
        "memory",
        "artifact",
    }
