from __future__ import annotations

from dataclasses import dataclass

import pytest

from skeleton.frontier.memory import InMemoryStore
from skeleton.observability.correlation import correlation_scope
from skeleton.observability.tracing import InMemoryExporter, Tracer
from skeleton.vault.audit import AuditLog
from skeleton.vault.data_lifecycle import DataLifecycleRegistry, GovernedDataRecord
from skeleton.vault.governance_audit import GovernanceAuditTimeline
from skeleton.vault.lifecycle_adapters import (
    LifecycleAdapterMissing,
    LifecycleAdapterRegistry,
    LifecycleExecutionError,
    LifecycleExecutor,
    MemoryDeletionAdapter,
    MongoCollectionLifecycleAdapter,
)


def _record(
    record_id: str,
    *,
    owner_plane: str = "memory",
    targets: tuple[str, ...] = ("memory",),
    tenant: str = "tenant-secret-a",
    source_ref: str = "memory://TOP-SECRET-SOURCE",
) -> GovernedDataRecord:
    return GovernedDataRecord(
        record_id=record_id,
        tenant_id=tenant,
        owner_plane=owner_plane,
        source_ref=source_ref,
        data_class="confidential",
        purposes=("model-inference",),
        deletion_targets=targets,
        created_at=10.0,
    )


def _timeline():
    exporter = InMemoryExporter()
    tracer = Tracer("governance-test", exporter=exporter)
    audit = AuditLog(clock=lambda: 123.0)
    return GovernanceAuditTimeline(
        audit,
        tracer=tracer,
        actor="governance-test-agent",
    ), audit, exporter


@pytest.mark.asyncio
async def test_deletion_emits_correlated_worm_plan_and_receipt_without_payload() -> None:
    lifecycle = DataLifecycleRegistry()
    memory = InMemoryStore()
    await memory.put(
        {
            "id": "record-1",
            "content": "TOP-SECRET-PAYLOAD",
            "metadata": {"source": "TOP-SECRET-SOURCE"},
        }
    )
    lifecycle.register(_record("record-1"))
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", MemoryDeletionAdapter(memory))
    timeline, audit, exporter = _timeline()
    executor = LifecycleExecutor(lifecycle, adapters, timeline=timeline)

    plan = lifecycle.request_deletion(
        "tenant-secret-a",
        record_ids=("record-1",),
        now=20.0,
    )
    with correlation_scope("gov-correlation-123"):
        await executor.execute_deletion_plan(plan, now=21.0)

    entries = audit.query(limit=20)
    assert {entry.action for entry in entries} == {
        "governance.lifecycle.plan",
        "governance.lifecycle.delete",
    }
    assert all(entry.metadata["correlation_id"] == "gov-correlation-123" for entry in entries)
    assert all(entry.subject_fp is not None for entry in entries)

    rendered_audit = repr(
        [
            {
                "action": entry.action,
                "subject_fp": entry.subject_fp,
                "metadata": entry.metadata,
            }
            for entry in entries
        ]
    )
    assert "TOP-SECRET-PAYLOAD" not in rendered_audit
    assert "TOP-SECRET-SOURCE" not in rendered_audit
    assert "tenant-secret-a" not in rendered_audit
    assert "record-1" not in rendered_audit

    spans = exporter.query(limit=20)
    assert len(spans) == 2
    assert all(span.trace_id == "gov-correlation-123" for span in spans)
    rendered_spans = repr([span.to_dict() for span in spans])
    assert "TOP-SECRET-PAYLOAD" not in rendered_spans
    assert "TOP-SECRET-SOURCE" not in rendered_spans
    assert "tenant-secret-a" not in rendered_spans


@pytest.mark.asyncio
async def test_preflight_denial_is_audited_before_any_physical_delete() -> None:
    lifecycle = DataLifecycleRegistry()
    memory = InMemoryStore()
    await memory.put({"id": "mixed", "content": "keep", "metadata": {}})
    lifecycle.register(
        _record(
            "mixed",
            targets=("memory", "artifact"),
            source_ref="memory://mixed",
        )
    )
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", MemoryDeletionAdapter(memory))
    timeline, audit, _ = _timeline()
    executor = LifecycleExecutor(lifecycle, adapters, timeline=timeline)
    plan = lifecycle.request_deletion(
        "tenant-secret-a",
        record_ids=("mixed",),
        now=20.0,
    )

    with pytest.raises(LifecycleAdapterMissing, match="artifact"):
        with correlation_scope("gov-preflight"):
            await executor.execute_deletion_plan(plan, now=21.0)

    assert len(await memory.search("", limit=10)) == 1
    assert lifecycle.receipts() == ()
    entries = audit.query(limit=20)
    assert [entry.outcome for entry in entries].count("denied") == 1
    denied = next(entry for entry in entries if entry.outcome == "denied")
    assert denied.action == "governance.lifecycle.preflight_denied"
    assert denied.metadata["missing_targets"] == ["artifact"]


