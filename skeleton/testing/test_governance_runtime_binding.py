from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.api.server import (
    ServerState,
    _canonical_memory_mongo_configured,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.memory.writeback import AsyncGovernedMemoryWriter
from skeleton.persistence.memory_repository import MongoMemoryRepository


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

