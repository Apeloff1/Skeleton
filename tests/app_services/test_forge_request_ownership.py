"""Forge HTTP retries and durable build receipts retain exact charter ownership."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace

import pytest

from skeleton.api import routes
from skeleton.api.hmac_seal import mint_seal
from skeleton.api.idempotency import IdempotencyConflict, IdempotencyGuard
from skeleton.app_services import job_api
from skeleton.app_services.job_api import IdempotencyMismatch, JobService
from skeleton.forge import game_build_queue
from skeleton.persistence.app_foundation.db import Database


def _headers(actor="test-sdk", tenant="studio", key=None):
    headers = {"x-gf-seal": mint_seal(actor), "x-skeleton-tenant": tenant}
    if key:
        headers["Idempotency-Key"] = key
    return headers


@pytest.fixture
def builds(gated_client, monkeypatch):
    monkeypatch.setattr(game_build_queue, "start_worker", lambda **kwargs: None)
    monkeypatch.setattr(routes, "_idempotency", IdempotencyGuard())
    return gated_client


def _submit(world, *, actor="test-sdk", tenant="studio", key="build-key", **body):
    return world.client.post("/api/v1/game/build", headers=_headers(actor, tenant, key),
                             json={"brief": "A small platformer", **body})


def test_advertised_build_route_has_shared_gate_and_exact_persisted_owner(builds):
    client, svc = builds.client, builds.services.jobs
    assert client.app.state.gate_policy.required_domain("/api/v1/game/build") == "forge"
    assert client.app.state.gate_policy.required_domain("/api/v1/game/build/x") == "forge"
    assert client.app.state.gate_policy.required_domain("/api/v1/game/build-extra") is None
    assert client.post("/api/v1/game/build", json={"brief": "private"}).status_code == 401
    accepted = _submit(builds)
    assert accepted.status_code == 202, accepted.text
    ack = accepted.json()
    identity = job_api.get_identity(ack["job_id"])
    assert (identity.actor_id, identity.tenant_id, identity.execution_id, identity.kind) == (
        "test-sdk", "studio", ack["execution_id"], "game.build")
    svc.register_handler("game.build", lambda ctx, body: {"private": "owner-only", "actor": ctx.actor_id,
                                                        "tenant": ctx.tenant_id})
    svc.run_once("controlled-worker")
    status = client.get(ack["status_ref"], headers=_headers())
    assert status.status_code == 200, status.text
    assert status.json()["result"] == {"private": "owner-only", "actor": "test-sdk", "tenant": "studio"}
    for headers in ({}, _headers("other-sdk"), _headers(tenant="elsewhere")):
        denied = client.get(ack["status_ref"], headers=headers)
        assert denied.status_code in (401, 404), denied.text
        assert "owner-only" not in denied.text
    # Query/body identities cannot replace the authenticated request scope.
    denied = client.get(ack["status_ref"] + "?actor_id=test-sdk&tenant_id=studio",
                        headers=_headers("other-sdk", "elsewhere"))
    assert denied.status_code == 404


def test_build_idempotency_is_scoped_and_preserves_exact_body_conflicts(builds):
    first = _submit(builds).json()
    replay = _submit(builds)
    assert replay.status_code == 202 and replay.json()["job_id"] == first["job_id"]
    assert replay.json()["replayed"] is True
    assert _submit(builds, brief="A different game").status_code == 409
    assert _submit(builds, deadline_s=10).status_code == 409
    assert _submit(builds, playtest="off").status_code == 409
    assert _submit(builds, unknown_ignored_field=True).status_code == 409
    for actor, tenant in (("other-sdk", "studio"), ("test-sdk", "elsewhere")):
        fresh = _submit(builds, actor=actor, tenant=tenant)
        assert fresh.status_code == 202 and fresh.json()["job_id"] != first["job_id"]
        assert not fresh.json()["replayed"]


@pytest.mark.parametrize("body", [{"actor_id": "other-sdk"}, {"tenant_id": "elsewhere"}])
def test_build_rejects_body_scope_override(builds, body):
    assert _submit(builds, **body).status_code == 422
    assert builds.services.db.query("SELECT COUNT(*) FROM jobs")[0][0] == 0


@pytest.mark.parametrize("tenant", ["", "bad tenant", "bad/tenant"])
def test_build_does_not_collapse_invalid_tenant_to_default(builds, tenant):
    assert _submit(builds, tenant=tenant).status_code == 422
    assert builds.services.db.query("SELECT COUNT(*) FROM jobs")[0][0] == 0


def test_unowned_or_wrong_kind_durable_rows_fail_closed_before_result_read(builds, monkeypatch):
    svc = builds.services.jobs
    legacy = svc.queue.enqueue("game.build", {"legacy": True})
    with svc.db.tx() as conn:
        conn.execute("UPDATE jobs SET execution_id=?,status='succeeded',result=? WHERE job_id=?",
                     (legacy.job_id, '{"private":"legacy-secret"}', legacy.job_id))
    other = svc.enqueue("other.kind", {}, actor_id="test-sdk", tenant_id="studio")
    monkeypatch.setattr(game_build_queue, "get_result", lambda job: pytest.fail("read before ownership"))
    for execution in (legacy.job_id, other.execution_id, "missing"):
        denied = builds.client.get(f"/api/v1/game/build/{execution}", headers=_headers())
        assert denied.status_code == 404 and "legacy-secret" not in denied.text


def test_owned_status_survives_database_and_service_restart(builds, tmp_path):
    path = tmp_path / "reopened.sqlite3"
    first_db = Database(path)
    first_db.migrate()
    first_service = JobService(first_db)
    job_api.set_job_service(first_service)
    accepted = _submit(builds).json()
    first_service.register_handler("game.build", lambda ctx, body: {"private": "durable-receipt"})
    first_service.run_once("before-restart")
    first_db.close()
    reopened = Database(path)
    reopened.migrate()
    job_api.set_job_service(JobService(reopened))
    try:
        assert builds.client.get(accepted["status_ref"], headers=_headers()).json()["result"] == {
            "private": "durable-receipt"}
        for actor, tenant in (("other-sdk", "studio"), ("test-sdk", "other")):
            result = builds.client.get(accepted["status_ref"], headers=_headers(actor, tenant))
            assert result.status_code == 404 and "durable-receipt" not in result.text
    finally:
        job_api.set_job_service(builds.services.jobs)
        reopened.close()


def test_owned_queue_publishes_metadata_before_claim_and_fences_changed_body(builds, monkeypatch):
    svc = builds.services.jobs
    original = svc.queue.enqueue_owned
    observed = []

    def observing(*args, **kwargs):
        job, replayed = original(*args, **kwargs)
        claimed = svc.queue.claim("immediate-worker", kinds=["game.build"])
        observed.append((claimed.job_id, svc.get_identity(claimed.job_id)))
        return job, replayed

    monkeypatch.setattr(svc.queue, "enqueue_owned", observing)
    response = _submit(builds)
    assert response.status_code == 202
    assert observed[0][0] == response.json()["job_id"]
    assert (observed[0][1].actor_id, observed[0][1].tenant_id) == ("test-sdk", "studio")
    assert _submit(builds, brief="changed").status_code == 409
    assert svc.get_identity(response.json()["job_id"]) == observed[0][1]


def test_owned_queue_concurrent_conflict_cannot_overwrite_binding(builds):
    svc = builds.services.jobs
    barrier = Barrier(2)

    def submit(value):
        barrier.wait(timeout=5)
        try:
            return svc.enqueue("game.build", {"value": value}, actor_id="owner", tenant_id="tenant",
                               idempotency_key="concurrent")
        except IdempotencyMismatch:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, [1, 2]))
    assert sum(item is not None for item in outcomes) == 1
    rows = svc.db.query("SELECT * FROM jobs")
    assert len(rows) == 1
    assert rows[0]["request_hash"] and rows[0]["actor_id"] == "owner" and rows[0]["tenant_id"] == "tenant"


def test_queue_scope_encoding_has_no_colon_collision_and_legacy_requires_binding(builds):
    svc = builds.services.jobs
    first = svc.enqueue("game.build", {}, actor_id="b:c", tenant_id="a", idempotency_key="key")
    second = svc.enqueue("game.build", {}, actor_id="c", tenant_id="a:b", idempotency_key="key")
    assert first.job_id != second.job_id
    legacy = svc.queue.enqueue("game.build", {}, idempotency_key="studio:test-sdk:game.build:old")
    with pytest.raises(IdempotencyMismatch):
        svc.enqueue("game.build", {}, actor_id="test-sdk", tenant_id="studio", idempotency_key="old")
    assert not svc.get_identity(legacy.job_id).actor_id


def test_legacy_owned_replay_requires_exact_identity_and_recorded_body(builds):
    svc = builds.services.jobs
    body = {"brief": "private"}
    legacy_key = "studio:test-sdk:game.build:old"
    legacy = svc.queue.enqueue("game.build", body, idempotency_key=legacy_key)
    with svc.db.tx() as conn:
        conn.execute("UPDATE jobs SET actor_id=?,tenant_id=?,execution_id=?,request_hash=? WHERE job_id=?",
                     ("test-sdk", "studio", legacy.job_id, job_api.request_hash("game.build", body), legacy.job_id))
    replay = svc.enqueue("game.build", body, actor_id="test-sdk", tenant_id="studio", idempotency_key="old")
    assert replay.job_id == legacy.job_id and replay.replayed
    with pytest.raises(IdempotencyMismatch):
        svc.enqueue("game.build", {"brief": "changed"}, actor_id="test-sdk", tenant_id="studio",
                    idempotency_key="old")


def test_build_project_link_requires_same_attested_actor_and_tenant(builds):
    from skeleton.contracts.projects import ProjectBrief
    from skeleton.persistence.app_foundation.projects_v1 import ProjectsV1Store

    actor = builds.user.user_id
    project, _ = ProjectsV1Store(builds.services.db).create(actor, "studio", ProjectBrief(title="Owned project"))
    for other_actor, tenant in (("other-sdk", "studio"), (actor, "elsewhere")):
        denied = _submit(builds, actor=other_actor, tenant=tenant, project_id=project.project_id)
        assert denied.status_code == 422
    assert builds.services.db.query("SELECT COUNT(*) FROM builds")[0][0] == 0
    accepted = _submit(builds, actor=actor, project_id=project.project_id)
    assert accepted.status_code == 202, accepted.text
    replay = _submit(builds, actor=actor, project_id=project.project_id)
    assert replay.status_code == 202 and replay.json()["replayed"]
    assert replay.json()["execution_id"] == accepted.json()["execution_id"]
    assert builds.services.db.query("SELECT COUNT(*) FROM builds")[0][0] == 1


def test_concurrent_project_retries_publish_one_build_and_fast_worker_stays_terminal(builds, monkeypatch):
    from skeleton.contracts.projects import ProjectBrief
    from skeleton.persistence.app_foundation.projects_v1 import ProjectsV1Store

    svc = builds.services.jobs
    actor = builds.user.user_id
    project, _ = ProjectsV1Store(svc.db).create(actor, "studio", ProjectBrief(title="Concurrent project"))
    barrier = Barrier(2)
    original_prepare = svc.queue.enqueue_owned

    def simultaneous(*args, **kwargs):
        barrier.wait(timeout=5)
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(svc.queue, "enqueue_owned", simultaneous)
    def submit(_):
        return svc.enqueue("game.build", {}, actor_id=actor, tenant_id="studio",
                           project_id=project.project_id, idempotency_key="project-race")
    with ThreadPoolExecutor(max_workers=2) as pool:
        handles = list(pool.map(submit, range(2)))
    assert handles[0].job_id == handles[1].job_id
    assert sum(handle.replayed for handle in handles) == 1
    assert svc.db.query("SELECT COUNT(*) FROM jobs")[0][0] == 1
    assert svc.db.query("SELECT COUNT(*) FROM builds")[0][0] == 1

    svc.register_handler("game.build", lambda ctx, payload: {"ok": True})
    svc.run_once("finish-race-job")
    def immediate_worker(*args, **kwargs):
        job, replayed = original_prepare(*args, **kwargs)
        svc.run_once("finish-before-enqueue-returns")
        return job, replayed
    monkeypatch.setattr(svc.queue, "enqueue_owned", immediate_worker)
    fast = svc.enqueue("game.build", {}, actor_id=actor, tenant_id="studio",
                       project_id=project.project_id, idempotency_key="fast-project")
    assert svc.get_status(fast.job_id).status == "succeeded"
    build = svc.builds.get_build(fast.execution_id)
    assert build.status == "succeeded" and build.job_id == fast.job_id


@pytest.fixture
def forge_work(builds, monkeypatch):
    calls = []

    def materialise(self, blueprint, **kwargs):
        calls.append(("materialise", blueprint.blueprint_id))
        return {"receipt": len(calls)}

    from skeleton.forge.universal import Forge
    monkeypatch.setattr(Forge, "materialise", materialise)
    # The existing route dependency delegates to this composition hook.
    monkeypatch.setattr(routes, "get_state", lambda: SimpleNamespace(forge=Forge()))

    def adapter(body, state):
        calls.append(("adapter", dict(body)))
        return {"receipt": len(calls)}

    monkeypatch.setattr(routes, "run_gameforge_adapter", adapter)
    yield builds, calls


@pytest.mark.parametrize("path,body", [
    ("/forge/materialise", {"name": "private"}),
    ("/forge/archetype", {"name": "extraction"}),
    ("/gameforge/run", {"vision": "private"}),
    ("/gameforge/intake", {"answers": {}}),
])
def test_every_compatibility_handler_scopes_replay_and_body_conflict(forge_work, path, body):
    world, calls = forge_work
    def post(data, actor="test-sdk", tenant="studio"):
        return world.client.post("/api/v1" + path, headers=_headers(actor, tenant, "shared"), json=data)
    first = post(body)
    assert first.status_code == 200, first.text
    assert post(body).json() == first.json() and len(calls) == 1
    anonymous = world.client.post("/api/v1" + path, headers={"Idempotency-Key": "shared"}, json=body)
    assert anonymous.status_code == 401 and len(calls) == 1
    ambiguous = world.client.post("/api/v1" + path,
                                  headers={**_headers(key="shared"), "X-Idempotency-Key": "other"},
                                  json=body)
    assert ambiguous.status_code == 422 and len(calls) == 1
    changed = post({**body, "include_files": True})
    assert changed.status_code == 409 and len(calls) == 1
    for actor, tenant in (("other-sdk", "studio"), ("test-sdk", "elsewhere")):
        fresh = post(body, actor, tenant)
        assert fresh.status_code == 200, fresh.text
        original_receipt = first.json().get("artefact", first.json())["receipt"]
        fresh_receipt = fresh.json().get("artefact", fresh.json())["receipt"]
        assert fresh_receipt != original_receipt
    assert len(calls) == 3


def test_compatibility_cache_separates_routes_and_rejects_unscoped_legacy_entry(forge_work):
    world, calls = forge_work
    headers = _headers(key="shared")
    first = world.client.post("/api/v1/gameforge/run", headers=headers, json={"vision": "private"})
    second = world.client.post("/api/v1/forge/materialise", headers=headers, json={"name": "private"})
    assert first.status_code == second.status_code == 200
    assert first.json()["receipt"] != second.json()["artefact"]["receipt"]
    routes._idempotency.remember({"Idempotency-Key": "legacy"}, {"private": "unowned-response"})
    result = world.client.post("/api/v1/gameforge/run", headers=_headers(key="legacy"), json={"vision": "x"})
    assert result.status_code == 409 and "unowned-response" not in result.text and len(calls) == 2


def test_guard_fences_concurrent_retry_and_releases_failed_attempt():
    guard = IdempotencyGuard()
    headers, scope, body = {"Idempotency-Key": "key"}, ("actor", "tenant", "POST", "/route"), {"x": 1}
    entered, finish = Event(), Event()

    def first():
        with guard.operation(headers, scope=scope, body=body):
            entered.set()
            assert finish.wait(5)
            guard.complete(headers, {"private": "receipt"}, scope=scope, body=body)

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(first)
        assert entered.wait(5)
        try:
            for request in (body, {"x": 2}):
                with pytest.raises(IdempotencyConflict):
                    with guard.operation(headers, scope=scope, body=request):
                        pytest.fail("concurrent operation admitted")
        finally:
            finish.set()
        running.result(timeout=5)
    with guard.operation(headers, scope=scope, body=body) as replay:
        assert replay == {"private": "receipt"}
        replay["private"] = "mutated-copy"
    with guard.operation(headers, scope=("actor", "tenant", "PUT", "/route"), body=body) as replay:
        assert replay is None
    with guard.operation(headers, scope=scope, body=body) as replay:
        assert replay == {"private": "receipt"}
    failed = {"Idempotency-Key": "failed"}
    with pytest.raises(RuntimeError):
        with guard.operation(failed, scope=scope, body=body):
            raise RuntimeError("operation failed")
    with guard.operation(failed, scope=scope, body={"x": 2}) as replay:
        assert replay is None


def test_optional_fallback_preserves_scope_and_denies_unprovable_project_owner(monkeypatch):
    fallback = game_build_queue._FallbackQueue()
    monkeypatch.setattr(game_build_queue, "_real_api", lambda: None)
    monkeypatch.setattr(game_build_queue, "_fallback", fallback)
    first = fallback.enqueue("game.build", {}, actor_id="owner", tenant_id="tenant", idempotency_key="key")
    assert fallback.enqueue("game.build", {}, actor_id="owner", tenant_id="tenant",
                            idempotency_key="key").replayed
    with pytest.raises(game_build_queue.IdempotencyMismatch):
        fallback.enqueue("game.build", {"different": True}, actor_id="owner", tenant_id="tenant",
                         idempotency_key="key")
    assert game_build_queue.execution_view(first.execution_id, actor_id="owner", tenant_id="tenant")["job_id"] == first.job_id
    for actor, tenant in (("other", "tenant"), ("owner", "other")):
        with pytest.raises(KeyError):
            game_build_queue.execution_view(first.execution_id, actor_id=actor, tenant_id=tenant)
    with pytest.raises(ValueError, match="durable queue owner"):
        fallback.enqueue("game.build", {}, actor_id="owner", tenant_id="tenant", project_id="unowned-project")
