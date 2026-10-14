"""Governed execution bridge for evidence-qualified model routing.

A descriptive RouteQualificationDecision is not execution authority by itself.
This module binds that decision to the exact canonical registry and exact
ModelRouteRequest, then executes through a restricted router containing only
the qualified selected provider. No fallback outside the permit is possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import math
from typing import Any

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.frontier.runtime.model_routing import (
    ModelRouteRequest,
    ModelRouteResult,
    ModelRouter,
    ProviderMetadataError,
)
from skeleton.intelligence.router_registry import RouterRegistry
from skeleton.intelligence.routing_governance import (
    RouteQualificationDecision,
    RouteQualificationRequest,
)


ROUTE_EXECUTION_AUTHORITY_SCOPE = "route-execution-permit-only"


def _sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ProviderMetadataError(f"{field} must be lowercase sha256")
    return value


def route_request_digest(request: ModelRouteRequest) -> str:
    if not isinstance(request, ModelRouteRequest):
        raise TypeError("request must be ModelRouteRequest")
    payload: dict[str, Any] = {
        "request_id": request.request_id,
        "messages": [
            {
                "role": item.role,
                "content": item.content,
                "name": item.name,
            }
            for item in request.messages
        ],
        "required_capabilities": sorted(request.required_capabilities),
        "tools": [
            {
                "name": item.name,
                "description": item.description,
                "input_schema": dict(item.input_schema),
            }
            for item in request.tools
        ],
        "response_schema": (
            None if request.response_schema is None else dict(request.response_schema)
        ),
        "max_output_tokens": request.max_output_tokens,
        "temperature": request.temperature,
        "timeout_seconds": request.timeout_seconds,
        "retry_policy": {
            "max_attempts": request.retry_policy.max_attempts,
            "backoff_seconds": request.retry_policy.backoff_seconds,
        },
        "budget": {
            "max_cost": request.budget.max_cost,
            "max_output_tokens": request.budget.max_output_tokens,
            "max_provider_attempts": request.budget.max_provider_attempts,
        },
        "estimated_input_tokens": request.estimated_input_tokens,
        "metadata": dict(request.metadata),
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class RouteExecutionPermit:
    registry_digest: str
    qualification_digest: str
    qualification_request_digest: str
    execution_request_digest: str
    selected_provider_id: str
    observed_at: float
    authority_scope: str = ROUTE_EXECUTION_AUTHORITY_SCOPE

    def __post_init__(self) -> None:
        for field in (
            "registry_digest",
            "qualification_digest",
            "qualification_request_digest",
            "execution_request_digest",
        ):
            object.__setattr__(self, field, _sha(getattr(self, field), field))
        if (
            not isinstance(self.selected_provider_id, str)
            or not self.selected_provider_id
            or self.selected_provider_id.strip() != self.selected_provider_id
        ):
            raise ProviderMetadataError("selected_provider_id must be normalized text")
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, (int, float))
            or not math.isfinite(float(self.observed_at))
            or float(self.observed_at) < 0
        ):
            raise ProviderMetadataError("observed_at must be finite non-negative")
        object.__setattr__(self, "observed_at", float(self.observed_at))
        if self.authority_scope != ROUTE_EXECUTION_AUTHORITY_SCOPE:
            raise ProviderMetadataError(
                "route execution permit cannot grant provider credentials or publication authority"
            )

    @property
    def digest(self) -> str:
        return sha256(
            canonical_json_bytes(
                {
                    "registry_digest": self.registry_digest,
                    "qualification_digest": self.qualification_digest,
                    "qualification_request_digest": self.qualification_request_digest,
                    "execution_request_digest": self.execution_request_digest,
                    "selected_provider_id": self.selected_provider_id,
                    "observed_at": self.observed_at,
                    "authority_scope": self.authority_scope,
                }
            )
        ).hexdigest()


def issue_route_execution_permit(
    registry: RouterRegistry,
    qualification_request: RouteQualificationRequest,
    decision: RouteQualificationDecision,
    execution_request: ModelRouteRequest,
) -> RouteExecutionPermit:
    if not isinstance(registry, RouterRegistry):
        raise TypeError("registry must be RouterRegistry")
    if not isinstance(qualification_request, RouteQualificationRequest):
        raise TypeError("qualification_request must be RouteQualificationRequest")
    if not isinstance(decision, RouteQualificationDecision):
        raise TypeError("decision must be RouteQualificationDecision")
    if not isinstance(execution_request, ModelRouteRequest):
        raise TypeError("execution_request must be ModelRouteRequest")

    snapshot = registry.snapshot()
    if not hmac.compare_digest(decision.registry_digest, snapshot.digest):
        raise ProviderMetadataError("qualification decision registry is stale")
    if not hmac.compare_digest(decision.request_digest, qualification_request.digest):
        raise ProviderMetadataError("qualification request digest mismatch")
    if decision.selected_provider_id is None:
        raise ProviderMetadataError("qualification decision selected no provider")
    if decision.selected_provider_id not in decision.eligible_provider_ids:
        raise ProviderMetadataError("selected provider is not qualification-eligible")

    providers = {item.provider_id: item for item in snapshot.providers}
    selected = providers.get(decision.selected_provider_id)
    if selected is None:
        raise ProviderMetadataError("selected provider is absent from registry")

    if set(execution_request.required_capabilities) != set(
        qualification_request.required_capabilities
    ):
        raise ProviderMetadataError(
            "execution capabilities do not match qualified capabilities"
        )
    if execution_request.estimated_input_tokens != qualification_request.input_tokens:
        raise ProviderMetadataError(
            "execution input token estimate does not match qualification"
        )
    if execution_request.max_output_tokens != qualification_request.output_tokens:
        raise ProviderMetadataError(
            "execution output token ceiling does not match qualification"
        )
    if (
        qualification_request.max_estimated_cost is not None
        and execution_request.budget.max_cost is not None
        and execution_request.budget.max_cost
        > qualification_request.max_estimated_cost
    ):
        raise ProviderMetadataError(
            "execution cost budget exceeds qualified maximum"
        )

    return RouteExecutionPermit(
        registry_digest=snapshot.digest,
        qualification_digest=decision.digest,
        qualification_request_digest=qualification_request.digest,
        execution_request_digest=route_request_digest(execution_request),
        selected_provider_id=selected.provider_id,
        observed_at=decision.observed_at,
    )


class GovernedModelRouter:
    """Execute exact qualified requests without unqualified provider fallback."""

    def __init__(self, registry: RouterRegistry, router: ModelRouter) -> None:
        if not isinstance(registry, RouterRegistry):
            raise TypeError("registry must be RouterRegistry")
        if not isinstance(router, ModelRouter):
            raise TypeError("router must be ModelRouter")
        expected = {
            item.provider_id: item
            for item in registry.snapshot().providers
        }
        actual = router.catalog()
        if set(expected) != set(actual):
            raise ProviderMetadataError(
                "router catalog does not match governed registry identities"
            )
        for provider_id, metadata in expected.items():
            if actual[provider_id] != metadata:
                raise ProviderMetadataError(
                    f"router catalog metadata drift for {provider_id}"
                )
        self.registry = registry
        self.router = router

    async def invoke(
        self,
        request: ModelRouteRequest,
        permit: RouteExecutionPermit,
    ) -> ModelRouteResult:
        if not isinstance(request, ModelRouteRequest):
            raise TypeError("request must be ModelRouteRequest")
        if not isinstance(permit, RouteExecutionPermit):
            raise TypeError("permit must be RouteExecutionPermit")

        snapshot = self.registry.snapshot()
        if not hmac.compare_digest(permit.registry_digest, snapshot.digest):
            raise ProviderMetadataError("route execution permit registry is stale")
        if not hmac.compare_digest(
            permit.execution_request_digest,
            route_request_digest(request),
        ):
            raise ProviderMetadataError(
                "route execution permit does not bind this exact request"
            )

        metadata = self.router.catalog().get(permit.selected_provider_id)
        if metadata is None:
            raise ProviderMetadataError(
                "route execution permit selected unknown provider"
            )
        adapter = self.router.runtime.resolve(metadata.adapter_name)

        restricted = ModelRouter(runtime=self.router.runtime)
        restricted.register(metadata, adapter)
        plan = restricted.plan(request)
        if plan.provider_ids != (permit.selected_provider_id,):
            raise ProviderMetadataError(
                "qualified provider is not executable for bound request"
            )

        result = await restricted.invoke(request)
        if result.ok and result.selected_provider_id != permit.selected_provider_id:
            raise ProviderMetadataError(
                "runtime selected provider outside execution permit"
            )
        if any(
            attempt.provider_id != permit.selected_provider_id
            for attempt in result.attempts
        ):
            raise ProviderMetadataError(
                "runtime attempted provider outside execution permit"
            )
        return result


__all__ = [
    "ROUTE_EXECUTION_AUTHORITY_SCOPE",
    "GovernedModelRouter",
    "RouteExecutionPermit",
    "issue_route_execution_permit",
    "route_request_digest",
]
