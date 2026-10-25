"""Routes that previously died during import must mount without external services."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

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
    assert reloaded._ARTIFACTS.endswith("/artifacts/builds")


def test_gameforge_auth_dependency_fails_closed() -> None:
    # Ensure a missing security module can never reintroduce the previous
    # anonymous dev-admin fallback through an import-time try/except.
    root = Path(__file__).resolve().parents[1]
    source = (root / "routes/gameforge_build.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    auth_imports = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "routes.gameforge_auth"
        and any(alias.name == "require_role" for alias in node.names)
    ]
    assert len(auth_imports) == 1
    assert not any(
        isinstance(node, ast.FunctionDef) and node.name in {"_viewer", "_editor"}
        for node in ast.walk(tree)
    )
    module = importlib.import_module("routes.gameforge_build")
    assert module._viewer is not module._editor
    assert module._viewer.__module__ == "routes.gameforge_auth"
    assert module._editor.__module__ == "routes.gameforge_auth"


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
