"""ASGI/JWT canaries for indirect Galaxy source, execution and job authority."""
from __future__ import annotations

import copy
import threading
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
import pytest

from core import autonomous_orchestrator as orch, churn_2_service as churn
from core import databases, text_gamefile, build_ledger, provenance_ledger
from routes import churn as churn_routes, orchestrator as orch_routes, gameforge_auth as auth
from routes import galaxy_studio_state as state
from routes import galaxy_studio_access as access


def matches(row, query):
    return all((row.get(k) != v["$ne"] if isinstance(v, dict) and "$ne" in v else row.get(k) == v)
               for k, v in query.items())


class Collection:
    def __init__(self):
        self.rows = []
        self.queries = []
        self.writes = []

    @staticmethod
    def project(row, projection):
        result = copy.deepcopy(row)
        included = {k for k, v in (projection or {}).items() if v}
        if included:
            result = {k: v for k, v in result.items() if k in included}
        else:
            for key, value in (projection or {}).items():
                if not value:
                    result.pop(key, None)
        return result

    def find_one(self, query, projection=None):
        self.queries.append(copy.deepcopy(query))
        row = next((row for row in self.rows if matches(row, query)), None)
        return self.project(row, projection) if row is not None else None

    def find(self, query, projection=None):
        self.queries.append(copy.deepcopy(query))
        rows = [self.project(row, projection) for row in self.rows if matches(row, query)]

        class Cursor(list):
            def sort(self, *args):
                return self

            def limit(self, count):
                return self[:count]

        return Cursor(rows)

    def replace_one(self, query, document, upsert=False):
        self.writes.append((copy.deepcopy(query), copy.deepcopy(document)))
        for index, row in enumerate(self.rows):
            if matches(row, query):
                self.rows[index] = copy.deepcopy(document)
                return
        if upsert:
            self.rows.append(copy.deepcopy(document))

    def distinct(self, *args):
        raise AssertionError("Private builds must never be discovered by a global gamefile scan")


@pytest.fixture
def private_http(monkeypatch):
    db = {name: Collection() for name in (
        "gameforge_users", "user_sessions", "galaxy_builds", "galaxy_text_gamefiles",
        "galaxy_churn_runs", "galaxy_build_plans")}
    monkeypatch.setattr(databases, "get_sync_db", lambda *args: db)
    monkeypatch.setattr(auth, "_secret", lambda: "test-private-galaxy-key-with-32-bytes")
    # The private consumers must require real authentication in local mode too.
    monkeypatch.setattr(auth, "_enforced", lambda: False)
    users = {
        "owner": {"email": "owner@example.test", "tenant_id": "tenant-a", "role": "editor"},
        "other": {"email": "other@example.test", "tenant_id": "tenant-a", "role": "editor"},
        "foreign": {"email": "foreign@example.test", "tenant_id": "tenant-b", "role": "editor"},
        "admin": {"email": "admin@example.test", "tenant_id": "tenant-a", "role": "admin"},
        "viewer": {"email": "viewer@example.test", "tenant_id": "tenant-a", "role": "viewer"},
    }
    db["gameforge_users"].rows = list(users.values())
    builds = {
        "own": {"build_id": "own", "tenant_id": "tenant-a", "owner_id": users["owner"]["email"]},
        "own-2": {"build_id": "own-2", "tenant_id": "tenant-a", "owner_id": users["owner"]["email"]},
        "other": {"build_id": "other", "tenant_id": "tenant-a", "owner_id": users["other"]["email"]},
        "foreign": {"build_id": "foreign", "tenant_id": "tenant-b", "owner_id": users["foreign"]["email"]},
        "cross-tenant": {"build_id": "cross-tenant", "tenant_id": "tenant-b", "owner_id": users["owner"]["email"]},
        "viewer": {"build_id": "viewer", "tenant_id": "tenant-a", "owner_id": users["viewer"]["email"]},
        "legacy": {"build_id": "legacy"},
    }
    monkeypatch.setattr(state, "_builds", builds)
    db["galaxy_builds"].rows = list(builds.values())
    for bid, build in builds.items():
        db["galaxy_text_gamefiles"].rows.append({
            "_id": f"{bid}:file", "id": "file", "build_id": bid, "label": f"secret-{bid}",
            "type": "quest", "source_text": f"private-source-{bid}", "fields": {"lore": "thin"}})
        db["galaxy_churn_runs"].rows.append({
            "_id": f"run-{bid}", "run_id": f"run-{bid}", **build, "gid": "file",
            "alternatives": [{"variant_id": "choice", "fields_delta": {"lore": f"changed-{bid}"}}]})
        db["galaxy_build_plans"].rows.append({
            "_id": f"plan-{bid}", "plan_id": f"plan-{bid}", **build, "version": 1, "status": "planned",
            "directive": f"private-plan-{bid}", "nodes": [], "created": 0})
    db["galaxy_churn_runs"].rows.append({"_id": "unowned-run", "build_id": "own", "gid": "file"})
    db["galaxy_build_plans"].rows.append({"_id": "unowned-plan", "build_id": "own", "nodes": []})
    monkeypatch.setattr(churn, "_JOBS", {})
    monkeypatch.setattr(churn, "_DAEMONS", {})
    monkeypatch.setattr(orch, "_JOBS", {})
    monkeypatch.setattr(build_ledger, "log", lambda *args, **kwargs: None)
    monkeypatch.setattr(provenance_ledger, "append", lambda *args, **kwargs: None)
    workers = []

    class HeldThread:
        def __init__(self, target, args=(), **kwargs):
            self.target, self.args = target, args

        def start(self):
            workers.append(self)

    for engine in (churn, orch):
        monkeypatch.setattr(engine, "threading", SimpleNamespace(Thread=HeldThread, Event=threading.Event))
    app = FastAPI()
    app.include_router(churn_routes.router)
    app.include_router(orch_routes.router)
    tokens = {name: auth.create_access_token(sub=user["email"], role=user["role"]) for name, user in users.items()}
    yield SimpleNamespace(app=app, db=db, builds=builds, users=users, tokens=tokens, workers=workers)
    for daemon in churn._DAEMONS.values():
        daemon["stop"].set()


