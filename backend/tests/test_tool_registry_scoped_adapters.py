from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest


@pytest.fixture
def registry():
    import services.tool_registry as tool_registry

    return tool_registry


@pytest.mark.asyncio
async def test_compile_denial_happens_before_subprocess(registry, monkeypatch):
    called = {"subprocess": 0}

    monkeypatch.setattr(registry, "code_execution_enabled", lambda: True)

    def run(*args, **kwargs):
        called["subprocess"] += 1
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(registry.subprocess, "run", run)

    result = await registry.invoke(
        "compile_code",
        {"language": "python", "code": "print('escape')"},
    )

    assert result == {"ok": False, "error": "tool_denied"}
    assert called["subprocess"] == 0


@pytest.mark.asyncio
async def test_database_scope_denial_happens_before_database_access(registry, monkeypatch):
    called = {"db": 0}

    def db():
        called["db"] += 1
        raise AssertionError("database must not be reached")

    monkeypatch.setattr(registry, "_db", db)

    result = await registry.invoke(
        "mongo_query",
        {"collection": "system.users", "filter": {}},
    )

    assert result == {"ok": False, "error": "tool_denied"}
    assert called["db"] == 0


@pytest.mark.asyncio
async def test_mongo_server_side_javascript_is_denied_before_database(registry, monkeypatch):
    called = {"db": 0}

    def db():
        called["db"] += 1
        raise AssertionError("database must not be reached")

    monkeypatch.setattr(registry, "_db", db)

    result = await registry.invoke(
        "mongo_query",
        {
            "collection": "knowledge",
            "filter": {"$where": "sleep(1000)"},
        },
    )

    assert result == {"ok": False, "error": "tool_denied"}
    assert called["db"] == 0


@pytest.mark.asyncio
async def test_artifact_scope_denial_happens_before_database_or_builder(registry, monkeypatch):
    called = {"db": 0, "builder": 0}
    monkeypatch.setattr(registry, "code_execution_enabled", lambda: True)

    def db():
        called["db"] += 1
        raise AssertionError("database must not be reached")

    async def build(*args, **kwargs):
        called["builder"] += 1
        raise AssertionError("builder must not be reached")

    monkeypatch.setattr(registry, "_db", db)
    monkeypatch.setattr(registry.binary_builder, "package_build", build)

    result = await registry.invoke(
        "package_build",
        {"build_id": "../escape", "kinds": ["zip"]},
    )

    assert result == {"ok": False, "error": "tool_denied"}
    assert called == {"db": 0, "builder": 0}


@pytest.mark.asyncio
async def test_egress_query_bound_denies_before_network_import(registry):
    result = await registry.invoke(
        "web_search",
        {"query": "x" * 513},
    )

    assert result == {"ok": False, "error": "tool_denied"}


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
async def test_legacy_invoke_returns_canonical_receipt(registry, monkeypatch):
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


def test_registry_describe_declares_canonical_authority(registry):
    description = registry.describe()

    assert description["authority"] == "canonical-tool-runtime"
    assert description["count"] == len(registry.TOOLS)
    assert all("effect" in item for item in description["tools"])



@pytest.mark.asyncio
async def test_nested_llm_compat_tool_is_retired_without_credential_access(
    registry,
    monkeypatch,
):
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)

    result = await registry.invoke("llm_chat", {"prompt": "hello"})

    assert result["ok"] is False
    assert result["disabled"] is True
    assert result["error"] == "nested_llm_tool_retired_use_engine_provider"
