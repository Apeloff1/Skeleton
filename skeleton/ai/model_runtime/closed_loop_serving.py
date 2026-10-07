"""Closed-loop deterministic serving controller."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .runtime_feedback import DeterministicRuntimeEstimator, FeedbackReceipt
from .runtime_policy import RuntimePolicy
from .serving_telemetry import RequestTelemetry
from .slo_planner import ResourcePlan, SLOResourcePlanner, SLOTarget


@dataclass(frozen=True, slots=True)
class ControlDecision:
    resource_plan: ResourcePlan
    feedback_digest: str
    policy_digest: str
    digest: str


class ClosedLoopServingController:
    """Uses measured performance to tune estimates, never capability authority."""

    def __init__(
        self,
        *,
        policy: RuntimePolicy,
        estimator: DeterministicRuntimeEstimator,
        planner: SLOResourcePlanner | None = None,
    ) -> None:
        if not isinstance(policy, RuntimePolicy):
            raise ValueError("RuntimePolicy required")
        if not isinstance(estimator, DeterministicRuntimeEstimator):
            raise ValueError("DeterministicRuntimeEstimator required")
        self.policy = policy
        self.estimator = estimator
        self.planner = planner or SLOResourcePlanner()

    def observe(self, telemetry: RequestTelemetry, *, kv_bytes_per_token: int) -> FeedbackReceipt:
        return self.estimator.observe(telemetry, kv_bytes_per_token=kv_bytes_per_token)

    def decide(
        self,
        *,
        prompt_tokens: int,
        slo: SLOTarget,
        kv_capacity_bytes: int,
        kv_used_bytes: int,
        queue_pressure_pct: int,
    ) -> ControlDecision:
        feedback = self.estimator.receipt()
        plan = self.planner.plan(
            prompt_tokens=prompt_tokens,
            estimate=feedback.estimate,
            slo=slo,
            kv_capacity_bytes=kv_capacity_bytes,
            kv_used_bytes=kv_used_bytes,
            queue_pressure_pct=queue_pressure_pct,
        )
        body = {
            "schema": "skeleton.ai.closed-loop-serving.v1",
            "resource_plan_digest": plan.digest,
            "feedback_digest": feedback.digest,
            "policy_digest": self.policy.digest,
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ControlDecision(plan, feedback.digest, self.policy.digest, digest)


__all__ = ["ClosedLoopServingController", "ControlDecision"]
