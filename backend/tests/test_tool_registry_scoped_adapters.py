from __future__ import annotations

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
