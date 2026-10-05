"""Service-level objectives, SLI evidence, and legacy tracker compatibility.

VOL-180 needs two surfaces:
* immutable SLO/SLI evidence used by exact error-budget policy; and
* the historical mutable SLOTracker API retained for existing callers.

The immutable contracts are authoritative only as evidence. They do not change
release, routing, alerting, or capacity state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Dict

from skeleton.kernel.errors import KernelError


class SLOError(KernelError):
    code = "OBS.SLO"


class SLOContractError(ValueError):
    """An immutable SLO/SLI evidence invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 256:
        raise SLOContractError(f"{name} must be non-empty normalized text")
    return value


def _ns(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SLOContractError(f"{name} must be a non-negative integer")
    return value


def _count(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SLOContractError(f"{name} must be a non-negative integer")
    return value


def _target(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SLOContractError("target must be a finite ratio in (0, 1]")
    result = float(value)
    if not math.isfinite(result) or not 0.0 < result <= 1.0:
        raise SLOContractError("target must be a finite ratio in (0, 1]")
    return result


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SLOContractError("SLO evidence must be canonical JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SLOWindow:
    window_id: str
    start_ns: int
    end_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _token("window_id", self.window_id))
        object.__setattr__(self, "start_ns", _ns("start_ns", self.start_ns))
        object.__setattr__(self, "end_ns", _ns("end_ns", self.end_ns))
        if self.end_ns <= self.start_ns:
            raise SLOContractError("SLO window end must be after start")

    @property
    def digest(self) -> str:
        return _digest({
            "window_id": self.window_id,
            "start_ns": self.start_ns,
            "end_ns": self.end_ns,
        })


@dataclass(frozen=True, slots=True)
class SLO:
    slo_id: str
    service_id: str
    sli_name: str
    target: float
    window: SLOWindow

    def __post_init__(self) -> None:
        for name in ("slo_id", "service_id", "sli_name"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(self, "target", _target(self.target))
        if not isinstance(self.window, SLOWindow):
            raise SLOContractError("window must be SLOWindow")

    @property
    def digest(self) -> str:
        return _digest({
            "slo_id": self.slo_id,
            "service_id": self.service_id,
            "sli_name": self.sli_name,
            "target": self.target,
            "window_digest": self.window.digest,
        })


@dataclass(frozen=True, slots=True)
class SLI:
    observation_id: str
    slo_id: str
    good_events: int
    total_events: int
    excluded_events: int
    observed_start_ns: int
    observed_end_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", _token("observation_id", self.observation_id))
        object.__setattr__(self, "slo_id", _token("slo_id", self.slo_id))
        for name in ("good_events", "total_events", "excluded_events"):
            object.__setattr__(self, name, _count(name, getattr(self, name)))
        object.__setattr__(self, "observed_start_ns", _ns("observed_start_ns", self.observed_start_ns))
        object.__setattr__(self, "observed_end_ns", _ns("observed_end_ns", self.observed_end_ns))
        if self.observed_end_ns < self.observed_start_ns:
            raise SLOContractError("SLI observation end cannot predate start")
        if self.excluded_events > self.total_events:
            raise SLOContractError("excluded_events cannot exceed total_events")
        if self.good_events > self.eligible_events:
            raise SLOContractError("good_events cannot exceed eligible events")

    @property
    def eligible_events(self) -> int:
        return self.total_events - self.excluded_events

    @property
    def observed_ratio(self) -> float:
        if self.eligible_events == 0:
            return 1.0
        return self.good_events / self.eligible_events

    @property
    def digest(self) -> str:
        return _digest({
            "observation_id": self.observation_id,
            "slo_id": self.slo_id,
            "good_events": self.good_events,
            "total_events": self.total_events,
            "excluded_events": self.excluded_events,
            "observed_start_ns": self.observed_start_ns,
            "observed_end_ns": self.observed_end_ns,
        })


@dataclass(frozen=True, slots=True)
class SLOAssessment:
    slo_digest: str
    sli_digest: str
    eligible_events: int
    observed_ratio: float
    target_met: bool
    excluded_events: int

    def __post_init__(self) -> None:
        for name in ("slo_digest", "sli_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
                raise SLOContractError(f"{name} must be lowercase sha256")
        object.__setattr__(self, "eligible_events", _count("eligible_events", self.eligible_events))
        object.__setattr__(self, "excluded_events", _count("excluded_events", self.excluded_events))
        if isinstance(self.observed_ratio, bool) or not isinstance(self.observed_ratio, (int, float)):
            raise SLOContractError("observed_ratio must be finite within [0, 1]")
        ratio = float(self.observed_ratio)
        if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
            raise SLOContractError("observed_ratio must be finite within [0, 1]")
        object.__setattr__(self, "observed_ratio", ratio)
        if not isinstance(self.target_met, bool):
            raise SLOContractError("target_met must be boolean")

    @property
    def digest(self) -> str:
        return _digest({
            "slo_digest": self.slo_digest,
            "sli_digest": self.sli_digest,
            "eligible_events": self.eligible_events,
            "observed_ratio": self.observed_ratio,
            "target_met": self.target_met,
            "excluded_events": self.excluded_events,
        })


def assess_slo(*, slo: SLO, sli: SLI) -> SLOAssessment:
    if not isinstance(slo, SLO) or not isinstance(sli, SLI):
        raise TypeError("slo and sli must be typed SLO/SLI contracts")
    if sli.slo_id != slo.slo_id:
        raise SLOContractError("SLI must reference the exact SLO identity")
    if sli.observed_start_ns < slo.window.start_ns or sli.observed_end_ns > slo.window.end_ns:
        raise SLOContractError("SLI observation must remain inside the SLO window")
    ratio = sli.observed_ratio
    return SLOAssessment(
        slo_digest=slo.digest,
        sli_digest=sli.digest,
        eligible_events=sli.eligible_events,
        observed_ratio=ratio,
        target_met=ratio >= slo.target,
        excluded_events=sli.excluded_events,
    )


# ---------------------------------------------------------------------------
# Legacy mutable tracker API retained for compatibility.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServiceLevelObjective:
    name: str
    target: float
    window_s: float = 3600.0 * 24 * 30

    def allowed_error_ratio(self) -> float:
        return 1.0 - self.target


@dataclass
class ErrorBudget:
    total_events: int = 0
    bad_events: int = 0

    @property
    def observed_ratio(self) -> float:
        if self.total_events == 0:
            return 1.0
        return 1.0 - (self.bad_events / self.total_events)


class SLOTracker:
    """Registers legacy SLOs and records outcomes per SLO."""

    def __init__(self) -> None:
        self._slos: Dict[str, ServiceLevelObjective] = {}
        self._budgets: Dict[str, ErrorBudget] = {}

    def register(self, slo: ServiceLevelObjective) -> None:
        self._slos[slo.name] = slo
        self._budgets[slo.name] = ErrorBudget()

    def record(self, slo_name: str, *, bad: bool) -> None:
        if slo_name not in self._slos:
            raise SLOError("unknown SLO", context={"slo": slo_name})
        budget = self._budgets[slo_name]
        budget.total_events += 1
        if bad:
            budget.bad_events += 1

    def remaining(self, slo_name: str) -> float:
        slo = self._slos.get(slo_name)
        budget = self._budgets.get(slo_name)
        if slo is None or budget is None:
            raise SLOError("unknown SLO", context={"slo": slo_name})
        allowed = slo.allowed_error_ratio()
        if budget.total_events == 0:
            return allowed
        bad_ratio = budget.bad_events / budget.total_events
        return max(0.0, allowed - bad_ratio)

    def burn_rate(self, slo_name: str) -> float:
        budget = self._budgets.get(slo_name)
        if budget is None or budget.total_events == 0:
            return 0.0
        return budget.bad_events / budget.total_events

    def status(self) -> Dict[str, float]:
        return {name: self.remaining(name) for name in self._slos}


__all__ = [
    "ErrorBudget",
    "SLI",
    "SLO",
    "SLOAssessment",
    "SLOContractError",
    "SLOError",
    "SLOTracker",
    "SLOWindow",
    "ServiceLevelObjective",
    "assess_slo",
]
