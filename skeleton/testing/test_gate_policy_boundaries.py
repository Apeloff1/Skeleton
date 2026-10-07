from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from skeleton.api.middleware import BodyBoundMiddleware, GatePolicy


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/health/",
        "/health/live",
        "/ready",
        "/api/v1/health/live",
        "/api/v1/health/ready",
    ],
)
def test_open_routes_allow_only_exact_routes_and_true_children(path: str) -> None:
    assert GatePolicy().is_open_route(path)


@pytest.mark.parametrize(
    "path",
    [
        "/healthcare",
        "/health-check",
        "/readyz",
        "/metrics",
        "/metrics-private",
        "/api/v1/health",
        "/api/v1/healthcare",
        "/api/v1/metrics",
        "/api/v1/metrics-private",
    ],
)
def test_sensitive_or_lookalike_routes_remain_sealed(path: str) -> None:
    assert not GatePolicy().is_open_route(path)


def test_root_open_prefix_is_exact_only() -> None:
    policy = GatePolicy(open_prefixes=("/",))

    assert policy.is_open_route("/")
    assert not policy.is_open_route("/admin")


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/forge", "forge"),
        ("/api/v1/forge/jobs", "forge"),
        ("/api/v1/cortex", "cognition"),
        ("/api/v1/cortex/status", "cognition"),
        ("/api/v1/health", "observability"),
        ("/api/v1/metrics", "observability"),
        ("/api/v1/application", "application"),
        ("/api/v1/application/capabilities", "application"),
        ("/api/v1/application/capabilities/lifecycle", "application"),
        ("/api/v1/application/planes/audit", "application"),
        ("/api/v1/application/planes/audit/galaxy", "application"),
        ("/api/v1/application/genesis/audit", "application"),
        ("/api/v1/application/genesis/audit/galaxy", "application"),
        ("/api/v1/application/capabilities/export-audit", "application"),
        ("/api/v1/application/capabilities/export-audit/cortex", "application"),
        ("/api/v1/application/routes/audit", "application"),
        ("/api/v1/application/routes/audit/POST/api/v1/pipeline/npc", "application"),
        ("/api/v1/application/hmac/audit", "application"),
        ("/api/v1/application/hmac/audit/GET/api/v1/health", "application"),
        ("/cortex/status", "cognition"),
        ("/cockpit", "interface"),
        ("/openapi.json", "interface"),
    ],
)
def test_governance_domain_matches_exact_routes_and_children(path: str, expected: str) -> None:
    assert GatePolicy().required_domain(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/forge-admin",
        "/api/v1/cortexual",
        "/api/v1/application-admin",
        "/api/governance-backdoor",
        "/api/courtroom",
        "/cockpit-admin",
        "/docs-private",
    ],
)
def test_governance_domain_lookalikes_are_unwritten(path: str) -> None:
    assert GatePolicy().required_domain(path) is None


def test_server_default_open_surface_is_probe_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from skeleton.api import server

    monkeypatch.delenv("SKELETON_PUBLIC_DEV_SURFACES", raising=False)
    prefixes = server._gate_open_prefixes()

    assert "/" in prefixes
    assert "/api/v1/health/live" in prefixes
    assert "/api/v1/health/ready" in prefixes
    for sensitive in (
        "/api/v1/health",
        "/api/v1/metrics",
        "/api/v1/genesis",
        "/cortex/status",
        "/cockpit",
        "/docs",
        "/openapi.json",
        "/redoc",
    ):
        assert sensitive not in prefixes


def test_engine_service_prefix_is_exactly_exempt_from_generic_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skeleton.api import server

    monkeypatch.delenv("SKELETON_PUBLIC_DEV_SURFACES", raising=False)
    policy = GatePolicy(
        open_prefixes=server._gate_open_prefixes(),
        body_limits=server._gate_body_limits(),
    )

    assert policy.is_open_route("/api/v1/engine/executions")
    assert policy.is_open_route("/api/v1/engine/media/images/edit")
    assert not policy.is_open_route("/api/v1/engineer")
    assert not policy.is_open_route("/api/v1/engines")

    mib = 1024 * 1024
    assert policy.body_limit("/api/v1/engine/executions", mib) == 4 * mib
    assert policy.body_limit("/api/v1/engine/media/images/variation", mib) == 34 * mib
    assert policy.body_limit("/api/v1/engine/media/images/edit", mib) == 70 * mib
    assert policy.body_limit("/api/v1/swarm/status", mib) == mib


