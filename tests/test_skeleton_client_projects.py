"""ProjectsClient tests (contract: PR #4097, /api/app/projects)."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from skeleton.client import (
    CancelToken,
    GatewayClient,
    Project,
    ProjectBuild,
    ProjectsClient,
    RetryPolicy,
    SkeletonCancelledError,
    SkeletonHTTPError,
    SkeletonSessionConfigError,
    SkeletonTimeoutError,
)
from skeleton.client import projects as projects_mod

PROJECT = {
    "project_id": "p1", "owner_id": "u1", "name": "Game", "brief": "make a game",
    "settings": {"a": 1}, "created_at": 1.5, "updated_at": 2.5, "extra": "ignored",
}


def _build(status="queued", **kw):
    return {"build_id": "b1", "project_id": "p1", "status": status, "target": "", "job_id": "j1",
            "result": {}, "error": "", "created_at": 1.0, "updated_at": 1.0, "future_field": 1, **kw}


def _client(handler, *, sleeps=None, token="sess-tok"):
    sleeps = sleeps if sleeps is not None else []
    gw = GatewayClient(
        "http://test",
        client=httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler)),
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0),
        sleep=sleeps.append,
    )
    return ProjectsClient(gw, session_token=token)


def test_dataclasses_tolerate_extra_keys():
    p = Project.from_dict(PROJECT)
    assert p.project_id == "p1" and p.settings == {"a": 1} and p.created_at == 1.5
    b = ProjectBuild.from_dict(_build("succeeded", job_id=None))
    assert b.is_terminal and b.job_id is None


def test_every_method_path_body_and_bearer():
    seen = []

    def handler(req):
        body = json.loads(req.content) if req.content else None
        seen.append((req.method, req.url.path, body, req.headers))
        path = req.url.path
        if req.method == "POST" and path == "/api/app/projects":
            return httpx.Response(201, json=PROJECT)
        if path == "/api/app/projects":
            return httpx.Response(200, json={"projects": [PROJECT]})
        if path == "/api/app/projects/p1":
            return httpx.Response(200, json=PROJECT)
        if req.method == "POST" and path.endswith("/builds"):
            return httpx.Response(202, json=_build())
        if path.endswith("/builds"):
            return httpx.Response(200, json={"builds": [_build(), _build("running")]})
        return httpx.Response(200, json=_build("running"))

    pc = _client(handler)
    assert pc.create("make a game", name="Game", settings={"a": 1}).name == "Game"
    assert seen[-1][2] == {"brief": "make a game", "name": "Game", "settings": {"a": 1}}
    assert [p.project_id for p in pc.list()] == ["p1"]
    assert pc.get("p1").owner_id == "u1"
    b = pc.start_build("p1", target="web", options={"x": 1}, idempotency_key="k1")
    assert b.status == "queued" and seen[-1][2] == {"idempotency_key": "k1", "target": "web", "options": {"x": 1}}
    assert len(pc.list_builds("p1")) == 2
    assert pc.get_build("p1", "b1").status == "running"
    assert seen[-1][1] == "/api/app/projects/p1/builds/b1"
    for _, _, _, headers in seen:
        assert headers["authorization"] == "Bearer sess-tok"
        assert len(headers.get_list("x-request-id")) == 1


def test_missing_token_and_redacted_repr(monkeypatch):
    monkeypatch.delenv("SKELETON_SESSION_TOKEN", raising=False)
    gw = GatewayClient("http://test")
    with pytest.raises(SkeletonSessionConfigError):
        ProjectsClient(gw)
    monkeypatch.setenv("SKELETON_SESSION_TOKEN", "env-secret")
    pc = ProjectsClient(gw)
    assert "env-secret" not in repr(pc)


def test_detail_codes_mapped():
    def handler(req):
        if req.method == "POST":
            return httpx.Response(409, json={"detail": "project_name_conflict"})
        if "/builds/" in req.url.path:
            return httpx.Response(404, json={"detail": "build_not_found"})
        if req.url.path == "/api/app/projects":
            return httpx.Response(401, json={"detail": "invalid_session"})
        return httpx.Response(404, json={"detail": "project_not_found"})

    pc = _client(handler)
    for call, code in [
        (lambda: pc.create("b"), "project_name_conflict"),
        (lambda: pc.get("nope"), "project_not_found"),
        (lambda: pc.get_build("p1", "nope"), "build_not_found"),
        (lambda: pc.list(), "invalid_session"),
    ]:
        with pytest.raises(SkeletonHTTPError) as info:
            call()
        assert info.value.code == code


def test_client_side_length_validation():
    pc = _client(lambda r: pytest.fail("no request expected"))
    with pytest.raises(ValueError):
        pc.create("")
    with pytest.raises(ValueError):
        pc.create("x" * 20001)
    with pytest.raises(ValueError):
        pc.create("ok", name="n" * 201)
    with pytest.raises(ValueError):
        pc.start_build("p1", target="t" * 65)
    with pytest.raises(ValueError):
        pc.start_build("p1", idempotency_key="k" * 129)


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
        keys.append(json.loads(req.content)["idempotency_key"])
        return httpx.Response(503 if len(keys) < 3 else 202, json=_build())

    b = _client(handler, sleeps=sleeps).start_build("p1")
    assert b.build_id == "b1" and len(keys) == 3 and len(set(keys)) == 1
    assert re.fullmatch(r"[0-9a-f]{32}", keys[0]) and len(sleeps) == 2


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


def test_projects_routes_exist_in_4097_router():
    try:
        from skeleton.app_services.projects_api import build_router
    except ImportError:
        pytest.skip("PR #4097 (skeleton.app_services.projects_api) is not on this branch yet")
    router = build_router(services=lambda: None)
    backend = {
        (m, re.sub(r"\{[^}]+\}", "{}", r.path))
        for r in router.routes for m in (getattr(r, "methods", None) or ())
    }
    for method, path in projects_mod.SDK_ROUTES:
        assert (method, re.sub(r"\{[^}]+\}", "{}", path)) in backend, f"{method} {path}"
