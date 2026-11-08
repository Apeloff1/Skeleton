"""Offline tenant-owned model selection and actual canonical discourse execution."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core import discourse_catalog as catalog
from routes import discourse


ALICE = {"tenant_id": "tenant-a", "owner_id": "alice@example.test"}


def _row(provider: str, model: str, *, active: bool = False, selectable: bool = True):
    return {
        "id": provider + ":" + model,
        "provider_id": provider,
        "model_id": model,
        "selectable": selectable,
        "available": selectable,
        "active": active,
    }


def _catalog(*models):
    return {"models": list(models)}


def test_one_actual_engine_model_is_a_disclosed_self_review():
    result = catalog._catalog_panel(
        _catalog(_row("local", "gguf-small", active=True)),
        selected=None, judge_key=None,
    )
    assert [row.key for row in result.models] == ["local:gguf-small"]
    assert result.judge.key == "local:gguf-small"
    assert result.mode == "single_model_self_review"
    assert result.independent_judge is False
    assert result.provider_diverse is False


def test_multiple_providers_prioritized_over_multiple_same_vendor_models():
    result = catalog._catalog_panel(
        _catalog(
            _row("openai", "first", active=True),
            _row("openai", "second"),
            _row("local", "gguf"),
            _row("anthropic", "other"),
        ),
        selected=None, judge_key=None, maximum=3,
    )
    assert result.models[0].key == "openai:first"
    assert len({row.provider_id for row in result.models}) == 3
    assert result.mode == "cross_provider"
    assert result.provider_diverse is True
    assert result.independent_judge is True
    assert result.available_models == (
        "anthropic:other", "local:gguf", "openai:first", "openai:second"
    )


@pytest.mark.parametrize("requested", [
    ["openai:not-available"],
    ["openai:first", "openai:first"],
    ["openai:first", "openai:private"],
])
def test_runtime_catalog_rejects_unknown_duplicate_or_unready_selections(requested):
    with pytest.raises(catalog.PanelUnavailable):
        catalog._catalog_panel(
            _catalog(
                _row("openai", "first", active=True),
                _row("openai", "private", selectable=False),
            ),
            selected=requested, judge_key=None,
        )


def test_runtime_catalog_cannot_use_unavailable_judge():
    with pytest.raises(catalog.PanelUnavailable, match="judge"):
        catalog._catalog_panel(
            _catalog(_row("local", "gguf", active=True)),
            selected=None, judge_key="openai:undeclared",
        )


def test_duplicate_engine_inventory_identity_is_not_accepted():
    row = _row("local", "gguf", active=True)
    with pytest.raises(catalog.PanelUnavailable, match="duplicate"):
        catalog._catalog_panel(_catalog(row, dict(row)), selected=None, judge_key=None)


def test_empty_or_unready_catalog_does_not_fabricate_panel():
    for payload in (
        _catalog(),
        _catalog(_row("local", "gguf", active=True, selectable=False)),
    ):
        with pytest.raises(catalog.PanelUnavailable, match="no_executable_models"):
            catalog._catalog_panel(payload, selected=None, judge_key=None)


def test_tenant_inventory_resolution_passes_exact_identity(monkeypatch):
    seen = []

    async def fake_catalog(_client, *, actor_id, tenant_id):
        seen.append((actor_id, tenant_id))
        return _catalog(_row("local", "gguf", active=True))

    monkeypatch.setattr(catalog.EngineClient, "from_env", lambda: object())
    monkeypatch.setattr(catalog, "model_catalog", fake_catalog)
    resolved = asyncio.run(catalog.tenant_panel(
        actor_id="alice@example.test", tenant_id="tenant-a",
    ))
    assert resolved.models[0].key == "local:gguf"
    assert seen == [("alice@example.test", "tenant-a")]


def test_unconfigured_engine_does_not_create_execution_models(monkeypatch):
    async def fake_catalog(client, **_kwargs):
        assert client is None
        return {"models": []}

    monkeypatch.setattr(catalog.EngineClient, "from_env", lambda: None)
    monkeypatch.setattr(catalog, "model_catalog", fake_catalog)
    with pytest.raises(catalog.PanelUnavailable):
        asyncio.run(catalog.tenant_panel(actor_id="alice", tenant_id="tenant-a"))


def _declared_panel(*models, judge):
    rows = tuple(catalog.DeclaredModel(p + ":" + m, p, m, i == 0)
                 for i, (p, m) in enumerate(models))
    j = catalog.DeclaredModel(judge[0] + ":" + judge[1], judge[0], judge[1], False)
    return catalog.DeclaredPanel(
        models=rows, judge=j,
        mode=("single_model_self_review" if len(rows) == 1 else "cross_provider"),
        provider_diverse=len({p for p, _ in models}) > 1,
        independent_judge=j.key not in {row.key for row in rows},
    )


def test_single_model_request_runs_real_catalog_selection_and_reports_self_review(monkeypatch):
    declared = _declared_panel(("local", "gguf"), judge=("local", "gguf"))
    source_calls, stored = [], []

    async def get_panel(**kwargs):
        assert kwargs["tenant_id"] == ALICE["tenant_id"]
        assert kwargs["actor_id"] == ALICE["owner_id"]
        return declared

    async def complete(task, prompt, system, **kwargs):
        source_calls.append(kwargs)
        assert "model" not in kwargs
        assert kwargs["provider_id"] == "local"
        assert kwargs["model_id"] == "gguf"
        assert kwargs["tenant_id"] == ALICE["tenant_id"]
        assert kwargs["actor_id"] == ALICE["owner_id"]
        if "CANDIDATES:" in prompt:
            return {"content": '{"scores":[{"index":0,"quality":80,"fidelity":90}],"winner_index":0}'}
        return {"content": "Original responsive puzzle design proposal", "execution_id": "execution-1"}

    class Log:
        async def insert_one(self, row):
            stored.append(row)
            return SimpleNamespace(acknowledged=True)

    monkeypatch.setattr(discourse, "tenant_panel", get_panel)
    monkeypatch.setattr(discourse, "route_complete", complete)
    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_log=Log()))
    result = asyncio.run(discourse.deliberate(
        "creative", "Create an original game",
        panel=None, do_discord=False, identity=ALICE,
    ))
    assert result["winner_model"] == "local:gguf"
    assert result["judge_model"] == "local:gguf"
    assert result["deliberation_mode"] == "single_model_self_review"
    assert result["judge_status"] == "self_scored"
    assert result["provider_diverse"] is False
    assert result["persistence_status"] == "durable"
    assert len(source_calls) == 2
    assert stored[0]["owner_id"] == ALICE["owner_id"]


def test_cross_provider_panel_executes_exact_model_pairs(monkeypatch):
    declared = _declared_panel(
        ("openai", "gpt"), ("local", "gguf"), judge=("anthropic", "sonnet"),
    )
    seen = []
    async def get_panel(**_kwargs):
        return declared

    async def complete(task, prompt, system, **kwargs):
        seen.append((kwargs["provider_id"], kwargs["model_id"]))
        if kwargs["provider_id"] == "anthropic":
            return {"content": '{"scores":[{"index":0,"quality":75,"fidelity":80},'
                               '{"index":1,"quality":90,"fidelity":90}],"winner_index":1}'}
        return {"content": "Original game design proposal"}

    class Log:
        async def insert_one(self, row):
            return SimpleNamespace(acknowledged=True)

    monkeypatch.setattr(discourse, "tenant_panel", get_panel)
    monkeypatch.setattr(discourse, "route_complete", complete)
    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_log=Log()))
    result = asyncio.run(discourse.deliberate(
        "creative", "Build a game",
        do_discord=False, identity=ALICE,
    ))
    assert result["winner_model"] == "local:gguf"
    assert result["provider_diverse"] is True
    assert result["independent_judge"] is True
    assert result["deliberation_mode"] == "cross_provider"
    assert seen == [("openai", "gpt"), ("local", "gguf"), ("anthropic", "sonnet")]


def test_unavailable_catalog_never_contacts_provider_or_database(monkeypatch):
    async def unready(**_kwargs):
        raise catalog.PanelUnavailable("no_executable_models")
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("provider should not be contacted")
    monkeypatch.setattr(discourse, "tenant_panel", unready)
    monkeypatch.setattr(discourse, "route_complete", forbidden)
    result = asyncio.run(discourse.deliberate(
        "creative", "Create an original game", identity=ALICE,
    ))
    assert result["error"] == "model_panel_unavailable"
    assert result["reason"] == "no_executable_models"


def test_no_ready_models_does_not_admit_async_job(monkeypatch):
    async def unavailable(**_kwargs):
        raise catalog.PanelUnavailable("no_executable_models")

    class ForbiddenDB:
        @property
        def discourse_jobs(self):
            raise AssertionError("no durable admission without executable models")

    monkeypatch.setattr(discourse, "_ACTIVE_DELIBERATIONS", set())
    monkeypatch.setattr(discourse, "tenant_panel", unavailable)
    monkeypatch.setattr(discourse, "_db", ForbiddenDB())
    result = asyncio.run(discourse.deliberate_async(
        discourse.DeliberateBody(prompt="Build a usable game"),
        identity=ALICE,
    ))
    assert result["error"] == "model_panel_unavailable"
    assert not discourse._ACTIVE_DELIBERATIONS
