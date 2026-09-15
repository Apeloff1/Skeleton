"""Regression tests for the shared observability contract (#121)."""

from types import SimpleNamespace

from skeleton.agents.bridge import MeshBridge
from skeleton.api.gateway import APIGateway, GatewayRequest
from skeleton.application.runtime_commands import build_runtime_command_service
from skeleton.observability.contract import redact, reset_observability


class _Agent:
    agent_id = "agent-7"


class _Mesh:
    def route(self, _specialisation):
        return _Agent()


class _Capability:
    def to_dict(self):
        return {"name": "inspect"}


class _Registry:
    def list(self):
        return [_Capability()]


class _Task:
    def __init__(self):
        self.task_id = "task-9"
        self.metadata = {}


def test_redaction_is_recursive_and_preserves_non_sensitive_fields():
    payload = {
        "authorization": "Bearer top-secret",
        "nested": {
            "api-key": "abc123",
            "password": "hunter2",
            "safe": "visible",
        },
        "items": [{"access_token": "token-value", "count": 2}],
    }

    safe = redact(payload)

    assert safe["authorization"] == "[REDACTED]"
    assert safe["nested"]["api-key"] == "[REDACTED]"
    assert safe["nested"]["password"] == "[REDACTED]"
    assert safe["nested"]["safe"] == "visible"
    assert safe["items"][0]["access_token"] == "[REDACTED]"
    assert safe["items"][0]["count"] == 2


def test_api_agent_tool_correlation_survives_end_to_end():
    telemetry = reset_observability()
    bridge = MeshBridge(_Mesh())
    service = build_runtime_command_service(SimpleNamespace(registry=_Registry()))
    captured = {}

    def handler(_payload):
        task = _Task()
        assert bridge.dispatch(task, "planner") is True
        captured["task"] = task
        result = service.execute("tool", {"action": "list", "tool_id": "registry.inspect"})
        assert result.ok is True
        return {"tool": result.data}

    gateway = APIGateway()
    gateway.route("/execute", handler)
    response = gateway.handle(
        GatewayRequest(
            "/execute",
            request_id="req-123",
            run_id="run-456",
            trace_id="trace-789",
            payload={"authorization": "must-not-leak"},
        )
    )

    assert response.status == 200
    assert response.request_id == "req-123"
    assert response.run_id == "run-456"
    assert response.trace_id == "trace-789"

    task_correlation = captured["task"].metadata["correlation"]
    assert task_correlation == {
        "request_id": "req-123",
        "run_id": "run-456",
        "trace_id": "trace-789",
        "agent_id": "agent-7",
        "tool_id": None,
    }

    events = telemetry.events()
    agent_event = next(event for event in events if event["event"] == "mesh.dispatch")
    tool_event = next(event for event in events if event["event"] == "runtime.tool")
    api_event = next(event for event in events if event["event"] == "gateway.request")

    assert agent_event["correlation"]["request_id"] == "req-123"
    assert agent_event["correlation"]["agent_id"] == "agent-7"
    assert tool_event["correlation"] == {
        "request_id": "req-123",
        "run_id": "run-456",
        "trace_id": "trace-789",
        "agent_id": "agent-7",
        "tool_id": "registry.inspect",
    }
    assert api_event["correlation"]["tool_id"] == "registry.inspect"

    snapshot = telemetry.metrics.snapshot()
    counters = snapshot["counters"]
    histograms = snapshot["histograms"]
    assert any(key.startswith("skeleton_operations_total{") for key in counters)
    assert any("component=api" in key for key in counters)
    assert any("component=agent" in key for key in counters)
    assert any("component=tool" in key for key in counters)
    assert any(key.startswith("skeleton_operation_latency_ms{") for key in histograms)


def test_gateway_emits_failure_and_rate_limit_baselines():
    telemetry = reset_observability()
    gateway = APIGateway()
    gateway.route("/limited", lambda _payload: {"ok": True}, rate_limit_per_s=1)

    first = gateway.handle(GatewayRequest("/limited", actor="same"))
    second = gateway.handle(GatewayRequest("/limited", actor="same"))

    assert first.status == 200
    assert second.status == 429
    counters = telemetry.metrics.snapshot()["counters"]
    assert any(key.startswith("skeleton_failures_total{") for key in counters)
    assert any(key.startswith("skeleton_rate_limits_total{") for key in counters)
