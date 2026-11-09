from __future__ import annotations

import pytest

from skeleton.vault.data_governance import DataGovernanceDenied
from skeleton.vault.data_lifecycle import (
    DataLifecycleRegistry,
    GovernedDataRecord,
    LifecycleConflict,
)
from skeleton.vault.governance_registry import (
    CanonicalDataPlane,
    GovernanceRegistry,
)
from skeleton.vault.lifecycle_adapters import (
    LifecycleAdapterRegistry,
    MemoryDeletionAdapter,
)
from skeleton.frontier.memory import InMemoryStore


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


@pytest.mark.parametrize(
    ("plane", "owner", "target"),
    [
        ("conversation", "conversation", "conversation"),
        ("memory", "memory", "memory"),
        ("retrieval", "retrieval", "retrieval"),
        ("artifact", "artifact", "artifact"),
    ],
)
def test_register_canonical_write_covers_required_planes(
    plane: str,
    owner: str,
    target: str,
) -> None:
    registry = GovernanceRegistry()

    record = registry.register_canonical_write(
        plane,
        record_id=f"{plane}-1",
        tenant_id="tenant-a",
        source_ref=f"{plane}://1",
        data_class="confidential",
        purposes=("model-inference", "verification"),
        created_at=10.0,
        retention_until=20.0,
    )

    row = registry.lifecycle.get(record.record_id)
    assert row["owner_plane"] == owner
    assert row["deletion_targets"] == [target]
    assert row["data_class"] == "confidential"
    assert row["purposes"] == ["model-inference", "verification"]
    assert row["retention_until"] == 20.0
    assert row["state"] == "active"


def test_register_canonical_write_accepts_explicit_projection_targets() -> None:
    registry = GovernanceRegistry()

    registry.register_canonical_write(
        CanonicalDataPlane.MEMORY,
        record_id="memory-1",
        tenant_id="tenant-a",
        source_ref="memory://1",
        data_class="internal",
        purposes=("retrieval-synthesis",),
        deletion_targets=("memory", "retrieval", "artifact"),
        created_at=10.0,
    )

    plan = registry.request_deletion(
        "tenant-a",
        record_ids=("memory-1",),
        now=20.0,
    )

    assert [(action.record_id, action.target) for action in plan.actions] == [
        ("memory-1", "artifact"),
        ("memory-1", "memory"),
        ("memory-1", "retrieval"),
    ]


@pytest.mark.parametrize("plane", ["unknown", "", "vector-cache"])
def test_register_canonical_write_rejects_unknown_planes(plane: str) -> None:
    registry = GovernanceRegistry()

    with pytest.raises(DataGovernanceDenied, match="unknown canonical data plane"):
        registry.register_canonical_write(
            plane,
            record_id="bad",
            tenant_id="tenant-a",
            source_ref="bad://1",
            data_class="internal",
            purposes=("model-inference",),
            created_at=10.0,
        )


def test_register_canonical_write_requires_purpose_and_preserves_registry_authority() -> None:
    registry = GovernanceRegistry()

    with pytest.raises(DataGovernanceDenied, match="at least one purpose"):
        registry.register_canonical_write(
            "conversation",
            record_id="message-1",
            tenant_id="tenant-a",
            source_ref="conversation://message-1",
            data_class="internal",
            purposes=(),
            created_at=10.0,
        )

    first = registry.register_canonical_write(
        "conversation",
        record_id="message-1",
        tenant_id="tenant-a",
        source_ref="conversation://message-1",
        data_class="internal",
        purposes=("model-inference",),
        created_at=10.0,
    )

    replay = registry.register_canonical_write(
        "conversation",
        record_id="message-1",
        tenant_id="tenant-a",
        source_ref="conversation://message-1",
        data_class="internal",
        purposes=("model-inference",),
        created_at=10.0,
    )
    assert replay == first

    with pytest.raises(LifecycleConflict, match="record identity conflicts"):
        registry.register_canonical_write(
            "conversation",
            record_id="message-1",
            tenant_id="tenant-a",
            source_ref="conversation://message-1",
            data_class="confidential",
            purposes=("model-inference",),
            created_at=10.0,
        )


