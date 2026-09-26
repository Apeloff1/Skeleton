from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from skeleton.artifact_plane.governance import GovernedArtifactStore
from skeleton.api.server import (
    ServerState,
    _canonical_memory_mongo_configured,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.memory.projection import AsyncMemoryProjectionCoordinator
from skeleton.memory.writeback import AsyncGovernedMemoryWriter
from skeleton.persistence.memory_repository import MongoMemoryRepository
from skeleton.retrieval.governance import GovernedRetrievalIndex


def test_server_state_binds_one_durable_governance_owner(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "governance-lifecycle.sqlite3"
    monkeypatch.setenv("SKL_GOVERNANCE_LIFECYCLE_PATH", str(path))

    first = ServerState()
    registry = first.bind_governance_registry()
    assert first.bind_governance_registry() is registry

    registry.register_canonical_write(
        "memory",
        record_id="memory-runtime-binding",
        tenant_id="tenant-a",
        source_ref="memory://assistant/memory-runtime-binding",
        data_class="confidential",
        purposes=("model-inference", "retrieval-synthesis"),
        created_at=10.0,
        retention_until=20.0,
    )
    first.close_governance_registry()

    restarted = ServerState()
    restored = restarted.bind_governance_registry()
    inventory = restored.export_inventory("tenant-a")

    assert inventory["count"] == 1
    assert inventory["records"][0]["record_id"] == "memory-runtime-binding"
    assert inventory["records"][0]["data_class"] == "confidential"
    assert inventory["records"][0]["retention_until"] == 20.0
    restarted.close_governance_registry()


def test_compose_binds_governance_lifecycle_to_skeleton_durable_volume() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert (
        "SKL_GOVERNANCE_LIFECYCLE_PATH=/app/data/governance_lifecycle.sqlite"
        in compose
    )
    assert "skeleton_data:/app/data" in compose

class _FakeCollection:
    def __init__(self) -> None:
        self.indexes = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append((tuple(keys), dict(kwargs)))
        return kwargs.get("name", "index")


class _FakeDatabase:
    def __init__(self) -> None:
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, _FakeCollection())


@pytest.mark.asyncio
async def test_server_state_binds_one_governed_admitted_mongo_memory_writer() -> None:
    state = ServerState()
    admission = AdmissionRuntime()
    state.engine_execution_admission_runtime = admission
    database = _FakeDatabase()

    writer = await state.bind_canonical_memory_writer(database)
    replay = await state.bind_canonical_memory_writer(database)

    assert replay is writer
    assert isinstance(writer, AsyncGovernedMemoryWriter)
    assert isinstance(state.canonical_memory_repository, MongoMemoryRepository)
    assert writer.repository is state.canonical_memory_repository
    assert writer.admission_runtime is admission
    assert writer.governance is state.governance_registry
    assert isinstance(
        state.canonical_memory_projection_coordinator,
        AsyncMemoryProjectionCoordinator,
    )
    assert (
        state.canonical_memory_projection_coordinator.admission_runtime
        is admission
    )
    assert state.canonical_memory_mongo_client is None

    assert set(database.collections) == {
        "canonical_memory_records",
        "canonical_memory_idempotency",
        "canonical_memory_revisions",
        "canonical_memory_projection_outbox",
    }
    assert all(
        collection.indexes
        for collection in database.collections.values()
    )

    await state.close_canonical_memory_writer()
    assert state.canonical_memory_writer is None
    assert state.canonical_memory_repository is None
    assert state.canonical_memory_projection_coordinator is None
    state.close_governance_registry()


def test_canonical_memory_mongo_binding_requires_explicit_runtime_configuration(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SKL_MONGO_URI", raising=False)
    assert _canonical_memory_mongo_configured() is False

    monkeypatch.setenv("SKL_MONGO_URI", "   ")
    assert _canonical_memory_mongo_configured() is False

    monkeypatch.setenv(
        "SKL_MONGO_URI",
        "mongodb://canonical-memory.example:27017",
    )
    assert _canonical_memory_mongo_configured() is True


def test_skeleton_runtime_declares_canonical_mongo_driver_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"motor==3.7.1"' in pyproject
    assert '"pymongo==4.18.1"' in pyproject
    assert "SKL_MONGO_URI=" in compose
    assert "SKL_MONGO_DATABASE=skeleton" in compose

def test_server_state_restores_durable_governance_audit_chain(
    tmp_path,
    monkeypatch,
) -> None:
    lifecycle_path = tmp_path / "governance-lifecycle.sqlite3"
    audit_path = tmp_path / "governance-audit.jsonl"
    monkeypatch.setenv(
        "SKL_GOVERNANCE_LIFECYCLE_PATH",
        str(lifecycle_path),
    )
    monkeypatch.setenv(
        "SKL_GOVERNANCE_AUDIT_PATH",
        str(audit_path),
    )

    first = ServerState()
    registry = first.bind_governance_registry()
    assert first.governance_audit_log is not None
    assert first.governance_audit_timeline is not None
    assert first.governance_lifecycle_adapters is not None

    registry.register_canonical_write(
        "memory",
        record_id="memory-audit-restart",
        tenant_id="tenant-a",
        source_ref="memory://assistant/memory-audit-restart",
        data_class="confidential",
        purposes=("model-inference",),
        created_at=10.0,
    )
    assert audit_path.exists()
    assert first.governance_audit_log.tamper_check() == (True, -1)
    first.close_governance_registry()

    restarted = ServerState()
    restored = restarted.bind_governance_registry()
    assert restored.export_inventory("tenant-a")["count"] == 1
    entries = restarted.governance_audit_log.query(
        action="governance.lifecycle.register",
        limit=20,
    )
    assert len(entries) == 1
    assert entries[0].outcome == "success"
    assert restarted.governance_audit_log.tamper_check() == (True, -1)
    restarted.close_governance_registry()



@pytest.mark.asyncio
async def test_server_state_composes_governed_artifact_lifecycle(
    tmp_path,
) -> None:
    state = ServerState()
    artifacts = state.bind_canonical_artifact_store(tmp_path / "artifacts")
    replay = state.bind_canonical_artifact_store(tmp_path / "other")

    assert replay is artifacts
    assert isinstance(artifacts, GovernedArtifactStore)
    assert state.governance_lifecycle_executor is not None
    assert state.governance_lifecycle_adapters is not None

    record = artifacts.write_bytes(
        tenant_id="tenant-a",
        artifact_id="runtime-artifact.bin",
        payload=b"runtime-governed-artifact",
        data_class="confidential",
        purposes=("artifact-delivery",),
        created_at=10.0,
        retention_until=100.0,
    )
    inventory = state.governance_registry.export_inventory("tenant-a")
    row = next(
        item
        for item in inventory["records"]
        if item["record_id"] == record.record_id
    )
    assert row["owner_plane"] == "artifact"
    assert row["data_class"] == "confidential"

    exported = await state.governance_lifecycle_executor.export_tenant(
        "tenant-a"
    )
    artifact_exports = [
        item
        for item in exported.records
        if item["governance"]["record_id"] == record.record_id
    ]
    assert len(artifact_exports) == 1
    assert (
        artifact_exports[0]["payload"]["artifact_id"]
        == "runtime-artifact.bin"
    )

    plan = state.governance_lifecycle.request_deletion(
        "tenant-a",
        record_ids=(record.record_id,),
        now=20.0,
    )
    await state.governance_lifecycle_executor.execute_deletion_plan(
        plan,
        now=21.0,
    )

    assert artifacts.read_bytes(
        "tenant-a",
        "runtime-artifact.bin",
    ) is None
    assert (
        state.governance_lifecycle.get(record.record_id)["state"]
        == "deleted"
    )
    state.close_governance_registry()

@pytest.mark.asyncio
async def test_server_state_composes_governed_retrieval_lifecycle() -> None:
    state = ServerState()
    retrieval = state.bind_canonical_retrieval_index()
    replay = state.bind_canonical_retrieval_index()

    assert replay is retrieval
    assert isinstance(retrieval, GovernedRetrievalIndex)
    assert state.governance_lifecycle_executor is not None
    assert state.governance_lifecycle_adapters is not None

    record = retrieval.add(
        tenant_id="tenant-a",
        doc_id="runtime-doc",
        text="governed retrieval runtime",
        created_at=10.0,
    )
    inventory = state.governance_registry.export_inventory("tenant-a")
    assert inventory["records"][0]["record_id"] == record.record_id
    assert inventory["records"][0]["owner_plane"] == "retrieval"

    exported = await state.governance_lifecycle_executor.export_tenant(
        "tenant-a"
    )
    assert exported.records[0]["payload"]["doc_id"] == "runtime-doc"

    plan = state.governance_lifecycle.request_deletion(
        "tenant-a",
        record_ids=(record.record_id,),
        now=20.0,
    )
    await state.governance_lifecycle_executor.execute_deletion_plan(
        plan,
        now=21.0,
    )
    assert retrieval.size("tenant-a") == 0
    state.close_governance_registry()

@pytest.mark.asyncio
async def test_governed_artifact_retention_expiry_physically_deletes_bytes(
    tmp_path,
) -> None:
    state = ServerState()
    artifacts = state.bind_canonical_artifact_store(tmp_path / "artifacts")

    record = artifacts.write_bytes(
        tenant_id="tenant-retention",
        artifact_id="expiring-build.zip",
        payload=b"expiring-artifact",
        data_class="internal",
        purposes=("artifact-delivery", "download"),
        created_at=10.0,
        retention_until=20.0,
    )
    assert artifacts.read_bytes(
        "tenant-retention",
        "expiring-build.zip",
    ) == b"expiring-artifact"

    results = await state.governance_lifecycle_executor.execute_retention_expiry(
        now=21.0,
    )

    assert len(results) == 1
    assert artifacts.read_bytes(
        "tenant-retention",
        "expiring-build.zip",
    ) is None
    lifecycle = state.governance_lifecycle.get(record.record_id)
    assert lifecycle["state"] == "deleted"
    receipts = state.governance_lifecycle.receipts(
        tenant_id="tenant-retention"
    )
    record_receipts = [
        receipt
        for receipt in receipts
        if receipt.record_id == record.record_id
    ]
    assert len(record_receipts) == 1
    assert record_receipts[0].target == "artifact"
    state.close_governance_registry()


def test_health_reports_canonical_memory_disabled_when_not_configured(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SKL_MONGO_URI", raising=False)
    state = ServerState()

    health = state.is_healthy()

    assert health["checks"]["canonical_memory"] == {
        "configured": False,
        "bound": False,
        "status": "disabled",
        "error": None,
    }


def test_health_fails_closed_when_configured_memory_authority_is_unbound(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SKL_MONGO_URI",
        "mongodb://canonical-memory.example:27017",
    )
    state = ServerState()

    health = state.is_healthy()

    assert health["overall"] is False
    assert health["checks"]["canonical_memory"]["configured"] is True
    assert health["checks"]["canonical_memory"]["bound"] is False
    assert health["checks"]["canonical_memory"]["status"] == "unavailable"
    assert "configured but not bound" in (
        health["checks"]["canonical_memory"]["error"]
    )


def test_health_reports_configured_memory_ready_only_when_full_bundle_bound(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SKL_MONGO_URI",
        "mongodb://canonical-memory.example:27017",
    )
    state = ServerState()
    state.canonical_memory_repository = object()
    state.canonical_memory_writer = object()
    state.canonical_memory_projection_coordinator = object()

    health = state.is_healthy()

    assert health["checks"]["canonical_memory"] == {
        "configured": True,
        "bound": True,
        "status": "ready",
        "error": None,
    }
    assert health["overall"] is True


class _RecordingMemoryWriter:
    def __init__(self) -> None:
        self.proposals = []

    def stage(self, proposal):
        self.proposals.append(proposal)
        return SimpleNamespace(proposal=proposal)

    async def commit(self, proposal_id, *, now=None):
        assert self.proposals
        assert self.proposals[-1].proposal_id == proposal_id
        return SimpleNamespace(memory_id="memory-finalized-1")


@pytest.mark.asyncio
async def test_verified_memory_finalization_is_noop_without_explicit_intent() -> None:
    state = ServerState()
    request = SimpleNamespace(
        operation_id=str(uuid4()),
        execution_id=str(uuid4()),
        context_policy={
            "tenant_id": "tenant-a",
            "context_digest": "a" * 64,
            "data_class": "internal",
        },
    )

    bindings = await state.bind_verified_memory_finalization(
        request,
        "verified answer",
        {},
    )

    assert bindings.memory_refs == ()


@pytest.mark.asyncio
async def test_verified_memory_finalization_fails_closed_without_authority() -> None:
    state = ServerState()
    request = SimpleNamespace(
        operation_id=str(uuid4()),
        execution_id=str(uuid4()),
        context_policy={
            "tenant_id": "tenant-a",
            "context_digest": "a" * 64,
            "data_class": "confidential",
            "memory_write_intent": {
                "subject_id": "user-a",
                "namespace": "assistant",
                "kind": "semantic",
                "data_class": "confidential",
                "content_from": "verified_final_output",
                "provenance_refs": [],
            },
        },
    )

    with pytest.raises(
        RuntimeError,
        match="canonical memory authority is required",
    ):
        await state.bind_verified_memory_finalization(
            request,
            "verified answer",
            {},
        )


@pytest.mark.asyncio
async def test_verified_memory_finalization_commits_governed_proposal() -> None:
    state = ServerState()
    writer = _RecordingMemoryWriter()
    state.canonical_memory_writer = writer
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    request = SimpleNamespace(
        operation_id=operation_id,
        execution_id=execution_id,
        context_policy={
            "tenant_id": "tenant-a",
            "context_digest": "b" * 64,
            "data_class": "confidential",
            "memory_write_intent": {
                "subject_id": "user-a",
                "namespace": "assistant",
                "kind": "semantic",
                "data_class": "confidential",
                "content_from": "verified_final_output",
                "provenance_refs": ["conversation:thread-a"],
            },
        },
    )

    bindings = await state.bind_verified_memory_finalization(
        request,
        "verified durable outcome",
        {
            "provider_receipts": ["provider-receipt-1"],
            "tool_receipts": ["tool-receipt-1"],
        },
    )

    assert bindings.memory_refs == ("memory:memory-finalized-1",)
    assert len(writer.proposals) == 1
    proposal = writer.proposals[0]
    assert proposal.tenant_id == "tenant-a"
    assert proposal.subject_id == "user-a"
    assert proposal.namespace == "assistant"
    assert proposal.content == "verified durable outcome"
    assert proposal.source_operation_id == operation_id
    assert proposal.data_class == "confidential"
    assert "execution:" + execution_id in proposal.provenance_refs
    assert "context:" + ("b" * 64) in proposal.provenance_refs
    assert "verified-final-output" in proposal.provenance_refs
    assert "provider:provider-receipt-1" in proposal.provenance_refs
    assert "tool:tool-receipt-1" in proposal.provenance_refs
    assert "conversation:thread-a" in proposal.provenance_refs
