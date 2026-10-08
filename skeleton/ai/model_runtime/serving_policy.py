"""Policy-aware serving planner for local transformer inference."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from .runtime_policy import RuntimePolicy
from .flgb_model_runtime import MAX_TOKENS, require_id


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
        try:
            require_id(self.request_id, "serving request_id")
            self.request_id.encode("utf-8", errors="strict")
        except (ValueError, UnicodeError) as exc:
            raise ValueError("invalid serving request_id") from exc
        if not isinstance(self.service_class, ServiceClass):
            raise ValueError("ServiceClass required")
        for name in ("prompt_tokens", "output_tokens", "prefix_tokens"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= MAX_TOKENS:
                raise ValueError(f"invalid {name}")
        if not 0 < self.prompt_tokens + self.output_tokens <= MAX_TOKENS:
            raise ValueError("serving request token budget out of bounds")
        if self.prefix_tokens > self.prompt_tokens:
            raise ValueError("prefix exceeds prompt")
        for name in ("prefix_cached", "draft_model_available"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"boolean {name} required")


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
        if not isinstance(request, ServingRequest):
            raise ValueError("ServingRequest required")
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
            "schema": "skeleton.ai.serving-plan.v2",
            "request_id": request.request_id,
            "service_class": request.service_class.value,
            "inputs": {
                "prompt_tokens": request.prompt_tokens,
                "output_tokens": request.output_tokens,
                "prefix_tokens": request.prefix_tokens,
                "prefix_cached": request.prefix_cached,
                "draft_model_available": request.draft_model_available,
                "kv_pressure_pct": kv_pressure_pct,
                "queue_pressure_pct": queue_pressure_pct,
            },
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