async def request(h, method, path, account="owner", **kwargs):
    headers = {"Authorization": "Bearer " + h.tokens[account]} if account else {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=h.app), base_url="http://private.test") as client:
        return await client.request(method, path, headers=headers, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", [
    ("GET", "/api/churn/own/analyze", None),
    ("GET", "/api/churn/own/file/analyze", None),
    ("POST", "/api/churn/own/run/async", {}),
    ("GET", "/api/churn/own/runs", None),
    ("POST", "/api/churn/own/file/apply", {"run_id": "run-own", "variant_id": "choice"}),
    ("GET", "/api/churn/job/unknown", None),
    ("POST", "/api/churn/job/unknown/cancel", None),
    ("GET", "/api/churn/daemon/status", None),
    ("POST", "/api/churn/daemon/toggle", {"enabled": False}),
    ("POST", "/api/orchestrator/own/plan", {}),
    ("GET", "/api/orchestrator/own/plans", None),
    ("GET", "/api/orchestrator/plan/plan-own", None),
    ("POST", "/api/orchestrator/plan/plan-own/execute/async", None),
    ("POST", "/api/orchestrator/plan/plan-own/replan", {"node_id": "n1"}),
    ("GET", "/api/orchestrator/job/unknown", None),
    ("POST", "/api/orchestrator/job/unknown/cancel", None),
])
async def test_anonymous_dispatch_is_401_in_every_mode(private_http, method, path, body):
    response = await request(private_http, method, path, account=None, json=body)
    assert response.status_code == 401, response.text
    assert not private_http.workers


@pytest.mark.asyncio
@pytest.mark.parametrize("account", ["other", "foreign", "admin"])
async def test_foreign_owner_and_tenant_are_404_before_source_work(private_http, account):
    h = private_http
    paths = [("GET", "/api/churn/own/analyze", None),
             ("POST", "/api/churn/own/run/async", {}),
             ("GET", "/api/churn/own/runs", None),
             ("POST", "/api/orchestrator/own/plan", {}),
             ("GET", "/api/orchestrator/own/plans", None),
             ("GET", "/api/orchestrator/plan/plan-own", None),
             ("POST", "/api/orchestrator/plan/plan-own/execute/async", None),
             ("POST", "/api/orchestrator/plan/plan-own/replan", {"node_id": "n1"})]
    for method, path, body in paths:
        response = await request(h, method, path, account, json=body)
        assert response.status_code == 404, (path, response.text)
        assert "private-" not in response.text
    assert not h.db["galaxy_text_gamefiles"].queries and not h.workers


