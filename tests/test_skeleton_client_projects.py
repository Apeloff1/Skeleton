"""ProjectsClient tests: one contract, skeleton.projects.v1 (TD ruling).

The v1 base path is /api/v1/projects. #4097 currently serves /api/app/projects,
which is reachable through ``base_path=``.
"""

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
    ProjectsClient,
    RetryPolicy,
    SkeletonCancelledError,
    SkeletonHTTPError,
    SkeletonSessionConfigError,
    SkeletonTimeoutError,
)
from skeleton.client import projects as projects_mod

LEGACY_PROJECT = {
    "project_id": "p1", "owner_id": "u1", "name": "Game", "brief": "make a game",
    "settings": {"a": 1}, "created_at": 1.5, "updated_at": 2.5, "extra": "ignored",
}
V1_PROJECT = {
    "schema_version": "1.0.0", "project_id": "p2", "actor_id": "u1", "tenant_id": "t1",
    "brief": {"title": "Space game", "summary": "s", "genre": "arcade", "constraints": ["2D"]},
    "status": "active", "build_ids": ["e1", "e2"],
    "created_at": "2026-10-17T16:00:00Z", "updated_at": "2026-10-17T16:05:00Z",
}


def _build(status="queued", **kw):
    return {"build_id": "b1", "project_id": "p1", "status": status, "target": "", "job_id": "j1",
            "result": {}, "error": "", "created_at": 1.0, "updated_at": 1.0, "future_field": 1, **kw}


def _client(handler, *, sleeps=None, token="sess-tok", base_path=None):
    sleeps = sleeps if sleeps is not None else []
    gw = GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)),
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0),
        sleep=sleeps.append,
    )
    kw = {} if base_path is None else {"base_path": base_path}
    return ProjectsClient(gw, session_token=token, **kw)


def test_base_path_constant_and_override():
    assert PROJECTS_BASE_PATH == "/api/v1/projects"
    paths = []

    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(200, json={"projects": []})

    _client(handler).list()
    _client(handler, base_path="/api/app/projects/").list()
    assert paths == ["/api/v1/projects", "/api/app/projects"]
    with pytest.raises(ValueError):
        _client(handler, base_path="api/x")


def test_parsing_tolerates_legacy_and_v1_shapes():
    legacy = Project.from_dict(LEGACY_PROJECT)
    assert legacy.brief == "make a game" and legacy.owner_id == "u1" and legacy.status is None
    v1 = Project.from_dict(V1_PROJECT)
    assert isinstance(v1.brief, ProjectBrief) and v1.brief.constraints == ("2D",)
    assert v1.status == "active" and v1.build_ids == ("e1", "e2") and v1.name == "Space game"
    assert v1.actor_id == "u1" and v1.tenant_id == "t1" and v1.created_at.endswith("Z")
    b = ProjectBuild.from_dict(_build("succeeded", job_id=None, execution_id="e9"))
    assert b.is_terminal and b.job_id is None and b.execution_id == "e9"


def test_create_text_and_structured_brief_bodies_have_no_actor_or_tenant():
    bodies = []
    headers = []

    def handler(req):
        bodies.append(json.loads(req.content))
        headers.append(req.headers)
        return httpx.Response(201, json=V1_PROJECT if len(bodies) > 1 else LEGACY_PROJECT)

    pc = _client(handler)
    assert pc.create("make a game", name="Game", settings={"a": 1}).name == "Game"
    brief = ProjectBrief(title="Space game", summary="s", genre="arcade", constraints=["2D"])
    assert pc.create(brief).status == "active"
    assert bodies[0] == {"schema_version": "1.0.0", "brief": "make a game", "name": "Game", "settings": {"a": 1}}
    assert bodies[1] == {"schema_version": "1.0.0", "brief": {
        "title": "Space game", "summary": "s", "genre": "arcade", "constraints": ["2D"]}}
    for body in bodies:
        assert "actor_id" not in body and "tenant_id" not in body
    for h in headers:
        assert h["authorization"] == "Bearer sess-tok" and len(h.get_list("x-request-id")) == 1


