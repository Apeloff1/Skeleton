from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
import sys

from skeleton.app.assembly import find_repo_root


def _runtime_module():
    root = find_repo_root(Path(__file__))
    backend = str(root / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    return importlib.import_module("routes.app_runtime")


def test_runtime_status_aggregates_backend_engine_and_mongo(monkeypatch):
    runtime = _runtime_module()

    class FakeDB:
        async def command(self, name: str):
            assert name == "ping"
            return {"ok": 1}

    def fake_engine(timeout_s: float):
        assert timeout_s == 0.5
        return {
            "name": "skeleton",
            "ok": True,
            "status": 200,
            "latency_ms": 7,
            "detail": "healthy",
        }

    monkeypatch.setattr(runtime, "core_db", FakeDB())
    monkeypatch.setattr(runtime, "_probe_engine", fake_engine)

    monkeypatch.setattr(
        runtime,
        "public_readiness",
        lambda: {
            "canonical_actions": 21,
            "ready_actions": 18,
            "ready_pct": 85.7,
            "governed_unbound": 3,
            "unsafe_actions": 0,
            "policy_gaps": 0,
            "attestation_sha256": "abc123",
        },
    )

    payload = asyncio.run(runtime._runtime_status(500))

    assert payload["ok"] is True
    assert payload["application"]["name"] == "Skeleton"
    assert payload["contract"]["ready"] == "/api/app/ready"
    assert [item["name"] for item in payload["services"]] == [
        "backend",
        "skeleton",
        "mongo",
    ]
    assert all(item["ok"] for item in payload["services"])
    assert payload["product"]["available"] is True
    assert payload["product"]["ready_actions"] == 18
    assert payload["product"]["canonical_actions"] == 21


def test_runtime_status_fails_closed_when_state_is_unavailable(monkeypatch):
    runtime = _runtime_module()

    class FailedDB:
        async def command(self, name: str):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(runtime, "core_db", FailedDB())
    monkeypatch.setattr(runtime, "public_readiness", lambda: (_ for _ in ()).throw(RuntimeError("readiness unavailable")))
    monkeypatch.setattr(
        runtime,
        "_probe_engine",
        lambda _timeout: {
            "name": "skeleton",
            "ok": True,
            "status": 200,
            "latency_ms": 1,
            "detail": "healthy",
        },
    )

    payload = asyncio.run(runtime._runtime_status(250))

    assert payload["ok"] is False
    mongo = next(item for item in payload["services"] if item["name"] == "mongo")
    assert mongo["ok"] is False
    assert mongo["detail"] == "RuntimeError"
    assert "database unavailable" not in json.dumps(payload)
    assert payload["product"]["available"] is False
    assert payload["product"]["detail"] == "RuntimeError"
    assert "readiness unavailable" not in json.dumps(payload)


def test_ready_endpoint_uses_http_status_for_whole_app_verdict(monkeypatch):
    runtime = _runtime_module()

    async def healthy(_timeout_ms: int):
        return {"ok": True, "services": []}

    async def degraded(_timeout_ms: int):
        return {"ok": False, "services": []}

    monkeypatch.setattr(runtime, "_runtime_status", healthy)
    healthy_response = asyncio.run(runtime.app_ready(500))
    assert healthy_response.status_code == 200

    monkeypatch.setattr(runtime, "_runtime_status", degraded)
    degraded_response = asyncio.run(runtime.app_ready(500))
    assert degraded_response.status_code == 503


def test_runtime_routes_are_manifest_owned():
    runtime = _runtime_module()

    manifest = runtime._MANIFEST
    paths = {route.path for route in runtime.router.routes}

    assert manifest.contract_path("bootstrap") in paths
    assert manifest.contract_path("status") in paths
    assert manifest.contract_path("ready") in paths
    assert runtime.router.prefix == manifest.public_contract["prefix"]
