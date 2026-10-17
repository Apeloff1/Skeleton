"""ProjectsClient tests for skeleton.projects.v1 (aligned to #4097 at 6524b7c35)."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from skeleton.client import (
    PROJECTS_BASE_PATH,
    CancelToken,
    GatewayClient,
    Project,
    ProjectBrief,
    ProjectBuild,
    ProjectBuildLink,
    ProjectsClient,
    RequestSealer,
    RetryPolicy,
    SkeletonCancelledError,
    SkeletonHTTPError,
    SkeletonSealConfigError,
    SkeletonSessionConfigError,
    SkeletonTimeoutError,
)
from skeleton.client import projects as projects_mod

PROJECT = {
    "schema_version": "1.0.0", "project_id": "p1", "actor_id": "u1", "tenant_id": "default",
    "brief": {"title": "Space game", "summary": "s", "genre": "arcade", "constraints": ["2D"]},
    "status": "active", "build_ids": ["b1", "b2"],
    "created_at": "2026-10-17T16:00:00Z", "updated_at": "2026-10-17T16:05:00Z", "future": 1,
}


def _build(status="queued", **kw):
    return {"schema_version": "1.0.0", "schema_id": "skeleton.projects.v1", "build_id": "b1",
            "execution_id": "b1", "project_id": "p1", "status": status, "target": "", "job_id": "j1",
            "result": {}, "error": "", "created_at": "2026-10-17T16:00:00Z",
            "updated_at": "2026-10-17T16:00:00Z", "replayed": False, **kw}


def _env(code, message="m", status=400):
    return httpx.Response(status, json={"error": {"type": "ProjectContractError", "code": code,
                                                  "message": message, "context": {}}})


def _client(handler, *, sleeps=None, token="sess-tok", base_path=None, seal=None):
    sleeps = sleeps if sleeps is not None else []
    gw = GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)),
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0),
        sleep=sleeps.append, seal=seal,
    )
    kw = {} if base_path is None else {"base_path": base_path}
    return ProjectsClient(gw, session_token=token, **kw)


def test_constants_and_base_path_override():
    assert PROJECTS_BASE_PATH == "/api/v1/projects"
    assert projects_mod.PROJECT_ERROR_STATUS == {
        "PROJECT.INVALID": 400, "PROJECT.UNAUTHENTICATED": 401, "PROJECT.NOT_FOUND": 404,
        "PROJECT.BUILD_CONFLICT": 409, "PROJECT.NAME_CONFLICT": 409, "PROJECT.UNAVAILABLE": 503}
    assert projects_mod.TERMINAL_BUILD_STATUSES == {"succeeded", "failed", "cancelled"}
    paths = []

    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(200, json={"schema_version": "1.0.0", "items": [], "next_cursor": None})

    _client(handler).list()
    _client(handler, base_path="/custom/projects/").list()
    assert paths == ["/api/v1/projects", "/custom/projects"]
    with pytest.raises(ValueError):
        _client(handler, base_path="api/x")


def test_models_parse_leniently():
    p = Project.from_dict(PROJECT)
    assert p.title == "Space game" and p.brief.constraints == ("2D",) and p.status == "active"
    assert p.build_ids == ("b1", "b2") and p.tenant_id == "default" and p.created_at.endswith("Z")
    b = ProjectBuild.from_dict(_build("succeeded", job_id=None, replayed=True))
    assert b.is_terminal and b.execution_id == "b1" and b.replayed and b.schema_id == "skeleton.projects.v1"
    assert ProjectBuild.from_dict({"build_id": "x"}).execution_id == "x"


def test_create_both_brief_forms_seal_bearer_and_no_scope_fields(monkeypatch):
    bodies, headers = [], []

    def handler(req):
        bodies.append(json.loads(req.content))
        headers.append(req.headers)
        return httpx.Response(201, json=PROJECT)

    pc = _client(handler, seal=RequestSealer("sdk", seal_secret="s"))
    assert pc.create("Space game\nshoot rocks").title == "Space game"
    pc.create(ProjectBrief(title="Space game", summary="s", genre="arcade", constraints=["2D"]))
    assert bodies[0] == {"schema_version": "1.0.0", "brief": "Space game\nshoot rocks"}
    assert bodies[1] == {"schema_version": "1.0.0", "brief": {
        "title": "Space game", "summary": "s", "genre": "arcade", "constraints": ["2D"]}}
    for body in bodies:
        assert set(body) == {"schema_version", "brief"}
    for h in headers:
        assert h["authorization"] == "Bearer sess-tok" and h["x-gf-seal"].startswith("sdk.")
        assert len(h.get_list("x-request-id")) == 1 and "idempotency-key" not in h


def test_create_rejects_name_and_settings_and_bad_briefs():
    pc = _client(lambda r: pytest.fail("no request expected"))
    with pytest.raises(ValueError, match="not part of skeleton.projects.v1"):
        pc.create("b", name="n")
    with pytest.raises(ValueError):
        pc.create("b", settings={})
    for bad in ("", "   ", "x" * 20001):
        with pytest.raises(ValueError):
            pc.create(bad)
    for bad in (
        {"title": ""}, {"title": "t" * 201}, {"title": "t", "summary": "s" * 8001},
        {"title": "t", "genre": "g" * 81}, {"title": "t", "constraints": ["c"] * 33},
        {"title": "t", "constraints": [""]},
    ):
        with pytest.raises(ValueError):
            ProjectBrief(**bad)
    with pytest.raises(TypeError):
        ProjectBrief(title="t", constraints="abc")
    with pytest.raises(ValueError):
        pc.create("b", idempotency_key="")
    with pytest.raises(ValueError):
        pc.create("b", idempotency_key="k" * 129)


def test_create_never_retried_without_key():
    hits, sleeps = [], []

    def handler(req):
        hits.append(1)
        return _env("PROJECT.UNAVAILABLE", status=503)

    with pytest.raises(SkeletonHTTPError) as info:
        _client(handler, sleeps=sleeps).create("brief")
    assert len(hits) == 1 and sleeps == [] and info.value.code == "PROJECT.UNAVAILABLE"


def test_create_with_idempotency_key_header_retries_and_accepts_200_replay():
    keys, sleeps = [], []

    def handler(req):
        keys.append(req.headers.get("idempotency-key"))
        return _env("PROJECT.UNAVAILABLE", status=503) if len(keys) == 1 else httpx.Response(200, json=PROJECT)

    p = _client(handler, sleeps=sleeps).create("brief", idempotency_key="create-1")
    assert p.project_id == "p1" and keys == ["create-1", "create-1"] and len(sleeps) == 1


def test_list_items_cursor_and_limit():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        nxt = None if "cursor" in req.url.params else "c2"
        return httpx.Response(200, json={"schema_version": "1.0.0", "items": [PROJECT], "next_cursor": nxt})

    pc = _client(handler)
    page = pc.list(limit=10)
    assert [p.project_id for p in page] == ["p1"] and page.next_cursor == "c2" and len(page) == 1
    assert pc.list(cursor="c2").next_cursor is None
    assert seen == [{"limit": "10"}, {"cursor": "c2"}]
    for bad in (0, 101, True):
        with pytest.raises(ValueError):
            pc.list(limit=bad)


def test_get_list_builds_get_build():
    def handler(req):
        p = req.url.path
        if p == "/api/v1/projects/p1":
            return httpx.Response(200, json=PROJECT)
        if p.endswith("/builds"):
            return httpx.Response(200, json={"schema_version": "1.0.0", "items": [_build(), _build("running")]})
        return httpx.Response(200, json=_build("running"))

    pc = _client(handler)
    assert pc.get("p1").status == "active"
    assert [b.status for b in pc.list_builds("p1")] == ["queued", "running"]
    assert pc.get_build("p1", "b1").status == "running"


def test_start_build_body_and_replay():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(202, json=_build(replayed=len(bodies) > 1))

    pc = _client(handler)
    b = pc.start_build("p1", target="web", options={"x": 1}, idempotency_key="k1")
    assert b.execution_id == "b1" and b.build_id == "b1" and b.status == "queued" and not b.replayed
    assert pc.start_build("p1", idempotency_key="k1").replayed
    assert bodies[0] == {"schema_version": "1.0.0", "idempotency_key": "k1", "target": "web", "options": {"x": 1}}
    for body in bodies:
        assert not set(body) & {"execution_id", "actor_id", "tenant_id"}
    with pytest.raises(ValueError):
        pc.start_build("p1", target="t" * 65)
    with pytest.raises(ValueError):
        pc.start_build("p1", idempotency_key="k" * 129)
    with pytest.raises(TypeError):
        pc.start_build("p1", execution_id="e1")  # linking is a separate call


def test_link_execution_returns_distinct_type_and_never_mixes_fields():
    bodies, statuses = [], iter([201, 200])

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        code = next(statuses)
        return httpx.Response(code, json={"schema_version": "1.0.0", "project_id": "p1",
                                          "execution_id": body["execution_id"],
                                          "linked_at": "2026-10-17T16:00:00Z", "replayed": code == 200})

    pc = _client(handler)
    link = pc.link_execution("p1", "exec-1")
    assert isinstance(link, ProjectBuildLink) and not isinstance(link, ProjectBuild)
    assert link.execution_id == "exec-1" and link.linked_at.endswith("Z") and not link.replayed
    assert pc.link_execution("p1", "exec-1").replayed
    assert bodies[0] == {"schema_version": "1.0.0", "execution_id": "exec-1"}
    with pytest.raises(ValueError):
        pc.link_execution("p1", "")


def test_missing_token_and_redacted_repr(monkeypatch):
    monkeypatch.delenv("SKELETON_SESSION_TOKEN", raising=False)
    gw = GatewayClient("http://test")
    with pytest.raises(SkeletonSessionConfigError):
        ProjectsClient(gw)
    monkeypatch.setenv("SKELETON_SESSION_TOKEN", "env-secret")
    assert "env-secret" not in repr(ProjectsClient(gw))


@pytest.mark.parametrize("code,status", sorted(projects_mod.PROJECT_ERROR_STATUS.items()))
def test_v1_error_envelope_codes(code, status):
    pc = _client(lambda r: httpx.Response(status, json={"error": {
        "type": "ProjectContractError", "code": code, "message": "nope", "context": {"k": 1}}}))
    with pytest.raises(SkeletonHTTPError) as info:
        pc.get("p1")
    assert info.value.status_code == status and info.value.code == code
    assert info.value.message == "nope" and info.value.context == {"k": 1}


def test_gate_string_error_form_parsed():
    pc = _client(lambda r: httpx.Response(401, json={"error": "invalid_seal"}))
    with pytest.raises(SkeletonHTTPError) as info:
        pc.get("p1")  # no seal configured, so no re-mint; string code still parsed
    assert info.value.code == "invalid_seal"


def test_invalid_seal_reminted_once_then_succeeds_or_raises():
    seals = []

    def ok_after_one(req):
        seals.append(req.headers["x-gf-seal"])
        return httpx.Response(401, json={"error": "invalid_seal"}) if len(seals) == 1 else httpx.Response(200, json=PROJECT)

    now = [1000.0]

    def clock():
        now[0] += 1
        return now[0]

    pc = _client(ok_after_one, seal=RequestSealer("sdk", seal_secret="s", clock=clock))
    assert pc.get("p1").project_id == "p1" and len(seals) == 2 and seals[0] != seals[1]

    hits = []

    def always(req):
        hits.append(1)
        return httpx.Response(401, json={"error": "invalid_seal"})

    with pytest.raises(SkeletonHTTPError) as info:
        _client(always, seal=RequestSealer("sdk", seal_secret="s")).create("b")
    assert len(hits) == 2 and info.value.code == "invalid_seal"


def test_seal_unavailable_never_retried_even_for_retryable_calls():
    hits, sleeps = [], []

    def handler(req):
        hits.append(1)
        return httpx.Response(503, json={"error": "seal_unavailable"})

    with pytest.raises(SkeletonSealConfigError):
        _client(handler, sleeps=sleeps).start_build("p1")
    assert len(hits) == 1 and sleeps == []


def test_start_build_retry_reuses_generated_idempotency_key():
    keys, sleeps = [], []

    def handler(req):
        keys.append(json.loads(req.content)["idempotency_key"])
        return httpx.Response(503 if len(keys) < 3 else 202, json=_build())

    b = _client(handler, sleeps=sleeps).start_build("p1")
    assert b.build_id == "b1" and len(keys) == 3 and len(set(keys)) == 1
    assert re.fullmatch(r"[0-9a-f]{32}", keys[0]) and len(sleeps) == 2


def test_wait_build_terminal_cancel_timeout():
    statuses = iter(["pending", "queued", "running", "failed"])
    naps: list[float] = []
    pc = _client(lambda r: httpx.Response(200, json=_build(next(statuses))))
    assert pc.wait_build("p1", "b1", poll_seconds=0.2, sleep=naps.append).status == "failed"
    assert naps == [0.2, 0.2, 0.2]

    tok = CancelToken()
    pc2 = _client(lambda r: httpx.Response(200, json=_build("running")))
    with pytest.raises(SkeletonCancelledError):
        pc2.wait_build("p1", "b1", cancel=tok, sleep=lambda s: tok.cancel())

    t = [0.0]
    with pytest.raises(SkeletonTimeoutError):
        pc2.wait_build("p1", "b1", timeout_seconds=1.0, poll_seconds=0.5,
                       sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])


def test_wait_build_default_timeout_and_validation():
    import inspect

    pc = _client(lambda r: httpx.Response(200, json=_build("running")))
    assert inspect.signature(pc.wait_build).parameters["timeout_seconds"].default == 600.0
    for bad in (None, 0, -5):
        with pytest.raises(ValueError):
            pc.wait_build("p1", "b1", timeout_seconds=bad)
    t = [0.0]
    with pytest.raises(SkeletonTimeoutError):
        pc.wait_build("p1", "b1", poll_seconds=100,
                      sleep=lambda s: t.__setitem__(0, t[0] + s), clock=lambda: t[0])
    assert t[0] >= 600


def test_projects_routes_exist_in_backend_router():
    """Conformance against #4097's real router (skips until it is on this branch)."""
    try:
        from skeleton.api.projects_routes import build_router
    except ImportError:
        pytest.skip("#4097 (skeleton.api.projects_routes) is not on this branch yet")
    router = build_router()
    backend = {
        (m, re.sub(r"\{[^}]+\}", "{}", "/api/v1" + r.path))  # mounted with prefix /api/v1
        for r in router.routes for m in (getattr(r, "methods", None) or ())
    }
    for method, path in projects_mod.SDK_ROUTES:
        assert (method, re.sub(r"\{[^}]+\}", "{}", path)) in backend, f"{method} {path}"