def test_brief_validation():
    pc = _client(lambda r: pytest.fail("no request expected"))
    with pytest.raises(ValueError):
        pc.create("")
    with pytest.raises(ValueError):
        pc.create("x" * 20001)
    with pytest.raises(ValueError):
        pc.create("ok", name="n" * 201)
    for bad in (
        dict(title=""), dict(title="t" * 201), dict(title="t", summary="s" * 8001),
        dict(title="t", genre="g" * 81), dict(title="t", constraints=["c"] * 33),
        dict(title="t", constraints=[""]), dict(title="t", constraints="abc"),
    ):
        with pytest.raises(ValueError):
            ProjectBrief(**bad)
    with pytest.raises(ValueError):
        pc.start_build("p1", target="t" * 65)
    with pytest.raises(ValueError):
        pc.start_build("p1", idempotency_key="k" * 129)


def test_list_both_shapes_and_cursor():
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        if "cursor" in req.url.params:
            return httpx.Response(200, json={"schema_version": "1.0.0", "items": [V1_PROJECT], "next_cursor": None})
        if "limit" in req.url.params:
            return httpx.Response(200, json={"schema_version": "1.0.0", "items": [V1_PROJECT], "next_cursor": "c2"})
        return httpx.Response(200, json={"projects": [LEGACY_PROJECT]})

    pc = _client(handler)
    legacy = pc.list()
    assert [p.project_id for p in legacy] == ["p1"] and legacy.next_cursor is None
    page = pc.list(limit=10)
    assert [p.project_id for p in page.items] == ["p2"] and page.next_cursor == "c2" and len(page) == 1
    assert pc.list(cursor="c2").next_cursor is None
    assert seen[1] == {"limit": "10"} and seen[2] == {"cursor": "c2"}
    with pytest.raises(ValueError):
        pc.list(limit=101)


def test_get_list_builds_get_build():
    def handler(req):
        p = req.url.path
        if p == "/api/v1/projects/p1":
            return httpx.Response(200, json=LEGACY_PROJECT)
        if p.endswith("/builds"):
            return httpx.Response(200, json={"builds": [_build(), _build("running")]})
        return httpx.Response(200, json=_build("running"))

    pc = _client(handler)
    assert pc.get("p1").owner_id == "u1"
    assert len(pc.list_builds("p1")) == 2
    assert pc.get_build("p1", "b1").status == "running"


def test_start_build_returns_execution_id_and_link_execution():
    bodies = []
    headers = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        headers.append(req.headers)
        if "execution_id" in body:
            return httpx.Response(200, json={"schema_version": "1.0.0", "project_id": "p1",
                                             "execution_id": body["execution_id"],
                                             "linked_at": "2026-10-17T16:00:00Z", "replayed": False})
        return httpx.Response(202, json=_build(execution_id="e-new"))

    pc = _client(handler)
    b = pc.start_build("p1", target="web", options={"x": 1}, idempotency_key="k1")
    assert b.execution_id == "e-new" and b.build_id == "b1" and b.status == "queued"
    assert bodies[0] == {"schema_version": "1.0.0", "idempotency_key": "k1", "target": "web", "options": {"x": 1}}
    assert headers[0]["idempotency-key"] == "k1"
    link = pc.link_execution("p1", "e-old")
    assert link.execution_id == "e-old" and link.replayed is False and link.build_id is None
    assert bodies[1]["execution_id"] == "e-old" and bodies[1]["schema_version"] == "1.0.0"
    for body in bodies:
        assert "actor_id" not in body and "tenant_id" not in body
    with pytest.raises(ValueError):
        pc.link_execution("p1", "")