class _FailingDeleteAdapter:
    async def delete(self, action) -> None:
        raise RuntimeError("TOP-SECRET-ERROR-BODY")


@pytest.mark.asyncio
async def test_adapter_failure_audit_records_error_type_not_secret_message() -> None:
    lifecycle = DataLifecycleRegistry()
    lifecycle.register(_record("failure-record", source_ref="memory://failure"))
    adapters = LifecycleAdapterRegistry()
    adapters.register_deletion("memory", _FailingDeleteAdapter())
    timeline, audit, exporter = _timeline()
    executor = LifecycleExecutor(lifecycle, adapters, timeline=timeline)
    plan = lifecycle.request_deletion(
        "tenant-secret-a",
        record_ids=("failure-record",),
        now=20.0,
    )

    with pytest.raises(LifecycleExecutionError):
        with correlation_scope("gov-failure"):
            await executor.execute_deletion_plan(plan, now=21.0)

    failure = next(entry for entry in audit.query(limit=20) if entry.outcome == "failure")
    assert failure.metadata["error_type"] == "RuntimeError"
    assert "TOP-SECRET-ERROR-BODY" not in repr(failure.metadata)
    assert "TOP-SECRET-ERROR-BODY" not in repr(
        [span.to_dict() for span in exporter.query(limit=20)]
    )


@dataclass
class _DeleteResult:
    deleted_count: int


class _FakeCollection:
    def __init__(self) -> None:
        self.rows = [
            {
                "_id": "native",
                "record_id": "export-1",
                "tenant_id": "tenant-secret-a",
                "payload": "TOP-SECRET-EXPORT-PAYLOAD",
            }
        ]

    async def delete_one(self, query):
        return _DeleteResult(0)

    async def find_one(self, query):
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None


@pytest.mark.asyncio
async def test_export_audit_records_inventory_shape_not_exported_payload() -> None:
    lifecycle = DataLifecycleRegistry()
    lifecycle.register(
        _record(
            "export-1",
            owner_plane="memory",
            source_ref="memory://TOP-SECRET-EXPORT-SOURCE",
        )
    )
    adapters = LifecycleAdapterRegistry()
    adapters.register_export(
        "memory",
        MongoCollectionLifecycleAdapter(_FakeCollection()),
    )
    timeline, audit, exporter = _timeline()
    executor = LifecycleExecutor(lifecycle, adapters, timeline=timeline)

    with correlation_scope("gov-export"):
        result = await executor.export_tenant("tenant-secret-a")

    assert result.records[0]["payload"]["payload"] == "TOP-SECRET-EXPORT-PAYLOAD"
    entry = next(
        item
        for item in audit.query(limit=20)
        if item.action == "governance.lifecycle.export"
    )
    rendered = repr(entry.metadata)
    assert entry.outcome == "success"
    assert entry.metadata["record_count"] == 1
    assert entry.metadata["owner_planes"] == ["memory"]
    assert "TOP-SECRET-EXPORT-PAYLOAD" not in rendered
    assert "TOP-SECRET-EXPORT-SOURCE" not in rendered
    assert "tenant-secret-a" not in rendered
    assert "TOP-SECRET-EXPORT-PAYLOAD" not in repr(
        [span.to_dict() for span in exporter.query(limit=20)]
    )


@pytest.mark.asyncio
async def test_export_missing_owner_adapter_is_audited_and_reads_nothing() -> None:
    lifecycle = DataLifecycleRegistry()
    lifecycle.register(
        _record(
            "artifact-1",
            owner_plane="artifact",
            targets=("artifact",),
            source_ref="artifact://1",
        )
    )
    timeline, audit, _ = _timeline()
    executor = LifecycleExecutor(
        lifecycle,
        LifecycleAdapterRegistry(),
        timeline=timeline,
    )

    with pytest.raises(LifecycleAdapterMissing, match="artifact"):
        with correlation_scope("gov-export-denied"):
            await executor.export_tenant("tenant-secret-a")

    denied = next(entry for entry in audit.query(limit=20) if entry.outcome == "denied")
    assert denied.action == "governance.lifecycle.export"
    assert denied.metadata["missing_owner_planes"] == ["artifact"]
