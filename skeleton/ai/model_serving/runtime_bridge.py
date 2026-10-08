"""Bridge verified model admission to the canonical serving planner.

No model execution occurs here: the trusted adapter must be supplied by the
deployment composition root, never from an untrusted request.
"""
from dataclasses import dataclass

from skeleton.ai.model_runtime.serving_policy import (
    PolicyAwareServingPlanner,
    ServingRequest as RuntimeServingRequest,
    ServingPlan,
)

from .admission import ServingPolicy
from .verified import ServingRequest, verified_invoke


@dataclass(frozen=True)
class PlannedInvocation:
    plan: ServingPlan
    backend_result: object


def plan_and_invoke(
    *,
    policy: ServingPolicy,
    planner: PolicyAwareServingPlanner,
    request: RuntimeServingRequest,
    model_bytes: bytes,
    evaluation_bytes: bytes,
    backend: str,
    invoke,
) -> PlannedInvocation:
    """Fail closed before planning and execution; do not retry failures."""
    if not isinstance(planner, PolicyAwareServingPlanner):
        raise TypeError("canonical serving planner required")
    if not isinstance(request, RuntimeServingRequest):
        raise TypeError("canonical serving request required")
    # Pre-admission binds the raw prompt/output token counts, not cached or
    # degraded planner estimates. Never allow a plan to bypass request limits.
    admission_request = ServingRequest(
        backend=backend,
        context_tokens=request.prompt_tokens,
        output_tokens=request.output_tokens,
    )

    def authorized_invoke(_admission_request):
        plan = planner.plan(request)
        result = invoke(plan)
        return PlannedInvocation(plan, result)

    return verified_invoke(
        policy, admission_request, model_bytes=model_bytes,
        evaluation_bytes=evaluation_bytes, invoke=authorized_invoke,
    )