@pytest.mark.asyncio
async def test_same_owner_in_different_tenant_and_unowned_build_fail_closed(private_http):
    for bid in ["cross-tenant", "legacy"]:
        assert (await request(private_http, "GET", f"/api/churn/{bid}/analyze")).status_code == 404
        assert (await request(private_http, "GET", f"/api/orchestrator/plan/plan-{bid}")).status_code == 404


@pytest.mark.asyncio
async def test_real_owner_reads_and_applies_only_matching_build_file_run(private_http):
    h = private_http
    response = await request(h, "GET", "/api/churn/own/file/analyze")
    assert response.status_code == 200 and response.json()["label"] == "secret-own"
    for run_id in ["run-own-2", "run-other", "run-foreign", "unowned-run"]:
        response = await request(h, "POST", "/api/churn/own/file/apply", json={"run_id": run_id, "variant_id": "choice"})
        assert response.status_code == 404, response.text
    wrong_file = await request(h, "POST", "/api/churn/own/other-file/apply", json={"run_id": "run-own", "variant_id": "choice"})
    assert wrong_file.status_code == 404
    assert not h.db["galaxy_text_gamefiles"].writes
    applied = await request(h, "POST", "/api/churn/own/file/apply", json={"run_id": "run-own", "variant_id": "choice"})
    assert applied.status_code == 200 and applied.json()["applied"] == "choice"
    assert h.db["galaxy_churn_runs"].queries[-1] == {
        "_id": "run-own", "build_id": "own", "tenant_id": "tenant-a", "owner_id": h.users["owner"]["email"]}
    runs = (await request(h, "GET", "/api/churn/own/runs")).json()["runs"]
    assert [run["run_id"] for run in runs] == ["run-own"]


@pytest.mark.asyncio
async def test_owner_plan_round_trip_and_historical_unowned_plan_is_hidden(private_http):
    h = private_http
    created = await request(h, "POST", "/api/orchestrator/own/plan", json={"directive": "Private review", "steps": [{"kind": "review"}]})
    assert created.status_code == 200, created.text
    plan = created.json()
    assert plan["owner_id"] == h.users["owner"]["email"] and plan["tenant_id"] == "tenant-a"
    assert (await request(h, "GET", "/api/orchestrator/plan/" + plan["plan_id"])).json() == plan
    assert (await request(h, "POST", "/api/orchestrator/plan/" + plan["plan_id"] + "/replan", json={"node_id": "n1"})).status_code == 200
    assert (await request(h, "GET", "/api/orchestrator/plan/unowned-plan")).status_code == 404


def run_worker(h):
    held = h.workers[-1]
    worker = threading.Thread(target=held.target, args=held.args)
    worker.start()
    worker.join(timeout=5)
    assert not worker.is_alive()


