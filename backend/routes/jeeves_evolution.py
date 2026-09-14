"""Safe HTTP probes for the Jeeves evolution control plane.

Mounted as a sub-router of ``routes.orchestrator``.  This first API slice is
intentionally non-destructive: it exposes runtime/pending status and a stateless
model-routing policy probe, but it does not provide canonical WorldGraph write
endpoints.  World adoption stays an internal capability until Galaxy Studio has
an explicit, revision-safe WorldGraph adapter.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.jeeves_control_plane import JeevesControlPlane
from core.model_router import (
    ModelEndpoint,
    ModelRouter,
    NoRoute,
    PrivacyLevel,
    RouteRequest,
)

router = APIRouter(prefix="/jeeves", tags=["orchestrator", "jeeves-evolution"])
_CONTROL_PLANE = JeevesControlPlane()
_MAX_ENDPOINTS = 128
_MAX_TELEMETRY_SAMPLES = 512


def get_control_plane() -> JeevesControlPlane:
    """Return the process-wide control plane used by this API surface."""
    return _CONTROL_PLANE


class ModelEndpointSpec(BaseModel):
    endpoint_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    capabilities: list[str] = Field(default_factory=list)
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    max_context_tokens: int = Field(default=0, ge=0)
    input_cost_per_million: float = Field(default=0.0, ge=0)
    output_cost_per_million: float = Field(default=0.0, ge=0)
    nominal_latency_ms: float = Field(default=1000.0, ge=0)
    privacy_ceiling: str = "public"
    local: bool = False
    enabled: bool = True

    def build(self) -> ModelEndpoint:
        return ModelEndpoint(
            endpoint_id=self.endpoint_id,
            provider=self.provider,
            model=self.model,
            capabilities=frozenset(self.capabilities),
            modalities=frozenset(self.modalities),
            max_context_tokens=self.max_context_tokens,
            input_cost_per_million=self.input_cost_per_million,
            output_cost_per_million=self.output_cost_per_million,
            nominal_latency_ms=self.nominal_latency_ms,
            privacy_ceiling=PrivacyLevel.parse(self.privacy_ceiling),
            local=self.local,
            enabled=self.enabled,
        )


class TelemetrySample(BaseModel):
    endpoint_id: str = Field(min_length=1, max_length=128)
    ok: bool
    quality: float | None = Field(default=None, ge=0, le=1)
    latency_ms: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    observed_at: float | None = Field(default=None, ge=0)


class RouteProbeRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=128)
    endpoints: list[ModelEndpointSpec]
    telemetry: list[TelemetrySample] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    required_modalities: list[str] = Field(default_factory=lambda: ["text"])
    context_tokens: int = Field(default=0, ge=0)
    expected_output_tokens: int = Field(default=0, ge=0)
    privacy: str = "public"
    latency_budget_ms: float | None = Field(default=None, ge=0)
    cost_budget: float | None = Field(default=None, ge=0)
    preferred_providers: list[str] = Field(default_factory=list)
    excluded_endpoints: list[str] = Field(default_factory=list)
    minimum_reliability: float = Field(default=0.0, ge=0, le=1)
    minimum_quality: float = Field(default=0.0, ge=0, le=1)


def _policy_snapshot(control: JeevesControlPlane) -> dict[str, Any]:
    policy = control.policy
    return {
        "minimum_evidence": policy.minimum_evidence,
        "evolve_minimum_gain": policy.evolve_minimum_gain,
        "mutation_minimum_gain": policy.mutation_minimum_gain,
        "metrics": [
            {
                "name": spec.name,
                "direction": spec.direction.value,
                "weight": spec.weight,
                "max_regression_fraction": spec.max_regression_fraction,
                "floor": spec.floor,
                "ceiling": spec.ceiling,
            }
            for spec in policy.metrics
        ],
    }


@router.get("/status")
def status() -> dict[str, Any]:
    control = get_control_plane()
    snapshot = control.snapshot()
    return {
        "runtime": snapshot["runtime"],
        "router": snapshot["router"],
        "pending_count": len(snapshot["pending"]),
        "policy": _policy_snapshot(control),
        "world_writes_exposed": False,
    }


@router.get("/pending")
def pending() -> dict[str, Any]:
    rows = [row.as_dict() for row in get_control_plane().pending()]
    return {"count": len(rows), "items": rows}


@router.post("/route")
def route_models(req: RouteProbeRequest) -> dict[str, Any]:
    """Evaluate one provider-neutral route without mutating shared router state."""
    if not req.endpoints:
        raise HTTPException(status_code=422, detail="at least one endpoint is required")
    if len(req.endpoints) > _MAX_ENDPOINTS:
        raise HTTPException(
            status_code=413,
            detail=f"endpoint limit exceeded: {len(req.endpoints)} > {_MAX_ENDPOINTS}",
        )
    if len(req.telemetry) > _MAX_TELEMETRY_SAMPLES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"telemetry sample limit exceeded: {len(req.telemetry)} > "
                f"{_MAX_TELEMETRY_SAMPLES}"
            ),
        )

    local_router = ModelRouter()
    try:
        for endpoint in req.endpoints:
            local_router.register(endpoint.build())
        for sample in req.telemetry:
            local_router.observe(
                sample.endpoint_id,
                ok=sample.ok,
                quality=sample.quality,
                latency_ms=sample.latency_ms,
                cost=sample.cost,
                observed_at=sample.observed_at,
            )
        decision = local_router.route(
            RouteRequest(
                task_type=req.task_type,
                required_capabilities=frozenset(req.required_capabilities),
                required_modalities=frozenset(req.required_modalities),
                context_tokens=req.context_tokens,
                expected_output_tokens=req.expected_output_tokens,
                privacy=PrivacyLevel.parse(req.privacy),
                latency_budget_ms=req.latency_budget_ms,
                cost_budget=req.cost_budget,
                preferred_providers=tuple(req.preferred_providers),
                excluded_endpoints=frozenset(req.excluded_endpoints),
                minimum_reliability=req.minimum_reliability,
                minimum_quality=req.minimum_quality,
            )
        )
    except NoRoute as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return decision.as_dict()
