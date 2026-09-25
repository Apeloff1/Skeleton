from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from skeleton.skills.tool_contract import approval_ref_for_request
from skeleton.skills.tool_runtime import ToolExecutionConflict


@pytest.fixture
def registry():
    import services.tool_registry as tool_registry
    return tool_registry


def _approval_for(
    registry,
    *,
    tool: str,
    params: dict,
    operation_id: str,
    idempotency_key: str,
    tenant_id: str = "legacy-backend",
) -> str:
    request = registry.ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id,
        tenant_id=tenant_id,
        tool_id=tool,
        idempotency_key=idempotency_key,
        arguments=dict(params),
        requested_at=datetime.now(timezone.utc),
    )
    return approval_ref_for_request(request)


def _reset_canonical(
    registry,
    *,
    receipt_path: str = ":memory:",
    result_path: str = ":memory:",
):
    prior_runtime = getattr(registry, "_CANONICAL_RUNTIME", None)
    prior_store = getattr(registry, "_CANONICAL_RESULT_STORE", None)
    if prior_runtime is not None and prior_runtime.receipt_store is not None:
        try:
            prior_runtime.receipt_store.close()
        except Exception:
            pass
    if prior_store is not None:
        try:
            prior_store.close()
        except Exception:
            pass
    registry._CANONICAL_RUNTIME = registry.AsyncToolRuntime(
        receipt_store=registry.SQLiteToolReceiptStore(receipt_path)
    )
    registry._CANONICAL_RESULT_STORE = registry._CompatibilityResultStore(result_path)
    registry._CANONICAL_INIT_LOCK = asyncio.Lock()
    registry._CANONICAL_READY = False


@pytest.mark.asyncio
async def test_canonical_delegate_coalesces_concurrent_exact_retries(
    registry,
    monkeypatch,
):
    _reset_canonical(registry)
    calls = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fake_vault(params):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return {"ok": True, "value": params.get("topic")}

    monkeypatch.setitem(registry.TOOLS, "vault_query", fake_vault)
    operation_id = str(uuid4())
    first = asyncio.create_task(
        registry.invoke_canonical(
            "vault_query",
            {"topic": "memory"},
            operation_id=operation_id,
            tenant_id="tenant-a",
            idempotency_key="same",
            request_id=str(uuid4()),
        )
    )
    await entered.wait()
    second = asyncio.create_task(
        registry.invoke_canonical(
            "vault_query",
            {"topic": "memory"},
            operation_id=operation_id,
            tenant_id="tenant-a",
            idempotency_key="same",
            request_id=str(uuid4()),
        )
    )
    await asyncio.sleep(0)

    assert calls == 1
    release.set()
    left, right = await asyncio.gather(first, second)

    assert left["ok"] is True
    assert right["ok"] is True
    assert left["value"] == right["value"] == "memory"
    assert left["receipt"]["receipt_id"] == right["receipt"]["receipt_id"]
    assert calls == 1


@pytest.mark.asyncio
async def test_canonical_schema_denial_prevents_legacy_handler_execution(
    registry,
    monkeypatch,
):
    _reset_canonical(registry)
    calls = 0

    async def fake_compile(params):
        nonlocal calls
        calls += 1
        return {"ok": True}

    monkeypatch.setitem(registry.TOOLS, "compile_code", fake_compile)
    result = await registry.invoke_canonical(
        "compile_code",
        {"language": "python", "code": "print(1)"},
        operation_id=str(uuid4()),
        tenant_id="tenant-a",
        idempotency_key="bad-schema",
    )

    assert result["ok"] is False
    assert result["error"] == "arguments_invalid"
    assert result["receipt"]["metered_tool_calls"] == 0
    assert calls == 0


@pytest.mark.asyncio
async def test_legacy_read_only_invoke_returns_canonical_receipt(registry, monkeypatch):
    _reset_canonical(registry)

    async def fake_consult(params):
        return {"ok": True, "answer": params.get("topic")}

    monkeypatch.setitem(registry.TOOLS, "jeeves_consult", fake_consult)
    result = await registry.invoke(
        "jeeves_consult",
        {"context": "lesson", "topic": "graphs"},
    )

    assert result["ok"] is True
    assert result["answer"] == "graphs"
    assert result["receipt"]["status"] == "succeeded"
    assert result["receipt"]["tool_id"] == "jeeves_consult"
    assert result["receipt"]["arguments_digest"]