@pytest.mark.asyncio
@pytest.mark.parametrize("engine,path", [(churn, "/api/churn/own/run/async"), (orch, "/api/orchestrator/plan/plan-own/execute/async")])
async def test_jobs_bind_principal_and_build_through_a_real_thread(private_http, engine, path):
    h = private_http
    response = await request(h, "POST", path, json={"gid": "file"} if engine is churn else None)
    assert response.status_code == 200, response.text
    jid = response.json()["job_id"]
    prefix = "/api/churn" if engine is churn else "/api/orchestrator"
    for account in ["other", "foreign", "admin"]:
        assert (await request(h, "GET", prefix + "/job/" + jid, account)).status_code == 404
        assert (await request(h, "POST", prefix + "/job/" + jid + "/cancel", account)).status_code == 404
    assert access._request_user.get() is None
    run_worker(h)
    polled = await request(h, "GET", prefix + "/job/" + jid)
    assert polled.status_code == 200 and polled.json()["status"] == "done", polled.text
    assert polled.json()["result"]
    h.builds["own"]["owner_id"] = h.users["other"]["email"]
    assert (await request(h, "GET", prefix + "/job/" + jid)).status_code == 404
    assert (await request(h, "GET", prefix + "/job/" + jid, "other")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("engine,path", [(churn, "/api/churn/own/run/async"), (orch, "/api/orchestrator/plan/plan-own/execute/async")])
@pytest.mark.parametrize("change", ["disabled", "tenant", "role", "build-owner", "cancel"])
async def test_queued_worker_revalidates_before_source_or_side_effects(private_http, engine, path, change):
    h = private_http
    kicked = await request(h, "POST", path, json={"gid": "file"} if engine is churn else None)
    jid = kicked.json()["job_id"]
    if change == "disabled":
        h.users["owner"]["disabled"] = True
    elif change == "tenant":
        h.users["owner"]["tenant_id"] = "tenant-b"
    elif change == "role":
        h.users["owner"]["role"] = "viewer"
    elif change == "build-owner":
        h.builds["own"]["owner_id"] = h.users["other"]["email"]
    else:
        prefix = "/api/churn" if engine is churn else "/api/orchestrator"
        assert (await request(h, "POST", prefix + "/job/" + jid + "/cancel")).status_code == 200
    run_worker(h)
    assert engine._JOBS[jid]["status"] == ("cancelled" if change == "cancel" else "error")
    assert engine._JOBS[jid]["result"] is None
    assert not h.db["galaxy_text_gamefiles"].queries and not h.db["galaxy_churn_runs"].writes


@pytest.mark.asyncio
async def test_viewer_can_read_own_source_but_cannot_dispatch_mutations(private_http):
    h = private_http
    assert (await request(h, "GET", "/api/churn/viewer/analyze", "viewer")).status_code == 200
    for path, body in [("/api/churn/viewer/run/async", {}),
                       ("/api/orchestrator/viewer/plan", {}),
                       ("/api/churn/daemon/toggle", {"enabled": True, "build_ids": ["viewer"]})]:
        assert (await request(h, "POST", path, "viewer", json=body)).status_code == 403
    assert not h.workers


@pytest.mark.asyncio
async def test_daemon_only_uses_explicit_owned_ids_and_private_status(private_http):
    h = private_http
    for ids, status in [(None, 422), ([], 422), (["own"] * 26, 422), (["other"], 404), (["own", "foreign"], 404)]:
        response = await request(h, "POST", "/api/churn/daemon/toggle", json={"enabled": True, "build_ids": ids})
        assert response.status_code == status, response.text
    assert not h.workers
    response = await request(h, "POST", "/api/churn/daemon/toggle", json={"enabled": True, "build_ids": ["own"]})
    assert response.status_code == 200 and response.json()["build_ids"] == ["own"]
    for account in ["other", "foreign", "admin"]:
        status = (await request(h, "GET", "/api/churn/daemon/status", account)).json()
        assert status["enabled"] is False and status["recent"] == [] and status["build_ids"] == []
        assert (await request(h, "POST", "/api/churn/daemon/toggle", account, json={"enabled": False})).status_code == 200
    assert (await request(h, "GET", "/api/churn/daemon/status")).json()["enabled"] is True
    # Run exactly one daemon iteration without waiting for the next interval.
    held = h.workers[-1]
    stop, daemon, principal = held.args
    original_wait = stop.wait
    stop.wait = lambda timeout: stop.set()  # type: ignore[method-assign]
    try:
        run_worker(h)
    finally:
        stop.wait = original_wait  # type: ignore[method-assign]
    assert daemon["scanned_builds"] == 1 and daemon["churned"] == 1
    assert all(row["build_id"] == "own" for row in h.db["galaxy_churn_runs"].rows if "ts" in row)


@pytest.mark.asyncio
async def test_cold_cache_uses_the_existing_canonical_build_metadata(private_http):
    h = private_http
    h.builds.pop("own")
    assert (await request(h, "GET", "/api/churn/own/analyze")).status_code == 200
    assert h.db["galaxy_builds"].queries[-1] == {
        "build_id": "own", "owner_id": h.users["owner"]["email"], "tenant_id": "tenant-a"}
    assert (await request(h, "GET", "/api/churn/own/analyze", "other")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", [churn, orch])
@pytest.mark.parametrize("revoke", [None, "before-transfer", "after-transfer"])
async def test_provider_work_has_confidential_galaxy_identity_and_revalidates(private_http, monkeypatch, engine, revoke):
    h = private_http
    from core import engine_chat

    transfers = []
    metadata = []

    class Chat:
        def __init__(self, **kwargs):
            metadata.append(kwargs)
            if revoke == "before-transfer":
                h.users["owner"]["disabled"] = True

        def with_model(self, provider, model):
            assert model == "test-galaxy-model"
            return self

        async def send_message(self, message):
            transfers.append(message.text)
            if revoke == "after-transfer":
                h.users["owner"]["disabled"] = True
            return '{"alts": [], "fields": {"title": "enriched-title"}, "brief": "enriched-brief"}'

    monkeypatch.setattr(engine_chat, "EngineChat", Chat)
    if engine is churn:
        kicked = await request(h, "POST", "/api/churn/own/run/async", json={"gid": "file", "model": "test-galaxy-model"})
    else:
        # Exercise the real deterministic generator, with its legacy optional
        # provider helper forbidden. Only EngineChat may receive this source.
        monkeypatch.setattr(text_gamefile, "_llm_enrich", lambda *args, **kwargs: pytest.fail("Legacy provider helper used"))
        planned = await request(h, "POST", "/api/orchestrator/own/plan", json={
            "steps": [{"kind": "forge", "target": "quest_from_text", "text": "Private owner-only quest source", "model": "test-galaxy-model"}]})
        assert planned.status_code == 200, planned.text
        kicked = await request(h, "POST", "/api/orchestrator/plan/" + planned.json()["plan_id"] + "/execute/async")
    jid = kicked.json()["job_id"]
    run_worker(h)
    assert metadata and metadata[0]["tenant_id"] == "tenant-a"
    assert metadata[0]["actor_id"] == h.users["owner"]["email"]
    assert metadata[0]["data_class"] == "confidential"
    assert len(transfers) == (0 if revoke == "before-transfer" else 1)
    assert engine._JOBS[jid]["status"] == ("error" if revoke else "done")
    if revoke:
        assert engine._JOBS[jid]["result"] is None
        assert not h.db["galaxy_churn_runs"].writes and not h.db["galaxy_text_gamefiles"].writes
    elif engine is orch:
        stored = h.db["galaxy_text_gamefiles"].writes[-1][1]
        from core import unbulk

        stored = unbulk.decompress_doc(stored, ["fields", "brief"])
        assert stored["llm_enriched"] is True and stored["fields"]["title"] == "enriched-title"


@pytest.mark.asyncio
async def test_orchestrator_job_cannot_follow_a_plan_rebound_to_another_owned_build(private_http):
    h = private_http
    kicked = await request(h, "POST", "/api/orchestrator/plan/plan-own/execute/async")
    jid = kicked.json()["job_id"]
    plan = next(row for row in h.db["galaxy_build_plans"].rows if row["_id"] == "plan-own")
    plan["build_id"] = "own-2"
    assert (await request(h, "GET", "/api/orchestrator/job/" + jid)).status_code == 404
    assert (await request(h, "POST", "/api/orchestrator/job/" + jid + "/cancel")).status_code == 404
    run_worker(h)
    assert orch._JOBS[jid]["status"] == "error" and not h.db["galaxy_build_plans"].writes


@pytest.mark.asyncio
async def test_daemon_revalidates_before_private_source_and_stops_after_revocation(private_http):
    h = private_http
    enabled = await request(h, "POST", "/api/churn/daemon/toggle", json={"enabled": True, "build_ids": ["own"]})
    assert enabled.status_code == 200
    h.users["owner"]["disabled"] = True
    run_worker(h)
    daemon = next(iter(churn._DAEMONS.values()))
    assert daemon["enabled"] is False and daemon["stop"].is_set()
    assert not h.db["galaxy_text_gamefiles"].queries and not h.db["galaxy_churn_runs"].writes

