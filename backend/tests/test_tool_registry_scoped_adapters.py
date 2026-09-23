from __future__ import annotations

from types import SimpleNamespace
import sys

import pytest


@pytest.fixture
def registry():
    import services.tool_registry as tool_registry
    return tool_registry


@pytest.mark.asyncio
async def test_compile_denial_happens_before_subprocess(registry, monkeypatch):
    called = {"subprocess": 0}
    monkeypatch.setattr(registry, "code_execution_enabled", lambda: True)

    def popen(*args, **kwargs):
        called["subprocess"] += 1
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(registry.subprocess, "Popen", popen)
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
async def test_artifact_byte_ceiling_rejects_before_metadata_persistence(registry, monkeypatch):
    monkeypatch.setattr(registry, "code_execution_enabled", lambda: True)
    persisted = []

    class Builds:
        async def find_one(self, *args, **kwargs):
            return {"build_id": "build-1"}

    class Artifacts:
        async def update_one(self, *args, **kwargs):
            persisted.append((args, kwargs))

    db = SimpleNamespace(galaxy_builds=Builds(), build_artifacts=Artifacts())
    monkeypatch.setattr(registry, "_db", lambda: db)

    async def package_build(*args, **kwargs):
        return {
            "artifacts": [
                {
                    "artifact_id": "zip_build-1",
                    "kind": "zip",
                    "size_bytes": 2048,
                    "path": "/definitely/not/a/real/artifact.zip",
                }
            ],
            "errors": [],
        }

    monkeypatch.setattr(registry.binary_builder, "package_build", package_build)
    result = await registry.invoke(
        "package_build",
        {
            "build_id": "build-1",
            "kinds": ["zip"],
            "max_output_bytes": 1024,
            "retention_days": 3,
        },
    )

    assert result["ok"] is False
    assert result["error"] == "artifact_too_large"
    assert result["artifacts_rejected"] == ["zip_build-1"]
    assert persisted == []


@pytest.mark.asyncio
async def test_egress_query_bound_denies_before_network_import(registry):
    result = await registry.invoke(
        "web_search",
        {"query": "x" * 513},
    )
    assert result == {"ok": False, "error": "tool_denied"}


@pytest.mark.asyncio
async def test_web_search_drops_private_loopback_and_userinfo_results(registry, monkeypatch):
    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results):
            return [
                {"title": "loop", "href": "http://127.0.0.1/admin", "body": "x"},
                {"title": "private", "href": "http://10.0.0.2/a", "body": "x"},
                {"title": "creds", "href": "https://u:p@example.com/a", "body": "x"},
                {"title": "ok", "href": "https://example.com/a", "body": "safe"},
            ]

        def news(self, query, max_results):
            return self.text(query, max_results)

        def images(self, query, max_results):
            return self.text(query, max_results)

    monkeypatch.setitem(sys.modules, "ddgs", SimpleNamespace(DDGS=FakeDDGS))
    result = await registry.invoke(
        "web_search",
        {"query": "safe query", "max_results": 4},
    )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["results"] == [
        {"title": "ok", "url": "https://example.com/a", "snippet": "safe"}
    ]
