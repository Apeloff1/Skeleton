"""Routes that previously died during import must mount without external services."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib
import json
import stat
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from pydantic import ValidationError


BOOT_MODULES = (
    "routes.creator_economy",
    "routes.marketplace",
    "routes.git_operations",
    "routes.jeeves_media",
    "routes.lafs",
    "routes.sorting_vault",
    "routes.swarm_cold_legion",
    "routes.swarm_hub",
)


@pytest.mark.parametrize("module_path", BOOT_MODULES)
def test_previously_skipped_routes_import(module_path: str) -> None:
    module = importlib.import_module(module_path)
    assert getattr(module, "router", None) is not None


def test_register_routes_logs_exception_type(capsys) -> None:
    from core.routes_registry import register_routes

    report = register_routes(FastAPI(), [("routes.missing_boot_module", "router")])

    assert report["ok"] == 0
    assert report["skipped"] == 1
    err = capsys.readouterr().err
    assert "import_failed" in err
    assert "ModuleNotFoundError" in err
    assert "routes.missing_boot_module" in err


def test_sorting_rule_allows_actions_without_a_folder() -> None:
    from routes.sorting_vault import SortingRule

    starred = SortingRule(
        id="rule_star",
        name="star",
        conditions=[{"field": "vault_type", "operator": "equals", "value": "ai_generated"}],
        action="star",
        target="",
    )
    assert starred.target == ""
    with pytest.raises(ValidationError):
        SortingRule(
            id="rule_move",
            name="move",
            conditions=[{"field": "tags", "operator": "contains", "value": "game"}],
            action="move_to_folder",
            target="",
        )


def test_git_workspace_is_not_created_at_import(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GIT_WORKSPACE_BASE", raising=False)
    module = importlib.reload(importlib.import_module("routes.git_operations"))
    assert module._workspace_base is None
    monkeypatch.setenv("GIT_WORKSPACE_BASE", str(tmp_path / "repos"))
    module._workspace_base = None
    root = module.workspace_base()
    assert root == (tmp_path / "repos").resolve()
    assert root.is_dir()


def test_gameforge_build_import_does_not_create_artifact_directory(monkeypatch) -> None:
    # The production container has a read-only /app filesystem. Importing
    # build endpoints must not try to initialize /app/backend/artifacts/builds.
    module = importlib.import_module("routes.gameforge_build")

    def reject_mkdir(*args, **kwargs):
        raise AssertionError("GameForge build router wrote during import")

    with monkeypatch.context() as scoped:
        scoped.setattr(module.os, "makedirs", reject_mkdir)
        reloaded = importlib.reload(module)

    paths = {route.path for route in reloaded.router.routes}
    assert {"/api/gameforge/build/web", "/api/gameforge/build/source",
            "/api/gameforge/build/godot"}.issubset(paths)
    from core.gameforge_artifact_builder import DEFAULT_ARTIFACTS_ROOT
    assert reloaded._ARTIFACTS == str(DEFAULT_ARTIFACTS_ROOT)


def test_gameforge_auth_dependency_fails_closed() -> None:
    from fastapi import HTTPException
    from routes import gameforge_build as build, gameforge_auth as auth

    source = (Path(__file__).resolve().parents[1] / "routes/gameforge_build.py").read_text(encoding="utf-8")
    assert "Depends(auth.require_authenticated_identity)" in source
    assert "role" in source and '"editor", "admin"' in source
    assert build._viewer is not build._editor
    for principal in (None, {"tenant_id": "test"}, {"email": "anonymous", "tenant_id": "test"}):
        with pytest.raises(HTTPException) as raised:
            auth.require_authenticated_identity(principal)
        assert raised.value.status_code == 401


@pytest.mark.parametrize("kind", ["web", "source"])
def test_governed_web_and_source_stage_privately_and_cleanup(monkeypatch, kind: str) -> None:
    from routes import gameforge_build as build

    staged: list[Path] = []

    def guarded_artifact_builder(game_name, **options):
        assert game_name == "read-only-image"
        root = Path(options["artifacts_root"])
        assert root.is_dir()
        assert root != Path(build._ARTIFACTS)
        assert stat.S_IMODE(root.stat().st_mode) == 0o700
        assert options["tenant_id"] == "tenant-isolated"
        assert options["governed_store"] is sentinel
        staged.append(root)
        return {"ok": True, "download_url": "/api/gameforge/build/download/fixture"}

    sentinel = object()
    with monkeypatch.context() as scoped:
        scoped.setattr(build, "_governed_store", lambda: sentinel)
        scoped.setattr(build, "_owned_gamefiles", lambda _name, _user: [{"filename": "game.py", "content": "x=1"}])
        scoped.setattr(
            build, "build_web_artifact" if kind == "web" else "build_source_artifact",
            guarded_artifact_builder,
        )
        body = build.BuildBody(game_name="read-only-image")
        endpoint = build._build_web_for_user if kind == "web" else build._build_source_for_user
        result = asyncio.run(endpoint(body, {"tenant_id": "tenant-isolated", "email": "tester@example.test", "role": "editor"}))

    assert result["ok"] is True
    assert len(staged) == 1
    assert not staged[0].exists()  # cleanup holds on all nonexceptional exits


def test_actual_governed_archive_builds_from_private_scratch(monkeypatch) -> None:
    # Exercise the real ZIP builders and registry, not just mocked entrypoints.
    # No live MongoDB, provider secret, writable /app, or native engine needed.
    from core import gameforge_artifact_builder as impl
    from routes import gameforge_build as routes

    saved: dict[tuple[str, str], bytes] = {}
    registered: list[dict] = []

    class Store:
        def write_bytes(self, *, tenant_id, artifact_id, payload, **kwargs):
            assert tenant_id == "tenant-private"
            assert kwargs["data_class"] == "internal"
            assert "download" in kwargs["purposes"]
            saved[(tenant_id, artifact_id)] = bytes(payload)
            return SimpleNamespace(
                record_id="record-" + artifact_id,
                source_ref=f"artifact://{tenant_id}/{artifact_id}",
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )

    class Database:
        def __getitem__(self, name):
            assert name == "gameforge_builds"
            return SimpleNamespace(
                update_one=lambda query, operation, **kwargs:
                    registered.append(operation["$set"]),
            )

    with monkeypatch.context() as scoped:
        scoped.setattr(routes, "_governed_store", Store)
        scoped.setattr(routes, "_owned_gamefiles", lambda _name, _user: [{"filename": "game.py", "content": "print(\'safe\')", "metadata": {"kind": "source"}}])
        scoped.setattr(impl, "database", Database)
        scoped.setattr(impl, "gamefiles", lambda _name: [
            {"filename": "game.py", "content": "print('safe')", "metadata": {"kind": "source"}},
        ])
        body = routes.BuildBody(game_name="read-only-image")
        owner = {"email": "tester@example.test", "tenant_id": "tenant-private", "role": "editor"}
        web = asyncio.run(routes._build_web_for_user(body, owner))
        src = asyncio.run(routes._build_source_for_user(body, owner))

    assert web["ok"] and src["ok"]
    assert len(saved) == 2 and len(registered) == 2
    assert all(rec["path"] is None for rec in registered)
    for rec in registered:
        assert rec["tenant_id"] == "tenant-private"
        assert rec["source_ref"].startswith("artifact://tenant-private/")
        assert len(rec["sha256"]) == 64

    web_zip = saved[("tenant-private", web["build_id"])]
    with ZipFile(BytesIO(web_zip)) as archive:
        assert set(archive.namelist()) == {"index.html", "game_data.json"}
        data = json.loads(archive.read("game_data.json"))
        assert data["files"][0]["filename"] == "game.py"

    source_zip = saved[("tenant-private", src["build_id"])]
    with ZipFile(BytesIO(source_zip)) as archive:
        assert set(archive.namelist()) == {"manifest.json", "gamefiles/game.py"}
        assert archive.read("gamefiles/game.py") == b"print('safe')"
        assert json.loads(archive.read("manifest.json"))["file_count"] == 1


def test_cold_storage_import_does_not_contact_mongo() -> None:
    module = importlib.reload(importlib.import_module("core.cold_storage"))
    assert module._db_handle is None
    assert module._registry_handle is None


def test_checkout_facade_rejects_unsigned_webhook_and_builds_server_amount() -> None:
    from emergentintegrations.payments.stripe.checkout import (
        CheckoutSessionRequest,
        StripeCheckout,
        _session_create_kwargs,
    )

    kwargs = _session_create_kwargs(
        CheckoutSessionRequest(
            amount=1.99,
            currency="usd",
            success_url="https://studio.example/marketplace?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://studio.example/marketplace?cancelled=1",
            metadata={"source": "marketplace", "playable_id": "game-1"},
        )
    )
    assert kwargs["line_items"][0]["price_data"]["unit_amount"] == 199
    assert kwargs["mode"] == "payment"

    checkout = StripeCheckout(api_key="", webhook_url="https://studio.example/api/webhook/stripe")

    async def _reject():
        await checkout.handle_webhook(b"{}", "sig")

    with pytest.raises(RuntimeError, match="webhook secret"):
        import asyncio

        asyncio.run(_reject())
