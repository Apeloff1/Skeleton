import pytest
from fastapi import HTTPException

from routes import orchestrator
from routes.jeeves_evolution import (
    ModelEndpointSpec,
    RouteProbeRequest,
    TelemetrySample,
    pending,
    route_models,
    status,
)


def _endpoint(
    endpoint_id: str,
    *,
    provider: str | None = None,
    latency: float = 100.0,
    privacy: str = "public",
    local: bool = False,
):
    return ModelEndpointSpec(
        endpoint_id=endpoint_id,
        provider=provider or endpoint_id,
        model=f"{endpoint_id}-model",
        capabilities=["code", "world"],
        nominal_latency_ms=latency,
        privacy_ceiling=privacy,
        local=local,
    )


def test_subrouter_is_mounted_under_existing_orchestrator_namespace():
    paths = {route.path for route in orchestrator.router.routes}
    assert "/api/orchestrator/jeeves/status" in paths
    assert "/api/orchestrator/jeeves/pending" in paths
    assert "/api/orchestrator/jeeves/route" in paths


def test_http_surface_does_not_expose_world_adoption_or_mutation():
    paths = {route.path for route in orchestrator.router.routes if "/jeeves/" in route.path}
    assert paths == {
        "/api/orchestrator/jeeves/status",
        "/api/orchestrator/jeeves/pending",
        "/api/orchestrator/jeeves/route",
    }
    assert status()["world_writes_exposed"] is False


def test_status_exposes_runtime_policy_and_pending_count():
    payload = status()
    assert set(payload) == {
        "runtime",
        "router",
        "pending_count",
        "policy",
        "world_writes_exposed",
    }
    assert payload["pending_count"] >= 0
    assert payload["policy"]["mutation_minimum_gain"] >= payload["policy"]["evolve_minimum_gain"]
    assert payload["policy"]["minimum_evidence"] >= 1
    assert pending()["count"] >= 0


def test_route_probe_enforces_local_only_privacy_before_scoring():
    payload = route_models(
        RouteProbeRequest(
            task_type="world_edit",
            endpoints=[
                _endpoint("remote", latency=5, privacy="public"),
                _endpoint("local", latency=50, privacy="local-only", local=True),
            ],
            required_capabilities=["world"],
            privacy="local-only",
        )
    )
    assert payload["selected"] == "local"
    assert "remote" in payload["rejected"]
    assert any("privacy" in reason for reason in payload["rejected"]["remote"])


def test_route_probe_uses_observed_quality_and_reliability():
    payload = route_models(
        RouteProbeRequest(
            task_type="code",
            endpoints=[_endpoint("a"), _endpoint("b")],
            telemetry=[
                TelemetrySample(
                    endpoint_id="a",
                    ok=False,
                    quality=0.1,
                    latency_ms=500,
                    observed_at=1,
                ),
                TelemetrySample(
                    endpoint_id="b",
                    ok=True,
                    quality=1.0,
                    latency_ms=10,
                    observed_at=1,
                ),
            ],
        )
    )
    assert payload["selected"] == "b"
    assert payload["fallbacks"] == ["a"]


def test_route_probe_is_stateless_between_requests():
    degraded = route_models(
        RouteProbeRequest(
            task_type="code",
            endpoints=[_endpoint("a"), _endpoint("b")],
            telemetry=[
                TelemetrySample(endpoint_id="a", ok=False, quality=0.0, observed_at=1),
                TelemetrySample(endpoint_id="b", ok=True, quality=1.0, observed_at=1),
            ],
        )
    )
    assert degraded["selected"] == "b"

    fresh = route_models(
        RouteProbeRequest(
            task_type="code",
            endpoints=[
                _endpoint("a", latency=10),
                _endpoint("b", latency=100),
            ],
        )
    )
    assert fresh["selected"] == "a"


def test_route_probe_rejects_unknown_telemetry_endpoint():
    with pytest.raises(HTTPException) as exc:
        route_models(
            RouteProbeRequest(
                task_type="code",
                endpoints=[_endpoint("a")],
                telemetry=[TelemetrySample(endpoint_id="missing", ok=True)],
            )
        )
    assert exc.value.status_code == 422
    assert "unknown endpoint" in str(exc.value.detail)


def test_route_probe_rejects_empty_endpoint_catalog():
    with pytest.raises(HTTPException) as exc:
        route_models(RouteProbeRequest(task_type="code", endpoints=[]))
    assert exc.value.status_code == 422
    assert "at least one endpoint" in str(exc.value.detail)