@pytest.mark.parametrize(
    ("field", "kwargs", "match"),
    [
        (
            "purposes",
            {"purposes": "model-inference"},
            "purpose must be a collection",
        ),
        (
            "deletion_targets",
            {
                "purposes": ("model-inference",),
                "deletion_targets": "memory",
            },
            "deletion target must be a collection",
        ),
    ],
)
def test_register_canonical_write_rejects_scalar_string_collections(
    field: str,
    kwargs: dict[str, object],
    match: str,
) -> None:
    registry = GovernanceRegistry()
    base: dict[str, object] = {
        "record_id": f"bad-{field}",
        "tenant_id": "tenant-a",
        "source_ref": f"memory://bad-{field}",
        "data_class": "internal",
        "purposes": ("model-inference",),
        "created_at": 10.0,
    }
    base.update(kwargs)

    with pytest.raises(DataGovernanceDenied, match=match):
        registry.register_canonical_write("memory", **base)


def test_canonical_write_registration_is_idempotent_for_identical_replay() -> None:
    registry = GovernanceRegistry()
    kwargs = {
        "record_id": "memory-replay",
        "tenant_id": "tenant-a",
        "source_ref": "memory://memory-replay",
        "data_class": "internal",
        "purposes": ("retrieval-synthesis",),
        "deletion_targets": ("memory", "retrieval"),
        "created_at": 10.0,
        "retention_until": 20.0,
    }

    first = registry.register_canonical_write("memory", **kwargs)
    second = registry.register_canonical_write("memory", **kwargs)

    assert second == first
    assert registry.export_inventory("tenant-a")["count"] == 1


def test_canonical_write_registration_rejects_identity_reuse_with_changed_metadata() -> None:
    registry = GovernanceRegistry()
    registry.register_canonical_write(
        "artifact",
        record_id="artifact-1",
        tenant_id="tenant-a",
        source_ref="artifact://artifact-1",
        data_class="internal",
        purposes=("model-inference",),
        created_at=10.0,
    )

    with pytest.raises(LifecycleConflict, match="identity conflicts"):
        registry.register_canonical_write(
            "artifact",
            record_id="artifact-1",
            tenant_id="tenant-a",
            source_ref="artifact://artifact-1",
            data_class="confidential",
            purposes=("model-inference",),
            created_at=10.0,
        )


@pytest.mark.asyncio
async def test_governance_registry_delete_with_adapters_executes_physical_delete() -> None:
    registry = GovernanceRegistry()
    memory = InMemoryStore()
    await memory.put({"id": "memory-physical", "content": "delete me", "metadata": {}})
    registry.register_canonical_write(
        "memory",
        record_id="memory-physical",
        tenant_id="tenant-a",
        source_ref="memory://memory-physical",
        data_class="internal",
        purposes=("model-inference",),
        created_at=10.0,
    )
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", MemoryDeletionAdapter(memory))

    result = await registry.delete_with_adapters(
        adapters,
        "tenant-a",
        record_ids=("memory-physical",),
        now=20.0,
    )

    assert result.receipts[-1].state.value == "deleted"
    assert await memory.search("", limit=10) == []
    assert registry.lifecycle.get("memory-physical")["state"] == "deleted"


@pytest.mark.asyncio
async def test_governance_registry_retention_with_adapters_executes_physical_delete() -> None:
    registry = GovernanceRegistry()
    memory = InMemoryStore()
    await memory.put({"id": "memory-expired", "content": "old", "metadata": {}})
    registry.register_canonical_write(
        "memory",
        record_id="memory-expired",
        tenant_id="tenant-a",
        source_ref="memory://memory-expired",
        data_class="internal",
        purposes=("model-inference",),
        created_at=10.0,
        retention_until=15.0,
    )
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", MemoryDeletionAdapter(memory))

    results = await registry.execute_retention_with_adapters(adapters, now=20.0)

    assert len(results) == 1
    assert results[0].receipts[-1].state.value == "deleted"
    assert await memory.search("", limit=10) == []
