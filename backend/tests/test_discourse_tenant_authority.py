"""Account and tenant authority for provider deliberation, history and async receipts."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routes import discourse


ALICE = {"tenant_id": "tenant-1", "owner_id": "alice@example.test"}
BOB = {"tenant_id": "tenant-1", "owner_id": "bob@example.test"}
OTHER_TENANT = {"tenant_id": "tenant-2", "owner_id": "alice@example.test"}


@pytest.fixture(autouse=True)
def _fake_tenant_catalog(monkeypatch):
    from core.discourse_catalog import DeclaredModel, DeclaredPanel

    async def resolve(*, tenant_id, actor_id, selected=None, judge_key=None, maximum=5):
        assert tenant_id and actor_id
        models = tuple(
            DeclaredModel("fixture:" + key, "fixture", key, False)
            for key in (selected or ["model-a"])[:maximum]
        )
        judge_id = judge_key or "judge"
        judge = DeclaredModel("fixture:" + judge_id, "fixture", judge_id, False)
        return DeclaredPanel(
            models, judge,
            "single_model_self_review" if len(models) == 1 else "multiple_models_one_provider",
            False, judge.key not in {item.key for item in models},
        )

    monkeypatch.setattr(discourse, "tenant_panel", resolve)


@pytest.mark.parametrize("identity", [
    None, {}, {"dev_mode": True},
    {"tenant_id": "t", "owner_id": ""},
    {"tenant_id": "", "owner_id": "user"},
    {"tenant_id": "t", "owner_id": "anonymous"},
    {"tenant_id": "t", "owner_id": "\x00"},
    {"tenant_id": " t ", "owner_id": "owner"},
])
def test_untrusted_or_missing_account_scope_rejected(identity):
    with pytest.raises(HTTPException):
        discourse._private_scope(identity)


def test_every_private_route_requires_authorization():
    app = FastAPI()
    app.include_router(discourse.router)
    body = {"task": "creative", "prompt": "Create an original puzzle mechanic"}
    with TestClient(app) as client:
        assert client.get("/api/discourse/panel").status_code == 401
        assert client.get("/api/discourse/history").status_code == 401
        assert client.get("/api/discourse/result/" + "a" * 32).status_code == 401
        assert client.post("/api/discourse/deliberate", json=body).status_code == 401
        assert client.post("/api/discourse/deliberate/async", json=body).status_code == 401


def test_histories_filter_by_tenant_and_owner_without_exposing_owner_columns(monkeypatch):
    seen = []

    class Cursor:
        def sort(self, *_args):
            return self
        def limit(self, n):
            seen.append(("limit", n))
            return self
        async def to_list(self, n):
            assert n == 5
            return [{"deliberation_id": "owner-only"}]

    class Collection:
        def find(self, query, projection):
            seen.append(("query", query))
            seen.append(("projection", projection))
            return Cursor()

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_log=Collection()))
    for identity in [ALICE, BOB, OTHER_TENANT]:
        result = asyncio.run(discourse.history(5, identity=identity))
        assert result["count"] == 1
    assert [x[1] for x in seen if x[0] == "query"] == [ALICE, BOB, OTHER_TENANT]
    assert all(
        entry[1]["tenant_id"] == 0 and entry[1]["owner_id"] == 0
        for entry in seen if entry[0] == "projection"
    )


def test_job_result_cannot_be_read_using_only_a_known_job_id(monkeypatch):
    seen = []

    class Jobs:
        async def find_one(self, query, projection):
            seen.append((query, projection))
            return None

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    result = asyncio.run(discourse.get_result("a" * 32, identity=ALICE))
    assert result == {"error": "not found", "status": "unknown"}
    assert seen[0][0] == {"job_id": "a" * 32, **ALICE}
    assert seen[0][1]["owner_id"] == 0
    assert seen[0][1]["tenant_id"] == 0


def test_deliberation_writes_full_scope_before_reporting_durable(monkeypatch):
    rows = []

    class Collection:
        async def insert_one(self, row):
            rows.append(row)
            return SimpleNamespace(acknowledged=True)

    async def fake_route(*_args, model=None, **_kwargs):
        model = _kwargs.get("model_id", model)
        if model == "judge":
            return {"content": '{"winner_index":0,"scores":[{"index":0,"quality":80,"fidelity":90}]}'}
        return {"content": "Scoped game design proposal"}

    monkeypatch.setattr(discourse, "route_complete", fake_route)
    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_log=Collection()))
    result = asyncio.run(discourse.deliberate(
        "creative", "Create original puzzle game",
        panel=["model-a"], judge_model="judge",
        do_discord=False, identity=ALICE,
    ))
    assert result["persistence_status"] == "durable"
    assert len(rows) == 1
    assert rows[0]["tenant_id"] == ALICE["tenant_id"]
    assert rows[0]["owner_id"] == ALICE["owner_id"]


def test_durable_async_admission_records_owner_before_worker_starts(monkeypatch):
    inserted = []
    queries = []
    discourse._ACTIVE_DELIBERATIONS.clear()

    class Jobs:
        async def insert_one(self, row):
            inserted.append(row)
            return SimpleNamespace(acknowledged=True)
        async def update_one(self, query, update, *, upsert):
            queries.append(query)
            return SimpleNamespace(acknowledged=True, matched_count=1)

    async def fake_deliberate(*_args, **_kwargs):
        return {"winner_model": "model-a", "winner_score": 80}

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    monkeypatch.setattr(discourse, "deliberate", fake_deliberate)

    async def scenario():
        admitted = await discourse.deliberate_async(
            discourse.DeliberateBody(prompt="Build a private puzzle game"),
            identity=ALICE,
        )
        for _ in range(10):
            if not discourse._ACTIVE_DELIBERATIONS:
                break
            await asyncio.sleep(0)
        return admitted

    accepted = asyncio.run(scenario())
    assert accepted["status"] == "running"
    assert inserted[0]["tenant_id"] == ALICE["tenant_id"]
    assert inserted[0]["owner_id"] == ALICE["owner_id"]
    # Terminal compare-and-set must retain both owner scope and the current
    # unforgeable run token; the old fixture incorrectly omitted this guard.
    assert queries == [{
        "job_id": accepted["job_id"], **ALICE,
        "run_token": inserted[0]["run_token"], "status": "running",
    }]
    assert not discourse._ACTIVE_DELIBERATIONS


def test_terminal_job_write_rejects_unmatched_owner_record(monkeypatch):
    updates = []
    discourse._ACTIVE_DELIBERATIONS.clear()

    class Jobs:
        async def update_one(self, query, update, *, upsert):
            updates.append((query, update["$set"]["status"]))
            return SimpleNamespace(acknowledged=True, matched_count=0)

    async def fake_deliberate(*_args, **_kwargs):
        return {"winner_model": "model-a", "winner_score": 80}

    monkeypatch.setattr(discourse, "_db", SimpleNamespace(discourse_jobs=Jobs()))
    monkeypatch.setattr(discourse, "deliberate", fake_deliberate)
    asyncio.run(discourse._run_bg(
        "a" * 32, discourse.DeliberateBody(prompt="Build private game"), ALICE,
    ))
    assert [state for _query, state in updates] == ["done", "error"]
    assert all(query["owner_id"] == ALICE["owner_id"] for query, _ in updates)


def test_disclosure_safe_validation_and_catalog_error_envelopes(monkeypatch):
    """Never return provider, prompt or catalog exception strings to clients."""
    secret = "Bearer private-repository-provider-credential"

    async def unavailable(**_kwargs):
        raise discourse.PanelUnavailable(secret)

    monkeypatch.setattr(discourse, "tenant_panel", unavailable)
    panel = asyncio.run(discourse.get_panel(identity=ALICE))
    direct = asyncio.run(discourse.deliberate(
        "creative", "Create an original puzzle world", identity=ALICE,
    ))
    admission = asyncio.run(discourse.deliberate_async(
        discourse.DeliberateBody(prompt="Create an original puzzle world"),
        identity=ALICE,
    ))
    for public in (panel, direct, admission):
        assert secret not in json.dumps(public)
    assert panel["readiness"] == "model_panel_unavailable"
    assert direct["error"] == admission["error"] == "model_panel_unavailable"

    def invalid(*_args, **_kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(discourse, "_admit", invalid)
    direct = asyncio.run(discourse.deliberate(
        "creative", "Create an original puzzle world", identity=ALICE,
    ))
    admission = asyncio.run(discourse.deliberate_async(
        discourse.DeliberateBody(prompt="Create an original puzzle world"),
        identity=ALICE,
    ))
    for public in (direct, admission):
        assert public == {"error": "invalid_deliberation_request"}
        assert secret not in json.dumps(public)
