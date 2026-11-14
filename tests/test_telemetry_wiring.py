"""Tests for skeleton.telemetry.wiring (#121 opt-in plane wiring)."""

from __future__ import annotations

import asyncio
import filecmp
from pathlib import Path

import pytest

from skeleton.automation.agents.coordination import Coordinator, TaskStatus
from skeleton.kernel.orchestrator import Orchestrator
from skeleton.observability.correlation import correlation_scope, get_correlation_id
from skeleton.telemetry.planes import PlaneTelemetry
from skeleton.telemetry.wiring import (
    HTTP_STATUS,
    PlaneTelemetryMiddleware,
    install_plane_telemetry,
    instrument_coordinator,
    instrument_kernel_orchestrator,
    traced,
)

ROOT = Path(__file__).resolve().parents[1]


def test_traced_sync_and_async_emit_spans_and_errors():
    tel = PlaneTelemetry()

    @traced("agents", "plan", telemetry=tel)
    def plan(x):
        return x + 1

    @traced("agents", "act", telemetry=tel)
    async def act():
        raise ValueError("nope")

    assert plan(1) == 2
    assert traced("agents", "plan", telemetry=tel)(plan) is plan  # idempotent
    with pytest.raises(ValueError):
        asyncio.run(act())
    assert tel.summary("agents", "plan")["calls"] == 1.0
    assert tel.summary("agents", "act")["errors"] == 1.0


def test_kernel_orchestrator_dispatch_span_is_correlated():
    tel = PlaneTelemetry()
    orch = instrument_kernel_orchestrator(Orchestrator(), telemetry=tel)
    assert instrument_kernel_orchestrator(orch, telemetry=tel) is orch
    with correlation_scope("req-kernel-121"):
        result = orch.dispatch("plan tensor ttk")
    assert result["kind"] == "kernel-orch"
    assert tel.summary("kernel", "dispatch")["calls"] == 1.0
    spans = tel.traces("req-kernel-121")
    assert [s["name"] for s in spans] == ["kernel.dispatch"]
    assert spans[0]["attributes"]["kernel.kind"] == "kernel-orch"


def test_coordinator_binds_metadata_correlation_for_nested_kernel_spans():
    tel = PlaneTelemetry()
    coordinator = instrument_coordinator(Coordinator(), telemetry=tel)
    kernel = instrument_kernel_orchestrator(Orchestrator(), telemetry=tel)
    seen = {}

    def handler(task):
        seen["cid"] = get_correlation_id()
        return kernel.dispatch(task.description)["kind"]

    coordinator.pool.create({"work"}, capacity=1)
    coordinator.register_handler("work", handler)
    task = coordinator.dispatch("plan tensor ttk", task_type="work", metadata={"request_id": "req-agent-121"})
    assert task.status is TaskStatus.COMPLETED
    assert seen["cid"] == "req-agent-121"
    names = [s["name"] for s in tel.traces("req-agent-121")]
    assert names == ["kernel.dispatch", "agents.execute", "agents.dispatch"]  # finish order
    assert tel.summary("agents", "execute")["calls"] == 1.0
    assert get_correlation_id() == ""


async def _app(scope, receive, send):
    if scope["path"] == "/boom":
        raise RuntimeError("boom")
    status = 503 if scope["path"] == "/down" else 200
    await send({"type": "http.response.start", "status": status, "headers": []})
    await send({"type": "http.response.body", "body": get_correlation_id().encode()})


def _call(mw, path, headers=()):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "get", "path": path, "headers": list(headers), "state": {}}
    asyncio.run(mw(scope, receive, send))
    return sent, scope


def test_api_middleware_binds_request_id_and_echoes_header():
    tel = PlaneTelemetry()
    mw = PlaneTelemetryMiddleware(_app, telemetry=tel)
    sent, scope = _call(mw, "/api/v1/health", [(b"x-request-id", b"req-api-121")])
    assert sent[1]["body"] == b"req-api-121"
    assert (b"x-request-id", b"req-api-121") in sent[0]["headers"]
    assert scope["state"]["request_id"] == "req-api-121"
    span = tel.traces("req-api-121")[0]
    assert span["name"] == "api.request"
    assert span["attributes"]["http.status_code"] == 200
    assert tel.registry.get_counter(HTTP_STATUS, {"plane": "api", "op": "request", "status": "2xx"}) == 1.0


