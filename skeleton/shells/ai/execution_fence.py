"""Distributed fenced ownership for one reviewed AI shell execution.

The ordinary execution seal proves that a principal may execute an exact plan.
It does not by itself prove that only one worker in a distributed fleet is
currently entitled to cross the process-creation boundary.  This module binds a
short-lived monotonic fencing lease to the reviewed plan and its runtime trust
surface.

There is deliberately no background renewal thread.  The lease lifetime must
cover the deterministic worst-case wall-time budget of the plan before
execution starts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Final

from skeleton.shells.ai.distributed_state import FencedLease
from skeleton.shells.ai.store_protocol import FencedLeaseBackend
from skeleton.shells.execution_plan import ExecutionPlan


_MAX_ID: Final[int] = 256


def _digest(name: str, value: str, *, optional: bool = False) -> str:
    if optional and not value:
        return ""
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Digest values are opaque 64-character authority tokens; production

    # hashes are hexadecimal, while deterministic test/adapter sentinels may

    # use the full string alphabet.
    return value.lower()


@dataclass(frozen=True)
class AIExecutionFencePolicy:
    """Bound deterministic lease duration without implicit authority widening."""

    default_step_timeout_seconds: float = 10.0
    per_step_overhead_seconds: float = 0.25
    safety_margin_seconds: float = 2.0
    minimum_ttl_seconds: float = 3.0
    maximum_ttl_seconds: float = 3600.0
    max_plan_steps: int = 1024

    def __post_init__(self) -> None:
        for name in (
            "default_step_timeout_seconds",
            "per_step_overhead_seconds",
            "safety_margin_seconds",
            "minimum_ttl_seconds",
            "maximum_ttl_seconds",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
            object.__setattr__(self, name, float(value))
        if self.default_step_timeout_seconds <= 0.0:
            raise ValueError("default_step_timeout_seconds must be positive")
        if self.minimum_ttl_seconds <= 0.0:
            raise ValueError("minimum_ttl_seconds must be positive")
        if self.maximum_ttl_seconds < self.minimum_ttl_seconds:
            raise ValueError("maximum_ttl_seconds below minimum")
        if (
            isinstance(self.max_plan_steps, bool)
            or not isinstance(self.max_plan_steps, int)
            or self.max_plan_steps <= 0
        ):
            raise ValueError("max_plan_steps must be positive")

    def to_dict(self) -> dict[str, object]:
        return {
            "default_step_timeout_seconds": self.default_step_timeout_seconds,
            "per_step_overhead_seconds": self.per_step_overhead_seconds,
            "safety_margin_seconds": self.safety_margin_seconds,
            "minimum_ttl_seconds": self.minimum_ttl_seconds,
            "maximum_ttl_seconds": self.maximum_ttl_seconds,
            "max_plan_steps": self.max_plan_steps,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def required_window(self, plan: ExecutionPlan) -> float:
        if not isinstance(plan, ExecutionPlan):
            raise TypeError("plan must be ExecutionPlan")
        if len(plan.steps) > self.max_plan_steps:
            raise ValueError("execution fence plan step bound exceeded")
        total = self.safety_margin_seconds
        for step in plan.steps:
            timeout = step.command.timeout
            if timeout is None:
                timeout = self.default_step_timeout_seconds
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(float(timeout))
                or float(timeout) <= 0.0
            ):
                raise ValueError(
                    f"plan step {step.step_id!r} has invalid timeout"
                )
            total += float(timeout) + self.per_step_overhead_seconds
        total = max(total, self.minimum_ttl_seconds)
        if total > self.maximum_ttl_seconds:
            raise ValueError(
                "plan worst-case wall-time exceeds execution fence maximum"
            )
        return total


@dataclass(frozen=True)
class AIExecutionFenceBinding:
    schema_version: int
    session_id: str
    principal: str
    worker_id: str
    plan_fingerprint: str
    runtime_trust_digest: str = ""
    release_evidence_digest: str = ""
    required_window_seconds: float = 0.0
    policy_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported AI execution fence schema")
        for name in ("session_id", "principal", "worker_id"):
            value = getattr(self, name)
            if not value or len(value) > _MAX_ID:
                raise ValueError(f"invalid execution fence {name}")
        object.__setattr__(
            self,
            "plan_fingerprint",
            _digest("plan_fingerprint", self.plan_fingerprint),
        )
        object.__setattr__(
            self,
            "runtime_trust_digest",
            _digest(
                "runtime_trust_digest",
                self.runtime_trust_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "release_evidence_digest",
            _digest(
                "release_evidence_digest",
                self.release_evidence_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "policy_digest",
            _digest("policy_digest", self.policy_digest),
        )
        if (
            isinstance(self.required_window_seconds, bool)
            or not isinstance(self.required_window_seconds, (int, float))
            or not math.isfinite(float(self.required_window_seconds))
            or float(self.required_window_seconds) <= 0.0
        ):
            raise ValueError(
                "execution fence required_window_seconds must be positive"
            )
        object.__setattr__(
            self,
            "required_window_seconds",
            float(self.required_window_seconds),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "principal": self.principal,
            "worker_id": self.worker_id,
            "plan_fingerprint": self.plan_fingerprint,
            "runtime_trust_digest": self.runtime_trust_digest,
            "release_evidence_digest": self.release_evidence_digest,
            "required_window_seconds": self.required_window_seconds,
            "policy_digest": self.policy_digest,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AIExecutionFence:
    binding: AIExecutionFenceBinding
    lease: FencedLease

    def __post_init__(self) -> None:
        if not isinstance(self.binding, AIExecutionFenceBinding):
            raise ValueError("binding must be AIExecutionFenceBinding")
        if not isinstance(self.lease, FencedLease):
            raise ValueError("lease must be FencedLease")

    def to_dict(self) -> dict[str, object]:
        return {
            "binding": self.binding.to_dict(),
            "binding_digest": self.binding.digest,
            "lease": self.lease.to_dict(),
            "fence_digest": self.digest,
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            {
                "binding_digest": self.binding.digest,
                "lease": self.lease.to_dict(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


class AIExecutionFenceError(RuntimeError):
    pass


class AIExecutionFenceManager:
    """Acquire and verify one monotonic distributed owner for an exact plan."""

    def __init__(
        self,
        backend: FencedLeaseBackend,
        *,
        namespace: str = "shell-ai-execution-fence",
        policy: AIExecutionFencePolicy | None = None,
    ) -> None:
        if not isinstance(backend, FencedLeaseBackend):
            raise TypeError("backend must satisfy FencedLeaseBackend")
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid execution fence namespace")
        self.backend = backend
        self.namespace = namespace
        self.policy = policy or AIExecutionFencePolicy()

    @staticmethod
    def _resource_key(
        session_id: str,
        plan_fingerprint: str,
    ) -> str:
        raw = json.dumps(
            {
                "session_id": session_id,
                "plan_fingerprint": plan_fingerprint,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return "exec:" + hashlib.sha256(raw).hexdigest()

    def binding(
        self,
        plan: ExecutionPlan,
        *,
        session_id: str,
        principal: str,
        worker_id: str,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
    ) -> AIExecutionFenceBinding:
        return AIExecutionFenceBinding(
            1,
            session_id,
            principal,
            worker_id,
            plan.fingerprint,
            runtime_trust_digest,
            release_evidence_digest,
            self.policy.required_window(plan),
            self.policy.digest,
        )

    def acquire(
        self,
        plan: ExecutionPlan,
        *,
        session_id: str,
        principal: str,
        worker_id: str,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
        ttl_seconds: float | None = None,
    ) -> AIExecutionFence:
        binding = self.binding(
            plan,
            session_id=session_id,
            principal=principal,
            worker_id=worker_id,
            runtime_trust_digest=runtime_trust_digest,
            release_evidence_digest=release_evidence_digest,
        )
        ttl = (
            binding.required_window_seconds
            if ttl_seconds is None
            else ttl_seconds
        )
        if (
            isinstance(ttl, bool)
            or not isinstance(ttl, (int, float))
            or not math.isfinite(float(ttl))
            or float(ttl) <= 0.0
        ):
            raise ValueError("execution fence ttl_seconds must be positive")
        ttl = float(ttl)
        if ttl < binding.required_window_seconds:
            raise AIExecutionFenceError(
                "execution fence TTL does not cover plan wall-time budget"
            )
        if ttl > self.policy.maximum_ttl_seconds:
            raise AIExecutionFenceError(
                "execution fence TTL exceeds configured maximum"
            )
        key = self._resource_key(
            binding.session_id,
            binding.plan_fingerprint,
        )
        lease = self.backend.acquire_lease(
            self.namespace,
            key,
            owner=worker_id,
            ttl_seconds=ttl,
        )
        return AIExecutionFence(binding, lease)

    def require(
        self,
        fence: AIExecutionFence,
        plan: ExecutionPlan,
        *,
        session_id: str,
        principal: str,
        worker_id: str,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
    ) -> AIExecutionFence:
        if not isinstance(fence, AIExecutionFence):
            raise AIExecutionFenceError("execution fence is required")
        expected = self.binding(
            plan,
            session_id=session_id,
            principal=principal,
            worker_id=worker_id,
            runtime_trust_digest=runtime_trust_digest,
            release_evidence_digest=release_evidence_digest,
        )
        if fence.binding != expected:
            raise AIExecutionFenceError(
                "execution fence binding differs from current authority surface"
            )
        expected_key = self._resource_key(
            session_id,
            plan.fingerprint,
        )
        if fence.lease.namespace != self.namespace:
            raise AIExecutionFenceError("execution fence namespace mismatch")
        if fence.lease.key != expected_key:
            raise AIExecutionFenceError("execution fence resource mismatch")
        if fence.lease.owner != worker_id:
            raise AIExecutionFenceError("execution fence owner mismatch")
        try:
            self.backend.require_fence(fence.lease)
        except Exception as exc:
            raise AIExecutionFenceError(
                "execution fence is stale, expired, or superseded"
            ) from exc
        return fence

    def renew(
        self,
        fence: AIExecutionFence,
        plan: ExecutionPlan,
        *,
        ttl_seconds: float,
    ) -> AIExecutionFence:
        required = self.policy.required_window(plan)
        if ttl_seconds < required:
            raise AIExecutionFenceError(
                "renewed execution fence TTL does not cover plan budget"
            )
        if ttl_seconds > self.policy.maximum_ttl_seconds:
            raise AIExecutionFenceError(
                "renewed execution fence TTL exceeds maximum"
            )
        try:
            lease = self.backend.renew_lease(
                fence.lease,
                ttl_seconds=ttl_seconds,
            )
        except Exception as exc:
            raise AIExecutionFenceError(
                "execution fence renewal failed"
            ) from exc
        return AIExecutionFence(fence.binding, lease)

    def release(self, fence: AIExecutionFence) -> bool:
        try:
            return self.backend.release_lease(fence.lease)
        except Exception as exc:
            raise AIExecutionFenceError(
                "execution fence release failed"
            ) from exc
