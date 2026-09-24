from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from skeleton.skills.tool_contract import approval_ref_for_request


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


def _reset_canonical(registry):
    registry._CANONICAL_RUNTIME = registry.AsyncToolRuntime()
    registry._CANONICAL_RESULT_STORE = registry._CompatibilityResultStore()
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
    assert all("effect" in item for item in description["tools"])
    package = next(item for item in description["tools"] if item["name"] == "package_build")
    assert package["approval_required"] is True
    assert package["idempotency_required"] is True