def test_api_middleware_rejects_duplicate_or_bad_ids_and_counts_errors():
    tel = PlaneTelemetry()
    mw = PlaneTelemetryMiddleware(_app, telemetry=tel)
    sent, _ = _call(mw, "/down", [(b"x-request-id", b"a"), (b"x-request-id", b"b")])
    minted = sent[1]["body"].decode()
    assert minted not in {"a", "b"} and len(minted) == 16
    sent, _ = _call(mw, "/down", [(b"x-request-id", b"bad id!")])
    assert sent[1]["body"] != b"bad id!"
    assert tel.summary("api", "request")["errors"] == 2.0
    with pytest.raises(RuntimeError):
        _call(mw, "/boom")
    assert tel.summary("api", "request")["errors"] == 3.0
    passthrough = []

    async def lifespan_app(scope, receive, send):
        passthrough.append(scope["type"])

    asyncio.run(PlaneTelemetryMiddleware(lifespan_app, telemetry=tel)({"type": "lifespan"}, None, None))
    assert passthrough == ["lifespan"]


def test_install_on_fastapi_app_end_to_end():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    tel = PlaneTelemetry()
    app = fastapi.FastAPI()

    @app.get("/ping")
    def ping():
        return {"cid": get_correlation_id()}

    install_plane_telemetry(app, telemetry=tel)
    install_plane_telemetry(app, telemetry=tel)
    response = TestClient(app).get("/ping", headers={"X-Request-ID": "req-fastapi-121"})
    assert response.json() == {"cid": "req-fastapi-121"}
    assert response.headers["x-request-id"] == "req-fastapi-121"
    assert tel.summary("api", "request")["calls"] == 1.0


def test_compat_mirror_is_byte_identical():
    for name in ("planes.py", "wiring.py"):
        assert filecmp.cmp(
            ROOT / "skeleton/telemetry" / name,
            ROOT / "skeleton/ai/compat/telemetry" / name,
            shallow=False,
        )


def test_private_paths_and_unbounded_method_values_never_enter_span():
    tel = PlaneTelemetry()
    mw = PlaneTelemetryMiddleware(_app, telemetry=tel)
    secret_path = "/account/private-user/file/opaque-private-source"
    sent, _ = _call(mw, secret_path, [(b"x-request-id", b"req-privacy")])
    assert sent[0]["status"] == 200
    attrs = tel.traces("req-privacy")[0]["attributes"]
    assert attrs["http.method"] == "GET"
    assert "http.path" not in attrs
    assert "opaque-private-source" not in str(attrs)


def test_exception_after_5xx_and_missing_response_count_once():
    tel = PlaneTelemetry()

    async def after_error(scope, receive, send):
        await send({"type": "http.response.start", "status": 503, "headers": []})
        raise RuntimeError("private upstream detail")

    with pytest.raises(RuntimeError):
        _call(PlaneTelemetryMiddleware(after_error, telemetry=tel), "/partial")
    assert tel.summary("api", "request")["errors"] == 1.0

    async def no_response(scope, receive, send):
        return None

    _call(PlaneTelemetryMiddleware(no_response, telemetry=tel), "/missing")
    assert tel.summary("api", "request")["errors"] == 2.0


def test_downstream_correlation_headers_are_canonical_and_unique():
    async def conflicting(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"X-Request-ID", b"unrelated"), (b"x-request-id", b"duplicate"),
            (b"content-type", b"text/plain"),
        ]})
    sent, _ = _call(PlaneTelemetryMiddleware(conflicting, telemetry=PlaneTelemetry()),
                    "/ok", [(b"x-request-id", b"canonical-id")])
    assert [v for k, v in sent[0]["headers"] if k.lower() == b"x-request-id"] == [b"canonical-id"]
    assert (b"content-type", b"text/plain") in sent[0]["headers"]
