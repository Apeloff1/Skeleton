from __future__ import annotations

import base64
import inspect
from pathlib import Path

import pytest

from skeleton.api import server as server_module
from skeleton.api.server import ServerState


def _governed_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> ServerState:
    monkeypatch.setenv(
        "SKL_GOVERNANCE_LIFECYCLE_PATH",
        str(tmp_path / "governance.sqlite3"),
    )
    monkeypatch.setenv(
        "SKL_GOVERNANCE_ARTIFACT_ROOT",
        str(tmp_path / "artifacts"),
    )
    state = ServerState()
    state.bind_governance_registry()
    return state


@pytest.mark.asyncio
async def test_server_state_binds_artifact_owner_and_executes_export_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _governed_state(tmp_path, monkeypatch)

    store = state.bind_canonical_artifact_store()
    replay = state.bind_canonical_artifact_store()

    assert replay is store
    assert state.canonical_artifact_store is store
    assert state.governance_lifecycle_adapters is not None
    assert state.governance_lifecycle_executor is not None

    record = store.write_bytes(
        tenant_id="tenant-a",
        artifact_id="answer.bin",
        payload=b"canonical artifact payload",
        data_class="confidential",
        purposes=("artifact-delivery", "verification"),
        created_at=10.0,
        retention_until=100.0,
    )

    row = state.governance_lifecycle.get(record.record_id)
    assert row["owner_plane"] == "artifact"
    assert row["deletion_targets"] == ["artifact"]
    assert row["state"] == "active"

    exported = await state.governance_lifecycle_executor.export_tenant(
        "tenant-a"
    )
    assert len(exported.records) == 1
    payload = exported.records[0]["payload"]
    assert payload is not None
    assert payload["artifact_id"] == "answer.bin"
    assert payload["tenant_id"] == "tenant-a"
    assert (
        base64.b64decode(payload["content_base64"])
        == b"canonical artifact payload"
    )

    plan = state.governance_lifecycle.request_deletion(
        "tenant-a",
        record_ids=(record.record_id,),
        now=20.0,
    )
    result = await state.governance_lifecycle_executor.execute_deletion_plan(
        plan,
        now=21.0,
    )

    assert result.receipts[-1].state.value == "deleted"
    assert store.read_bytes("tenant-a", "answer.bin") is None
    assert state.governance_lifecycle.get(record.record_id)["state"] == "deleted"

    state.close_governance_registry()


@pytest.mark.asyncio
async def test_server_state_artifact_retention_physically_deletes_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _governed_state(tmp_path, monkeypatch)
    store = state.bind_canonical_artifact_store()

    record = store.write_bytes(
        tenant_id="tenant-a",
        artifact_id="expired.bin",
        payload=b"expired artifact",
        created_at=10.0,
        retention_until=15.0,
    )
    assert store.read_bytes("tenant-a", "expired.bin") == b"expired artifact"

    results = await state.governance_lifecycle_executor.execute_retention_expiry(
        now=20.0
    )

    assert len(results) == 1
    assert results[0].receipts[-1].record_id == record.record_id
    assert results[0].receipts[-1].state.value == "deleted"
    assert store.read_bytes("tenant-a", "expired.bin") is None

    state.close_governance_registry()


@pytest.mark.asyncio
async def test_api_startup_binds_canonical_artifact_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _State:
        genesis = object()

        def bind_governance_registry(self):
            calls.append("governance")

        def bind_canonical_artifact_store(self):
            calls.append("artifact")

        def bind_canonical_retrieval_index(self):
            calls.append("retrieval")

        def bind_engine_execution_service(self):
            calls.append("engine")

        async def bind_canonical_memory_writer(self):
            calls.append("memory")

        async def recover_engine_executions(self):
            calls.append("recover")
            return ()

        async def close_canonical_memory_writer(self):
            return None

        async def close_engine_execution_service(self):
            return None

        def close_governance_registry(self):
            return None

        def close_operation_runtime(self):
            return None

    fake = _State()
    monkeypatch.setattr(server_module, "get_state", lambda: fake)
    monkeypatch.delenv("SKL_MONGO_URI", raising=False)

    app = server_module.create_app()
    startup_handlers = tuple(app.router.on_startup)
    assert startup_handlers

    for handler in startup_handlers:
        result = handler()
        if inspect.isawaitable(result):
            await result

    assert calls[:4] == [
        "governance",
        "artifact",
        "retrieval",
        "engine",
    ]
    assert calls[-1] == "recover"
    assert "memory" not in calls
