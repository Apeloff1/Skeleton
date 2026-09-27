"""SLO-driven canary promotion and rollback with immutable decision evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
import time
from typing import Any, Callable

from skeleton.deployment.canary import CanaryController, Rollout
from skeleton.observability.slo import ServiceLevelObjective, SLOTracker


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class ReleaseSLOError(RuntimeError):
    """Release SLO promotion contract was violated."""


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ReleaseSLOPolicy:
    availability_target: float = 0.99
    max_error_rate: float = 0.05
    max_latency_regression: float = 1.5
    minimum_quality_score: float = 0.8
    minimum_samples: int = 100
    stages: tuple[int, ...] = (1, 10, 25, 50, 100)

    def __post_init__(self) -> None:
        for name, value in (
            ("availability_target", self.availability_target),
            ("max_error_rate", self.max_error_rate),
            ("minimum_quality_score", self.minimum_quality_score),
        ):
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if not 0.0 < self.availability_target <= 1.0:
            raise ValueError("availability_target must be in (0, 1]")
        if not 0.0 <= self.max_error_rate < 1.0:
            raise ValueError("max_error_rate must be in [0, 1)")
        if self.max_latency_regression < 1.0:
            raise ValueError("max_latency_regression must be at least 1")
        if not 0.0 <= self.minimum_quality_score <= 1.0:
            raise ValueError("minimum_quality_score must be in [0, 1]")
        if self.minimum_samples <= 0:
            raise ValueError("minimum_samples must be positive")
        if (
            not self.stages
            or tuple(sorted(set(self.stages))) != self.stages
            or self.stages[-1] != 100
            or self.stages[0] <= 0
        ):
            raise ValueError(
                "stages must be unique increasing percentages ending at 100"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "availability_target": self.availability_target,
            "max_error_rate": self.max_error_rate,
            "max_latency_regression": self.max_latency_regression,
            "minimum_quality_score": self.minimum_quality_score,
            "minimum_samples": self.minimum_samples,
            "stages": list(self.stages),
        }


@dataclass(frozen=True, slots=True)
class ReleaseDecisionReceipt:
    release_id: str
    rollout_id: str
    action: str
    stage_pct: int
    error_rate: float
    p99_latency_ms: float
    quality_score: float
    samples: int
    source_evidence_digest: str
    policy_digest: str
    slo_remaining: float
    reason: str
    observed_at: float
    operator_id: str = ""

    def __post_init__(self) -> None:
        if self.action not in {"held", "advanced", "promoted", "rolled_back"}:
            raise ValueError("unsupported release action")
        if not self.release_id or len(self.release_id) > 160:
            raise ValueError("invalid release_id")
        if not self.rollout_id or len(self.rollout_id) > 160:
            raise ValueError("invalid rollout_id")
        if not _DIGEST_RE.fullmatch(self.source_evidence_digest):
            raise ValueError("source_evidence_digest must be SHA-256 hex")
        if not _DIGEST_RE.fullmatch(self.policy_digest):
            raise ValueError("policy_digest must be SHA-256 hex")
        if not self.reason or len(self.reason) > 512:
            raise ValueError("release decision requires a bounded reason")
        if self.operator_id and len(self.operator_id) > 256:
            raise ValueError("operator_id is too long")

    def to_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "rollout_id": self.rollout_id,
            "action": self.action,
            "stage_pct": self.stage_pct,
            "error_rate": self.error_rate,
            "p99_latency_ms": self.p99_latency_ms,
            "quality_score": self.quality_score,
            "samples": self.samples,
            "source_evidence_digest": self.source_evidence_digest,
            "policy_digest": self.policy_digest,
            "slo_remaining": self.slo_remaining,
            "reason": self.reason,
            "observed_at": self.observed_at,
            "operator_id": self.operator_id,
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


@dataclass(slots=True)
class _ReleaseState:
    rollout: Rollout
    evidence_digest: str
    last_receipt: ReleaseDecisionReceipt | None = None


class ReleaseSLOLoop:
    """Consume canary observations and produce promotion/rollback evidence."""

    slo_name = "release-canary-health"

    def __init__(
        self,
        policy: ReleaseSLOPolicy | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or ReleaseSLOPolicy()
        self._clock = clock
        self.canary = CanaryController(
            max_error_rate=self.policy.max_error_rate,
            max_latency_regression=self.policy.max_latency_regression,
        )
        self.slo = SLOTracker()
        self.slo.register(
            ServiceLevelObjective(
                self.slo_name,
                target=self.policy.availability_target,
            )
        )
        self._states: dict[str, _ReleaseState] = {}
        self._history: list[ReleaseDecisionReceipt] = []
        self._policy_digest = _digest(self.policy.to_dict())

    def start(
        self,
        release_id: str,
        *,
        service: str,
        from_version: str,
        to_version: str,
        source_evidence_digest: str,
        baseline_latency_ms: float,
    ) -> Rollout:
        if release_id in self._states:
            raise ReleaseSLOError("release rollout already exists")
        if not _DIGEST_RE.fullmatch(source_evidence_digest):
            raise ReleaseSLOError(
                "release rollout requires a SHA-256 evidence digest"
            )
        if baseline_latency_ms <= 0 or not math.isfinite(
            float(baseline_latency_ms)
        ):
            raise ReleaseSLOError("baseline latency must be positive and finite")
        rollout = self.canary.start(
            service,
            from_version,
            to_version,
            stages=list(self.policy.stages),
            baseline_latency_ms=float(baseline_latency_ms),
        )
        self._states[release_id] = _ReleaseState(
            rollout=rollout,
            evidence_digest=source_evidence_digest,
        )
        return rollout

    def observe(
        self,
        release_id: str,
        *,
        error_rate: float,
        p99_latency_ms: float,
        quality_score: float,
        samples: int,
    ) -> ReleaseDecisionReceipt:
        state = self._state(release_id)
        rollout = state.rollout
        if rollout.status not in {"in_progress", "paused"}:
            raise ReleaseSLOError("release rollout is already terminal")
        if rollout.status == "paused":
            raise ReleaseSLOError("release rollout is paused")
        self._validate_observation(
            error_rate=error_rate,
            p99_latency_ms=p99_latency_ms,
            quality_score=quality_score,
            samples=samples,
        )

        stage_pct = rollout.current_pct
        if samples < self.policy.minimum_samples:
            receipt = self._receipt(
                release_id,
                state,
                action="held",
                stage_pct=stage_pct,
                error_rate=error_rate,
                p99_latency_ms=p99_latency_ms,
                quality_score=quality_score,
                samples=samples,
                bad=False,
                reason="insufficient canary samples",
            )
            return receipt

        if quality_score < self.policy.minimum_quality_score:
            self.canary.rollback(rollout.rollout_id)
            receipt = self._receipt(
                release_id,
                state,
                action="rolled_back",
                stage_pct=stage_pct,
                error_rate=error_rate,
                p99_latency_ms=p99_latency_ms,
                quality_score=quality_score,
                samples=samples,
                bad=True,
                reason="provider quality score below release threshold",
            )
            return receipt

        result = self.canary.observe(
            rollout.rollout_id,
            error_rate,
            p99_latency_ms,
            samples=samples,
        )
        action = str(result["action"])
        bad = action == "rolled_back"
        if action == "rolled_back":
            reason = "canary error or latency SLO breached"
        elif action == "advanced":
            reason = "canary SLO healthy; advanced rollout stage"
        elif action == "promoted":
            reason = "all canary stages satisfied release SLO"
        else:  # pragma: no cover - CanaryController contract guard
            raise ReleaseSLOError(f"unexpected canary action: {action}")
        return self._receipt(
            release_id,
            state,
            action=action,
            stage_pct=stage_pct,
            error_rate=error_rate,
            p99_latency_ms=p99_latency_ms,
            quality_score=quality_score,
            samples=samples,
            bad=bad,
            reason=reason,
        )

    def operator_override(
        self,
        release_id: str,
        *,
        action: str,
        operator_id: str,
        reason: str,
    ) -> ReleaseDecisionReceipt:
        state = self._state(release_id)
        rollout = state.rollout
        if action not in {"hold", "rollback"}:
            raise ReleaseSLOError(
                "operator override may only hold or rollback; "
                "it cannot force promotion"
            )
        if not operator_id or len(operator_id) > 256:
            raise ReleaseSLOError("operator_id is required")
        if not reason or len(reason) > 512:
            raise ReleaseSLOError("operator override requires a bounded reason")
        if rollout.status in {"promoted", "rolled_back"}:
            raise ReleaseSLOError("release rollout is already terminal")

        latest = rollout.metrics[-1] if rollout.metrics else None
        error_rate = 0.0 if latest is None else latest.error_rate
        p99 = 0.0 if latest is None else latest.p99_latency_ms
        samples = 0 if latest is None else latest.samples
        quality = (
            self.policy.minimum_quality_score
            if state.last_receipt is None
            else state.last_receipt.quality_score
        )
        stage_pct = rollout.current_pct

        if action == "rollback":
            self.canary.rollback(rollout.rollout_id)
            receipt_action = "rolled_back"
            bad = True
        else:
            self.canary.pause(rollout.rollout_id)
            receipt_action = "held"
            bad = False

        return self._receipt(
            release_id,
            state,
            action=receipt_action,
            stage_pct=stage_pct,
            error_rate=error_rate,
            p99_latency_ms=p99,
            quality_score=quality,
            samples=samples,
            bad=bad,
            reason=f"operator override: {reason}",
            operator_id=operator_id,
        )

    def history(
        self,
        release_id: str | None = None,
    ) -> tuple[ReleaseDecisionReceipt, ...]:
        if release_id is None:
            return tuple(self._history)
        return tuple(
            item for item in self._history if item.release_id == release_id
        )

    def _state(self, release_id: str) -> _ReleaseState:
        try:
            return self._states[release_id]
        except KeyError as exc:
            raise ReleaseSLOError("unknown release rollout") from exc

    @staticmethod
    def _validate_observation(
        *,
        error_rate: float,
        p99_latency_ms: float,
        quality_score: float,
        samples: int,
    ) -> None:
        if (
            isinstance(error_rate, bool)
            or not math.isfinite(float(error_rate))
            or not 0.0 <= error_rate <= 1.0
        ):
            raise ReleaseSLOError("error_rate must be in [0, 1]")
        if (
            isinstance(p99_latency_ms, bool)
            or not math.isfinite(float(p99_latency_ms))
            or p99_latency_ms < 0
        ):
            raise ReleaseSLOError(
                "p99_latency_ms must be finite and non-negative"
            )
        if (
            isinstance(quality_score, bool)
            or not math.isfinite(float(quality_score))
            or not 0.0 <= quality_score <= 1.0
        ):
            raise ReleaseSLOError("quality_score must be in [0, 1]")
        if isinstance(samples, bool) or not isinstance(samples, int) or samples < 0:
            raise ReleaseSLOError("samples must be a non-negative integer")

    def _receipt(
        self,
        release_id: str,
        state: _ReleaseState,
        *,
        action: str,
        stage_pct: int,
        error_rate: float,
        p99_latency_ms: float,
        quality_score: float,
        samples: int,
        bad: bool,
        reason: str,
        operator_id: str = "",
    ) -> ReleaseDecisionReceipt:
        self.slo.record(self.slo_name, bad=bad)
        receipt = ReleaseDecisionReceipt(
            release_id=release_id,
            rollout_id=state.rollout.rollout_id,
            action=action,
            stage_pct=stage_pct,
            error_rate=float(error_rate),
            p99_latency_ms=float(p99_latency_ms),
            quality_score=float(quality_score),
            samples=samples,
            source_evidence_digest=state.evidence_digest,
            policy_digest=self._policy_digest,
            slo_remaining=self.slo.remaining(self.slo_name),
            reason=reason,
            observed_at=float(self._clock()),
            operator_id=operator_id,
        )
        state.last_receipt = receipt
        self._history.append(receipt)
        return receipt


__all__ = [
    "ReleaseDecisionReceipt",
    "ReleaseSLOError",
    "ReleaseSLOLoop",
    "ReleaseSLOPolicy",
]
