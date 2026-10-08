"""Bridge verified model admission to the canonical serving planner.

No model execution occurs here: the trusted adapter must be supplied by the
deployment composition root, never from an untrusted request.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from .capacity import CapacityLedger

from skeleton.ai.model_runtime.serving_policy import (
    PolicyAwareServingPlanner,
    ServingRequest as RuntimeServingRequest,
    ServingPlan,
)

from .admission import ServingPolicy
from .verified import AdmissionDenied, ServingRequest, verified_invoke


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
    ledger: CapacityLedger | None = None,
) -> PlannedInvocation:
    """Fail closed before planning and execution; do not retry failures."""
    if not isinstance(planner, PolicyAwareServingPlanner):
        raise TypeError("canonical serving planner required")
    if not isinstance(request, RuntimeServingRequest):
        raise TypeError("canonical serving request required")
    if not callable(invoke):
        raise AdmissionDenied("trusted backend callback required")
    # Pre-admission binds the raw prompt/output token counts, not cached or
    # degraded planner estimates. Never allow a plan to bypass request limits.
    admission_request = ServingRequest(
        backend=backend,
        context_tokens=request.prompt_tokens,
        output_tokens=request.output_tokens,
    )

    def authorized_invoke(_admission_request):
        lease = None
        if ledger is not None:
            if not isinstance(ledger, CapacityLedger):
                raise TypeError("CapacityLedger required")
            fingerprint = sha256(json.dumps({
                "model": policy.model_digest,
                "evaluation": policy.evaluation_digest,
                "backend": backend,
                "request": request.request_id,
                "prompt_tokens": request.prompt_tokens,
                "output_tokens": request.output_tokens,
            }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            lease = ledger.acquire(request.request_id, fingerprint,
                                   request.prompt_tokens + request.output_tokens,
                                   exclusive=True, in_flight=True)
        try:
            plan = planner.plan(request)
            result = invoke(plan)
            return PlannedInvocation(plan, result)
        finally:
            if lease is not None:
                ledger.release(lease)

    return verified_invoke(
        policy, admission_request, model_bytes=model_bytes,
        evaluation_bytes=evaluation_bytes, invoke=authorized_invoke,
    )