def test_missing_token_and_redacted_repr(monkeypatch):
    monkeypatch.delenv("SKELETON_SESSION_TOKEN", raising=False)
    gw = GatewayClient("http://test")
    with pytest.raises(SkeletonSessionConfigError):
        ProjectsClient(gw)
    monkeypatch.setenv("SKELETON_SESSION_TOKEN", "env-secret")
    assert "env-secret" not in repr(ProjectsClient(gw))


def test_v1_error_envelope_and_legacy_detail_fallback():
    def handler(req):
        if req.method == "POST":
            return httpx.Response(409, json={"error": {"type": "ProjectContractError", "code": "PROJECT.BUILD_CONFLICT",
                                                       "message": "build already linked", "context": {"k": 1}}})
        if "/builds/" in req.url.path:
            return httpx.Response(404, json={"detail": "build_not_found"})
        if req.url.path == "/api/v1/projects":
            return httpx.Response(401, json={"detail": "invalid_session"})
        return httpx.Response(404, json={"error": {"type": "ProjectContractError", "code": "PROJECT.NOT_FOUND",
                                                   "message": "project not found"}})

    pc = _client(handler)
    with pytest.raises(SkeletonHTTPError) as info:
        pc.start_build("p1")
    assert info.value.code == "PROJECT.BUILD_CONFLICT" and info.value.message == "build already linked"
    assert info.value.context == {"k": 1}
    with pytest.raises(SkeletonHTTPError) as info:
        pc.get("nope")
    assert info.value.code == "PROJECT.NOT_FOUND" and info.value.message == "project not found"
    for call, code in [(lambda: pc.get_build("p1", "x"), "build_not_found"), (lambda: pc.list(), "invalid_session")]:
        with pytest.raises(SkeletonHTTPError) as info:
            call()
        assert info.value.code == code


def test_create_not_retried():
    hits = []
    sleeps: list[float] = []

    def handler(req):
        hits.append(1)
        return httpx.Response(503, json={"detail": "busy"})

    with pytest.raises(SkeletonHTTPError):
        _client(handler, sleeps=sleeps).create("brief")
    assert len(hits) == 1 and sleeps == []


def test_start_build_retry_reuses_generated_idempotency_key():
    keys = []
    sleeps: list[float] = []

    def handler(req):
        keys.append((json.loads(req.content)["idempotency_key"], req.headers["idempotency-key"]))
        return httpx.Response(503 if len(keys) < 3 else 202, json=_build())

    b = _client(handler, sleeps=sleeps).start_build("p1")
    assert b.build_id == "b1" and len(keys) == 3 and len(set(keys)) == 1
    assert keys[0][0] == keys[0][1] and re.fullmatch(r"[0-9a-f]{32}", keys[0][0]) and len(sleeps) == 2


def test_wait_build_terminal_cancel_timeout():
    statuses = iter(["queued", "running", "succeeded"])
    naps: list[float] = []
    pc = _client(lambda r: httpx.Response(200, json=_build(next(statuses))))
    assert pc.wait_build("p1", "b1", poll_seconds=0.2, sleep=naps.append).status == "succeeded"
    assert naps == [0.2, 0.2]

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
    try:
        from skeleton.app_services.projects_api import PREFIX, build_router
    except ImportError:
        pytest.skip("#4097 (skeleton.app_services.projects_api) is not on this branch yet")
    if PREFIX != PROJECTS_BASE_PATH:
        pytest.skip(f"#4097 router is still at {PREFIX}; waiting for IS to move it to {PROJECTS_BASE_PATH}")
    router = build_router(services=lambda: None)
    backend = {
        (m, re.sub(r"\{[^}]+\}", "{}", r.path))
        for r in router.routes for m in (getattr(r, "methods", None) or ())
    }
    for method, path in projects_mod.SDK_ROUTES:
        assert (method, re.sub(r"\{[^}]+\}", "{}", path)) in backend, f"{method} {path}"