def test_every_engine_route_keeps_dedicated_service_token_dependency() -> None:
    from fastapi.routing import APIRoute

    from skeleton.api.engine_routes import _engine_service_token, router

    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert routes
    for route in routes:
        dependency_calls = {
            dependency.call
            for dependency in route.dependant.dependencies
        }
        assert _engine_service_token in dependency_calls, (
            f"{sorted(route.methods)} {route.path} lost engine service token auth"
        )


def test_dev_surface_exposure_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    from skeleton.api import server

    monkeypatch.setenv("SKELETON_PUBLIC_DEV_SURFACES", "true")
    prefixes = server._gate_open_prefixes()

    for dev_surface in server._DEV_OPEN_PREFIXES:
        assert dev_surface in prefixes


def _exercise_body_bound(
    chunks: list[bytes],
    *,
    max_body: int = 5,
    content_length: Optional[str] = None,
) -> tuple[list[dict], list[bytes]]:
    messages = [
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    ]
    if not messages:
        messages.append({"type": "http.request", "body": b"", "more_body": False})

    sent: list[dict] = []
    consumed: list[bytes] = []

    async def receive() -> dict:
        return messages.pop(0)

    async def send(message: dict) -> None:
        sent.append(message)

    async def app(_scope, bounded_receive, bounded_send) -> None:
        body = bytearray()
        while True:
            message = await bounded_receive()
            if message["type"] != "http.request":
                break
            body.extend(message.get("body") or b"")
            if not message.get("more_body", False):
                break
        consumed.append(bytes(body))
        await bounded_send({"type": "http.response.start", "status": 204, "headers": []})
        await bounded_send({"type": "http.response.body", "body": b""})

    headers = []
    if content_length is not None:
        headers.append((b"content-length", content_length.encode("ascii")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/forge",
        "raw_path": b"/api/v1/forge",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    asyncio.run(BodyBoundMiddleware(app, max_body_bytes=max_body)(scope, receive, send))
    return sent, consumed


def _response_status(sent: list[dict]) -> int:
    start = next(message for message in sent if message["type"] == "http.response.start")
    return int(start["status"])


def test_streamed_body_without_content_length_cannot_bypass_limit() -> None:
    sent, consumed = _exercise_body_bound([b"abc", b"def"], max_body=5)

    assert _response_status(sent) == 413
    assert consumed == []


def test_forged_small_content_length_cannot_bypass_actual_byte_limit() -> None:
    sent, consumed = _exercise_body_bound(
        [b"abc", b"def"], max_body=5, content_length="1"
    )

    assert _response_status(sent) == 413
    assert consumed == []


def test_exact_body_limit_passes() -> None:
    sent, consumed = _exercise_body_bound([b"ab", b"cde"], max_body=5)

    assert _response_status(sent) == 204
    assert consumed == [b"abcde"]


def test_declared_oversize_body_is_rejected_before_read() -> None:
    sent, consumed = _exercise_body_bound([b"x"], max_body=5, content_length="6")

    assert _response_status(sent) == 413
    assert consumed == []


@pytest.mark.parametrize("bad_length", ["nope", "-1"])
def test_malformed_content_length_is_rejected(bad_length: str) -> None:
    sent, consumed = _exercise_body_bound([b"x"], max_body=5, content_length=bad_length)

    assert _response_status(sent) == 400
    assert consumed == []


def test_non_positive_body_limit_fails_closed() -> None:
    async def app(_scope, _receive, _send) -> None:
        raise AssertionError("app must not run")

    with pytest.raises(ValueError, match="positive"):
        BodyBoundMiddleware(app, max_body_bytes=0)


def test_bool_and_float_body_limit_fails_closed() -> None:
    async def app(_scope, _receive, _send) -> None:
        raise AssertionError("app must not run")

    with pytest.raises(TypeError, match="integer"):
        BodyBoundMiddleware(app, max_body_bytes=True)
    with pytest.raises(TypeError, match="integer"):
        BodyBoundMiddleware(app, max_body_bytes=False)
    with pytest.raises(TypeError, match="integer"):
        BodyBoundMiddleware(app, max_body_bytes=1.5)
