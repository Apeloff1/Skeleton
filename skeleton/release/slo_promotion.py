"""Evidence-bound release SLO promotion and rollback control.

The controller consumes explicit observability signals and emits deterministic
promotion receipts. It never deploys directly: callers apply the returned
decision through the deployment plane. Missing or stale evidence fails closed.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from skeleton.kernel.errors import KernelError


SCHEMA_VERSION = 1
_MAX_TEXT = 512
_MAX_SIGNAL_AGE_SECONDS = 3600


class ReleasePromotionError(KernelError):
    code = "RELEASE.SLO_PROMOTION"
    http_status = 422


class ReleaseAction(str, Enum):
    HOLD = "hold"
    PROMOTE = "promote"
    ROLLBACK = "rollback"


def _text(name: str, value: object, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleasePromotionError(f"{name} must be non-empty text")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise ReleasePromotionError(f"{name} is not normalized")
    return normalized


def _finite(name: str, value: object, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReleasePromotionError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ReleasePromotionError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise ReleasePromotionError(f"{name} is below minimum")
    return number


def _unit(name: str, value: object) -> float:
    number = _finite(name, value, minimum=0.0)
    if number > 1.0:
        raise ReleasePromotionError(f"{name} must be between 0 and 1")
    return number


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReleasePromotionError(f"{name} must be a positive integer")
    return value


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ReleasePromotionError("release evidence must be canonical JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ReleaseSLOPolicy:
    min_samples: int = 500
    max_error_rate: float = 0.01
    max_p99_latency_ms: float = 1000.0
    min_provider_quality: float = 0.95
    max_signal_age_seconds: int = _MAX_SIGNAL_AGE_SECONDS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "min_samples",
            _positive_int("min_samples", self.min_samples),
        )
        object.__setattr__(
            self,
            "max_error_rate",
            _unit("max_error_rate", self.max_error_rate),
        )
        object.__setattr__(
            self,
            "max_p99_latency_ms",
            _finite(
                "max_p99_latency_ms",
                self.max_p99_latency_ms,
                minimum=0.001,
            ),
        )
        object.__setattr__(
            self,
            "min_provider_quality",
            _unit("min_provider_quality", self.min_provider_quality),
        )
        object.__setattr__(
            self,
            "max_signal_age_seconds",
            _positive_int(
                "max_signal_age_seconds",
                self.max_signal_age_seconds,
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "min_samples": self.min_samples,
            "max_error_rate": self.max_error_rate,
            "max_p99_latency_ms": self.max_p99_latency_ms,
            "min_provider_quality": self.min_provider_quality,
            "max_signal_age_seconds": self.max_signal_age_seconds,
        }


@dataclass(frozen=True, slots=True)
class CanarySLOSignal:
    release_id: str
    service: str
    from_version: str
    to_version: str
    stage_percent: int
    samples: int
    error_rate: float
    p99_latency_ms: float
    provider_quality: float
    observed_at: int
    source: str = "observability"

    def __post_init__(self) -> None:
        for name in ("release_id", "service", "from_version", "to_version"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.source != "observability":
            raise ReleasePromotionError(
                "release SLO signals must come from observability"
            )
        if (
            isinstance(self.stage_percent, bool)
            or not isinstance(self.stage_percent, int)
            or not 1 <= self.stage_percent <= 100
        ):
            raise ReleasePromotionError("stage_percent must be between 1 and 100")
        object.__setattr__(
            self,
            "samples",
            _positive_int("samples", self.samples),
        )
        object.__setattr__(
            self,
            "error_rate",
            _unit("error_rate", self.error_rate),
        )
        object.__setattr__(
            self,
            "p99_latency_ms",
            _finite("p99_latency_ms", self.p99_latency_ms, minimum=0.0),
        )
        object.__setattr__(
            self,
            "provider_quality",
            _unit("provider_quality", self.provider_quality),
        )
        if (
            isinstance(self.observed_at, bool)
            or not isinstance(self.observed_at, int)
            or self.observed_at < 0
        ):
            raise ReleasePromotionError(
                "observed_at must be a non-negative integer"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "release_id": self.release_id,
            "service": self.service,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "stage_percent": self.stage_percent,
            "samples": self.samples,
            "error_rate": self.error_rate,
            "p99_latency_ms": self.p99_latency_ms,
            "provider_quality": self.provider_quality,
            "observed_at": self.observed_at,
            "source": self.source,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class OperatorOverride:
    operator_id: str
    requested_action: ReleaseAction
    reason: str
    issued_at: int
    incident_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _text("operator_id", self.operator_id))
        object.__setattr__(self, "reason", _text("reason", self.reason))
        object.__setattr__(
            self,
            "incident_ref",
            _text("incident_ref", self.incident_ref),
        )
        if not isinstance(self.requested_action, ReleaseAction):
            raise ReleasePromotionError("requested_action must be ReleaseAction")
        if (
            isinstance(self.issued_at, bool)
            or not isinstance(self.issued_at, int)
            or self.issued_at < 0
        ):
            raise ReleasePromotionError("issued_at must be a non-negative integer")

    def as_dict(self) -> dict[str, object]:
        return {
            "operator_id": self.operator_id,
            "requested_action": self.requested_action.value,
            "reason": self.reason,
            "issued_at": self.issued_at,
            "incident_ref": self.incident_ref,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ReleaseDecisionReceipt:
    release_id: str
    action: ReleaseAction
    reasons: tuple[str, ...]
    evaluated_at: int
    policy_digest: str
    signal_digests: tuple[str, ...]
    override_digest: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "release_id", _text("release_id", self.release_id))
        if not isinstance(self.action, ReleaseAction):
            raise ReleasePromotionError("action must be ReleaseAction")
        if (
            isinstance(self.evaluated_at, bool)
            or not isinstance(self.evaluated_at, int)
            or self.evaluated_at < 0
        ):
            raise ReleasePromotionError(
                "evaluated_at must be a non-negative integer"
            )
        if self.schema_version != SCHEMA_VERSION:
            raise ReleasePromotionError("unsupported release decision schema")
        if not self.signal_digests:
            raise ReleasePromotionError("release decision requires signal evidence")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "release_id": self.release_id,
            "action": self.action.value,
            "reasons": list(self.reasons),
            "evaluated_at": self.evaluated_at,
            "policy_digest": self.policy_digest,
            "signal_digests": list(self.signal_digests),
            "override_digest": self.override_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


class ReleaseSLOPromotionController:
    """Evaluate canary observability and emit a deterministic release action."""

    def __init__(self, policy: ReleaseSLOPolicy | None = None) -> None:
        self.policy = policy or ReleaseSLOPolicy()

    def evaluate(
        self,
        signals: Sequence[CanarySLOSignal],
        *,
        evaluated_at: int,
        override: OperatorOverride | None = None,
    ) -> ReleaseDecisionReceipt:
        if not signals:
            raise ReleasePromotionError("at least one canary signal is required")
        if (
            isinstance(evaluated_at, bool)
            or not isinstance(evaluated_at, int)
            or evaluated_at < 0
        ):
            raise ReleasePromotionError(
                "evaluated_at must be a non-negative integer"
            )

        release_ids = {signal.release_id for signal in signals}
        services = {signal.service for signal in signals}
        versions = {
            (signal.from_version, signal.to_version)
            for signal in signals
        }
        if len(release_ids) != 1 or len(services) != 1 or len(versions) != 1:
            raise ReleasePromotionError(
                "all canary signals must describe one release"
            )

        ordered = tuple(
            sorted(
                signals,
                key=lambda signal: (
                    signal.stage_percent,
                    signal.observed_at,
                    signal.digest,
                ),
            )
        )
        reasons: list[str] = []
        total_samples = sum(signal.samples for signal in ordered)
        if total_samples < self.policy.min_samples:
            reasons.append("insufficient_samples")

        for signal in ordered:
            age = evaluated_at - signal.observed_at
            if age < 0 or age > self.policy.max_signal_age_seconds:
                reasons.append("stale_or_future_signal")
            if signal.error_rate > self.policy.max_error_rate:
                reasons.append("error_rate_exceeded")
            if signal.p99_latency_ms > self.policy.max_p99_latency_ms:
                reasons.append("latency_exceeded")
            if signal.provider_quality < self.policy.min_provider_quality:
                reasons.append("provider_quality_below_threshold")

        unique_reasons = tuple(sorted(set(reasons)))
        action = ReleaseAction.PROMOTE
        if unique_reasons:
            hard_failure = any(
                reason != "insufficient_samples"
                for reason in unique_reasons
            )
            action = ReleaseAction.ROLLBACK if hard_failure else ReleaseAction.HOLD

        override_digest: str | None = None
        if override is not None:
            if override.issued_at > evaluated_at:
                raise ReleasePromotionError("override cannot be issued in the future")
            override_digest = override.digest
            # Operators may conservatively hold or rollback a healthy release.
            # Promoting over failed evidence is intentionally forbidden.
            if override.requested_action is ReleaseAction.PROMOTE and action is not ReleaseAction.PROMOTE:
                raise ReleasePromotionError(
                    "operator override cannot promote failed SLO evidence"
                )
            action = override.requested_action
            unique_reasons = tuple(
                sorted(
                    set(
                        unique_reasons
                        + ("operator_override:" + override.incident_ref,)
                    )
                )
            )

        return ReleaseDecisionReceipt(
            release_id=ordered[0].release_id,
            action=action,
            reasons=unique_reasons,
            evaluated_at=evaluated_at,
            policy_digest=_digest(self.policy.as_dict()),
            signal_digests=tuple(signal.digest for signal in ordered),
            override_digest=override_digest,
        )


__all__ = [
    "CanarySLOSignal",
    "OperatorOverride",
    "ReleaseAction",
    "ReleaseDecisionReceipt",
    "ReleasePromotionError",
    "ReleaseSLOPolicy",
    "ReleaseSLOPromotionController",
]
