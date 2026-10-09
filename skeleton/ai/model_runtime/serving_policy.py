"""Policy-aware serving planner for local transformer inference."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from .runtime_policy import RuntimePolicy


class ServiceClass(str, Enum):
    INTERACTIVE = "interactive"
    STANDARD = "standard"
    THROUGHPUT = "throughput"
    BACKGROUND = "background"


@dataclass(frozen=True, slots=True)
class ServingRequest:
    request_id: str
    prompt_tokens: int
    output_tokens: int
    service_class: ServiceClass = ServiceClass.STANDARD
    prefix_tokens: int = 0
    prefix_cached: bool = False
    draft_model_available: bool = False

    def __post_init__(self) -> None:
        if not self.request_id:
            raise ValueError("request_id required")
        for name in ("prompt_tokens", "output_tokens", "prefix_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"invalid {name}")
        if self.prompt_tokens + self.output_tokens <= 0:
            raise ValueError("empty serving request")
        if self.prefix_tokens > self.prompt_tokens:
            raise ValueError("prefix exceeds prompt")


@dataclass(frozen=True, slots=True)
class ServingPlan:
    request_id: str
    service_class: ServiceClass
    prefill_tokens: int
    decode_tokens: int
    prefix_reused_tokens: int
    phase_mode: str
    speculative: bool
    priority_boost: int
    degradation: tuple[str, ...]
    policy_digest: str
    digest: str


class PolicyAwareServingPlanner:
    def __init__(self, policy: RuntimePolicy) -> None:
        if not isinstance(policy, RuntimePolicy):
            raise ValueError("RuntimePolicy required")
        self.policy = policy

    def plan(
        self,
        request: ServingRequest,
        *,
        kv_pressure_pct: int = 0,
        queue_pressure_pct: int = 0,
    ) -> ServingPlan:
        for name, value in (("kv_pressure_pct", kv_pressure_pct), ("queue_pressure_pct", queue_pressure_pct)):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise ValueError(f"{name} must be integer percentage")

        reused = 0
        if (
            request.prefix_cached
            and request.prefix_tokens
            and self.policy.allows("prefix_affinity")
        ):
            reused = request.prefix_tokens
        prefill = request.prompt_tokens - reused

        phase_mode = "unified"
        if self.policy.allows("phase_disaggregation") and request.prompt_tokens >= 1024:
            phase_mode = "disaggregated"

        speculative = (
            request.draft_model_available
            and self.policy.allows("speculative_decoding")
            and request.output_tokens >= 8
        )

        class_boost = {
            ServiceClass.INTERACTIVE: 100,
            ServiceClass.STANDARD: 25,
            ServiceClass.THROUGHPUT: 0,
            ServiceClass.BACKGROUND: -25,
        }[request.service_class]
        degradation: list[str] = []

        if kv_pressure_pct >= 90:
            if speculative:
                speculative = False
                degradation.append("disable_speculative_under_kv_pressure")
            if phase_mode == "disaggregated":
                phase_mode = "unified"
                degradation.append("collapse_phase_disaggregation_under_kv_pressure")
        if queue_pressure_pct >= 90 and request.service_class is ServiceClass.BACKGROUND:
            class_boost -= 75
            degradation.append("deprioritize_background_under_queue_pressure")
        if queue_pressure_pct >= 95 and request.service_class is ServiceClass.INTERACTIVE:
            class_boost += 50
            degradation.append("protect_interactive_latency")

        body = {
            "schema": "skeleton.ai.serving-plan.v1",
            "request_id": request.request_id,
            "service_class": request.service_class.value,
            "prefill_tokens": prefill,
            "decode_tokens": request.output_tokens,
            "prefix_reused_tokens": reused,
            "phase_mode": phase_mode,
            "speculative": speculative,
            "priority_boost": class_boost,
            "degradation": degradation,
            "policy_digest": self.policy.digest,
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ServingPlan(
            request.request_id,
            request.service_class,
            prefill,
            request.output_tokens,
            reused,
            phase_mode,
            speculative,
            class_boost,
            tuple(degradation),
            self.policy.digest,
            digest,
        )


__all__ = ["PolicyAwareServingPlanner", "ServiceClass", "ServingPlan", "ServingRequest"]