@pytest.mark.asyncio
async def test_side_effecting_legacy_invoke_requires_idempotency_and_approval(
    registry,
    monkeypatch,
):
    _reset_canonical(registry)
    calls = 0

    async def fake_package(params):
        nonlocal calls
        calls += 1
        return {"ok": True, "artifacts": []}

    monkeypatch.setitem(registry.TOOLS, "package_build", fake_package)

    missing_key = await registry.invoke(
        "package_build",
        {"build_id": "build-1", "kinds": ["zip"]},
    )
    assert missing_key == {
        "ok": False,
        "error": "idempotency_key_required",
        "tool": "package_build",
    }

    denied = await registry.invoke(
        "package_build",
        {"build_id": "build-1", "kinds": ["zip"]},
        operation_id=str(uuid4()),
        idempotency_key="package-once",
    )
    assert denied["ok"] is False
    assert denied["receipt"]["status"] == "denied"
    assert denied["error"] == "approval_required"
    assert calls == 0

    approved_operation_id = str(uuid4())
    approved_params = {"build_id": "build-1", "kinds": ["zip"]}
    approved_ref = _approval_for(
        registry,
        tool="package_build",
        params=approved_params,
        operation_id=approved_operation_id,
        idempotency_key="package-approved",
    )
    approved = await registry.invoke(
        "package_build",
        approved_params,
        operation_id=approved_operation_id,
        idempotency_key="package-approved",
        approval_ref=approved_ref,
    )
    assert approved["ok"] is True
    assert approved["receipt"]["status"] == "succeeded"
    assert approved["receipt"]["approval_ref"] == approved_ref
    assert calls == 1


@pytest.mark.asyncio
async def test_legacy_failure_is_failed_receipt_not_success(
    registry,
    monkeypatch,
):
    _reset_canonical(registry)

    async def fake_search(params):
        return {"ok": False, "error": "upstream_failed"}

    monkeypatch.setitem(registry.TOOLS, "web_search", fake_search)
    result = await registry.invoke(
        "web_search",
        {"query": "test"},
    )

    assert result["ok"] is False
    assert result["receipt"]["status"] == "failed"
    assert result["error"] == "postcondition_failed"


@pytest.mark.asyncio
async def test_failed_package_postcondition_runs_compensation(
    registry,
    monkeypatch,
    tmp_path,
):
    _reset_canonical(registry)
    artifact = tmp_path / "partial.zip"
    artifact.write_bytes(b"partial")

    async def fake_package(params):
        return {
            "ok": False,
            "error": "publish_failed",
            "artifacts": [{"path": str(artifact), "artifact_id": "partial"}],
        }

    monkeypatch.setitem(registry.TOOLS, "package_build", fake_package)
    operation_id = str(uuid4())
    params = {"build_id": "build-1", "kinds": ["zip"]}
    approval_ref = _approval_for(
        registry,
        tool="package_build",
        params=params,
        operation_id=operation_id,
        idempotency_key="package-compensate",
    )
    result = await registry.invoke(
        "package_build",
        params,
        operation_id=operation_id,
        idempotency_key="package-compensate",
        approval_ref=approval_ref,
    )

    assert result["ok"] is False
    assert result["receipt"]["status"] == "failed"
    assert result["receipt"]["error_code"] == "postcondition_failed"
    assert result["receipt"]["compensation_ref"].startswith("compensation:")
    assert not artifact.exists()


def test_registry_describe_declares_canonical_authority(registry):
    description = registry.describe()

    assert description["authority"] == "canonical-tool-runtime"
    assert description["count"] == len(registry.TOOLS)
    assert description["retired_tools"]["llm_chat"]["delegate"] == (
        "skeleton-engine-provider-boundary"
    )
    assert all("effect" in item for item in description["tools"])
    package = next(item for item in description["tools"] if item["name"] == "package_build")
    assert package["approval_required"] is True
    assert package["idempotency_required"] is True



@pytest.mark.asyncio
async def test_canonical_delegate_replays_result_after_process_restart(
    registry,
    monkeypatch,
    tmp_path,
):
    receipt_path = str(tmp_path / "tool-receipts.sqlite3")
    result_path = str(tmp_path / "tool-results.sqlite3")
    operation_id = str(uuid4())
    calls = {"count": 0}

    async def first_handler(params):
        calls["count"] += 1
        return {"ok": True, "value": params["topic"], "generation": 1}

    monkeypatch.setitem(registry.TOOLS, "vault_query", first_handler)
    _reset_canonical(
        registry,
        receipt_path=receipt_path,
        result_path=result_path,
    )
    first = await registry.invoke_canonical(
        "vault_query",
        {"topic": "durability"},
        operation_id=operation_id,
        tenant_id="tenant-a",
        idempotency_key="fixture",
        request_id=str(uuid4()),
    )
    assert first["ok"] is True
    assert first["generation"] == 1
    assert calls["count"] == 1

    async def must_not_replay_effect(_params):
        calls["count"] += 1
        raise AssertionError("durable canonical receipt must fence duplicate effect")

    monkeypatch.setitem(registry.TOOLS, "vault_query", must_not_replay_effect)
    _reset_canonical(
        registry,
        receipt_path=receipt_path,
        result_path=result_path,
    )
    replay = await registry.invoke_canonical(
        "vault_query",
        {"topic": "durability"},
        operation_id=operation_id,
        tenant_id="tenant-a",
        idempotency_key="fixture",
        request_id=str(uuid4()),
    )

    assert replay["ok"] is True
    assert replay["value"] == "durability"
    assert replay["generation"] == 1
    assert replay["receipt"]["receipt_id"] == first["receipt"]["receipt_id"]
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_retired_llm_tool_never_reads_provider_credentials(registry, monkeypatch):
    monkeypatch.setenv("EMERGENT_LLM_KEY", "must-not-be-read")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-read")

    result = await registry.invoke(
        "llm_chat",
        {"prompt": "hello"},
    )

    assert result == {
        "ok": False,
        "error": "provider_tool_retired",
        "tool": "llm_chat",
        "delegate": "skeleton-engine-provider-boundary",
    }
    assert "llm_chat" not in registry.TOOLS
    assert "llm_chat" not in registry._TOOL_MANIFESTS


