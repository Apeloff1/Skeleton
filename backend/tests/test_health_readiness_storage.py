"""Readiness must preserve vault contents and reflect the required database."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import shutil
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

import server
from core import build_vault, compressed_vault
from routes import app_runtime, galaxy_studio, registry_health
from services import database


@pytest.fixture
def vaults(tmp_path, monkeypatch):
    galaxy = tmp_path / "galaxy"
    builds = tmp_path / "builds"
    for path in (galaxy, builds):
        path.mkdir()
        (path / ".probe").write_text("existing readiness data")
        (path / ".probe_rw").write_text("existing vault data")
    monkeypatch.setattr(galaxy_studio, "VAULT_DIR", str(galaxy))
    monkeypatch.setattr(build_vault, "BUILDS_ROOT", builds)
    monkeypatch.setattr(build_vault, "BUILDS_VAULT_FALLBACK", False)
    monkeypatch.setattr(registry_health, "critical_router_readiness", lambda: {"ok": True})
    monkeypatch.setattr(server, "ai_service", SimpleNamespace(available=False, provider_status=lambda: "unavailable"))
    return galaxy, builds


@pytest.mark.asyncio
async def test_readiness_tracks_database_recovery_without_harming_vault_files(vaults, monkeypatch):
    ping = AsyncMock(side_effect=ConnectionError("database unavailable"))
    monkeypatch.setattr(database, "db", SimpleNamespace(command=ping))
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/api/health/live")
        unavailable = await client.get("/api/health/ready")
        ping.side_effect = None
        ping.return_value = {"ok": 1}
        recovered = await client.get("/api/health/ready")
        vault = await client.get("/api/health/vault")

    assert live.status_code == 200
    assert unavailable.status_code == 503
    assert unavailable.json() == {"detail": "internal server error"}
    assert recovered.status_code == 200
    assert recovered.json()["checks"]["mongo"]["ok"] is True
    assert recovered.json()["canonical_application"] == {
        "name": "Skeleton", "version": "16.0.0", "component": "backend", "ingress_prefix": "/api"
    }
    assert "canonical_application" not in unavailable.json()
    assert vault.status_code == 200
    for path in vaults:
        assert (path / ".probe").read_text() == "existing readiness data"
        assert (path / ".probe_rw").read_text() == "existing vault data"
        assert sorted(p.name for p in path.iterdir()) == [".probe", ".probe_rw"]


def test_vault_probes_do_not_collide_when_run_concurrently(vaults):
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(server._probe_vault_io, [vaults[0]] * 100))
    assert sorted(p.name for p in vaults[0].iterdir()) == [".probe", ".probe_rw"]


@pytest.mark.asyncio
async def test_stalled_vault_probe_is_bounded_single_flight_and_liveness_stays_responsive(vaults, monkeypatch):
    monkeypatch.setattr(database, "db", SimpleNamespace(command=AsyncMock(return_value={"ok": 1})))
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def blocked(_path):
        calls.append(1)
        entered.set()
        if not release.wait(10):
            raise TimeoutError("test worker timed out")

    monkeypatch.setattr(server, "_probe_vault_io", blocked)
    try:
        first = asyncio.create_task(server.health_ready())
        second = asyncio.create_task(server.health_ready())
        assert await asyncio.to_thread(entered.wait, 2)
        live = await asyncio.wait_for(server.health_live(), timeout=0.25)
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
        assert live["status"] == "live"
        assert all(result.status_code == 503 for result in results)
        assert len(calls) == 1  # Both callers shared the same blocked worker.
    finally:
        release.set()
        task = getattr(server.app.state, "_vault_observation_ready", None)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=2)


@pytest.mark.asyncio
async def test_mongo_and_vault_observations_run_concurrently(vaults, monkeypatch):
    mongo_started = threading.Event()
    vault_started = threading.Event()
    original_probe = server._probe_vault_io

    async def ping(_command):
        mongo_started.set()
        if not await asyncio.to_thread(vault_started.wait, 0.8):
            raise TimeoutError("vault observation did not start alongside Mongo")
        return {"ok": 1}

    def observe(path):
        vault_started.set()
        assert mongo_started.wait(0.8), "Mongo did not start alongside vault observation"
        original_probe(path)

    monkeypatch.setattr(database, "db", SimpleNamespace(command=ping))
    monkeypatch.setattr(server, "_probe_vault_io", observe)
    result = await asyncio.wait_for(server.health_ready(), timeout=2.5)
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_unwritable_vault_fails_readiness(vaults, monkeypatch):
    monkeypatch.setattr(database, "db", SimpleNamespace(command=AsyncMock(return_value={"ok": 1})))
    monkeypatch.setattr(server, "_probe_vault_io", lambda _path: (_ for _ in ()).throw(PermissionError()))
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "internal server error"}


@pytest.mark.asyncio
async def test_temporary_vault_fallback_is_not_reported_ready(vaults, monkeypatch):
    monkeypatch.setattr(database, "db", SimpleNamespace(command=AsyncMock(return_value={"ok": 1})))
    monkeypatch.setattr(build_vault, "BUILDS_VAULT_FALLBACK", True)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ready = await client.get("/api/health/ready")
        vault = await client.get("/api/health/vault")
    assert ready.status_code == 503
    assert ready.json() == {"detail": "internal server error"}
    assert vault.status_code == 503
    assert vault.json() == {"detail": "internal server error"}


@pytest.mark.asyncio
async def test_deep_vault_degraded_response_serializes_path_object(vaults, monkeypatch):
    monkeypatch.setattr(galaxy_studio, "VAULT_DIR", vaults[0])
    monkeypatch.setattr(build_vault, "BUILDS_VAULT_FALLBACK", True)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/vault")
    assert response.status_code == 503
    assert response.json() == {"detail": "internal server error"}
    assert str(vaults[0]) not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("disk_failure", [True, False])
async def test_deep_vault_checks_selected_storage_and_fails_closed(vaults, monkeypatch, disk_failure):
    observed_paths = []

    def disk_usage(path):
        observed_paths.append(path)
        if disk_failure:
            raise OSError("disk unavailable")
        return 1000, 960, 40

    monkeypatch.setattr(shutil, "disk_usage", disk_usage)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/vault")
    assert observed_paths == [str(vaults[1])]
    assert response.status_code == 503
    assert response.json() == {"detail": "internal server error"}


@pytest.mark.asyncio
async def test_application_status_includes_real_backend_readiness(vaults, monkeypatch):
    healthy_db = SimpleNamespace(command=AsyncMock(return_value={"ok": 1}))
    monkeypatch.setattr(database, "db", healthy_db)
    monkeypatch.setattr(app_runtime, "core_db", healthy_db)
    monkeypatch.setattr(app_runtime, "public_readiness", lambda: {})
    monkeypatch.setattr(app_runtime, "_probe_engine", AsyncMock(return_value={
        "name": "skeleton", "ok": True, "status": 200, "latency_ms": 0, "detail": "healthy"
    }))
    monkeypatch.setattr(build_vault, "BUILDS_VAULT_FALLBACK", True)
    app = FastAPI()
    app.include_router(app_runtime.router)
    app.state.backend_readiness_probe = server.health_ready
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/app/ready", params={"timeout_ms": 1000})
    assert response.status_code == 503
    backend = next(item for item in response.json()["services"] if item["name"] == "backend")
    assert backend["ok"] is False


def test_vault_initialization_preserves_existing_probe_files_and_checks_fallback(tmp_path):
    preferred = tmp_path / "persistent"
    preferred.mkdir()
    sentinel = preferred / ".w_probe"
    sentinel.write_text("user data")
    assert build_vault._resolve_writable_dir(str(preferred), str(tmp_path / "fallback")) == preferred
    assert sentinel.read_text() == "user data"
    assert sorted(p.name for p in preferred.iterdir()) == [".w_probe"]

    unavailable = tmp_path / "not-a-directory"
    unavailable.write_text("file")
    fallback = tmp_path / "fallback"
    assert build_vault._resolve_writable_dir(str(unavailable), str(fallback)) == fallback
    assert list(fallback.iterdir()) == []


def test_compressed_vault_does_not_overwrite_existing_probe_file(tmp_path):
    sentinel = tmp_path / ".writable_test"
    sentinel.write_text("user data")
    assert compressed_vault._resolve_writable_dir(str(tmp_path), str(tmp_path / "fallback")) == tmp_path
    assert sentinel.read_text() == "user data"
    assert list(tmp_path.iterdir()) == [sentinel]