def test_tool_registry_source_contains_no_shadow_provider_bootstrap() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "tool_registry.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "emergentintegrations",
        "LlmChat(",
        "UserMessage(",
        "EMERGENT_LLM_KEY",
        "OPENAI_API_KEY",
    )
    assert all(marker not in source for marker in forbidden)


def test_backend_topology_persists_canonical_tool_receipts_and_results() -> None:
    compose = (
        Path(__file__).resolve().parents[2]
        / "docker-compose.yml"
    ).read_text(encoding="utf-8")
    assert "BACKEND_TOOL_RECEIPT_PATH=/app/data/backend_tool_receipts.sqlite3" in compose
    assert "BACKEND_TOOL_RESULT_PATH=/app/data/backend_tool_results.sqlite3" in compose
    assert 'com.skeleton.state.role: "declared-mixed-tool-authority-and-derived"' in compose

@pytest.mark.asyncio
async def test_backend_delegate_preserves_lineage_and_restart_replay(
    registry,
    monkeypatch,
    tmp_path,
):
    receipt_path = str(tmp_path / "lineage-tool-receipts.sqlite3")
    result_path = str(tmp_path / "lineage-tool-results.sqlite3")
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    call_id = str(uuid4())
    calls = {"count": 0}

    async def first_handler(params):
        calls["count"] += 1
        return {"ok": True, "value": params["topic"]}

    monkeypatch.setitem(registry.TOOLS, "vault_query", first_handler)
    _reset_canonical(
        registry,
        receipt_path=receipt_path,
        result_path=result_path,
    )
    first = await registry.invoke_canonical(
        "vault_query",
        {"topic": "lineage"},
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        call_id=call_id,
        tenant_id="tenant-a",
        idempotency_key="lineage-replay",
        request_id=str(uuid4()),
    )

    assert first["ok"] is True
    assert first["receipt"]["execution_id"] == execution_id
    assert first["receipt"]["turn_id"] == turn_id
    assert first["receipt"]["call_id"] == call_id
    assert calls["count"] == 1

    async def must_not_execute_again(_params):
        calls["count"] += 1
        raise AssertionError("durable lineage replay must fence duplicate effect")

    monkeypatch.setitem(registry.TOOLS, "vault_query", must_not_execute_again)
    _reset_canonical(
        registry,
        receipt_path=receipt_path,
        result_path=result_path,
    )
    replay = await registry.invoke_canonical(
        "vault_query",
        {"topic": "lineage"},
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        call_id=call_id,
        tenant_id="tenant-a",
        idempotency_key="lineage-replay",
        request_id=str(uuid4()),
    )

    assert replay["ok"] is True
    assert replay["receipt"]["receipt_id"] == first["receipt"]["receipt_id"]
    assert replay["receipt"]["execution_id"] == execution_id
    assert replay["receipt"]["turn_id"] == turn_id
    assert replay["receipt"]["call_id"] == call_id
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_backend_delegate_rejects_idempotency_reuse_with_changed_call_lineage(
    registry,
    monkeypatch,
):
    _reset_canonical(registry)
    calls = {"count": 0}

    async def handler(params):
        calls["count"] += 1
        return {"ok": True, "value": params["topic"]}

    monkeypatch.setitem(registry.TOOLS, "vault_query", handler)
    operation_id = str(uuid4())
    execution_id = str(uuid4())
    turn_id = str(uuid4())
    first_call_id = str(uuid4())

    first = await registry.invoke_canonical(
        "vault_query",
        {"topic": "lineage"},
        operation_id=operation_id,
        execution_id=execution_id,
        turn_id=turn_id,
        call_id=first_call_id,
        tenant_id="tenant-a",
        idempotency_key="lineage-conflict",
        request_id=str(uuid4()),
    )
    assert first["ok"] is True

    with pytest.raises(
        ToolExecutionConflict,
        match="different tool or arguments",
    ):
        await registry.invoke_canonical(
            "vault_query",
            {"topic": "lineage"},
            operation_id=operation_id,
            execution_id=execution_id,
            turn_id=turn_id,
            call_id=str(uuid4()),
            tenant_id="tenant-a",
            idempotency_key="lineage-conflict",
            request_id=str(uuid4()),
        )

    assert calls["count"] == 1

