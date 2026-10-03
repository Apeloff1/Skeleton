"""SLO definitions and error-budget tracking for observability.

Alerts fire on thresholds; SLOs frame the acceptable ratio of bad to
good outcomes over a window. Track remaining budget and burn rate.

- :class:`ServiceLevelObjective` — name, target ratio, window
- :class:`ErrorBudget` — total, used, remaining, burn rate
- :class:`SLOTracker` — per-SLO accounting
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Tuple

from skeleton.kernel.errors import KernelError


class SLOError(KernelError):
    code = "OBS.SLO"


@dataclass(frozen=True)
class ServiceLevelObjective:
    name: str
    target: float  # e.g. 0.999
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
    """Registers SLOs and records outcomes per SLO."""

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
        """Bad events per event averaged — everything > 0 burns budget."""
        budget = self._budgets.get(slo_name)
        if budget is None or budget.total_events == 0:
            return 0.0
        return budget.bad_events / budget.total_events

    def status(self) -> Dict[str, float]:
        return {name: self.remaining(name) for name in self._slos}


def _slo_token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SLOError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise SLOError(f"{name} exceeds maximum length")
    return value


def _slo_ratio(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SLOError(f"{name} must be a finite ratio")
    result = float(value)
    if not math.isfinite(result) or result < 0.0 or result > 1.0:
        raise SLOError(f"{name} must be within [0, 1]")
    return result


def _slo_nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SLOError(f"{name} must be a non-negative integer")
    return value


def _slo_tokens(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SLOError(f"{name} must be a collection")
    return tuple(sorted({_slo_token(name, value) for value in values}))


def _slo_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SLOError("SLO evidence must be canonical JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SLOWindow:
    """Explicit SLO measurement window and declared exclusions."""

    window_id: str
    start_ns: int
    end_ns: int
    excluded_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "window_id", _slo_token("window_id", self.window_id))
        object.__setattr__(self, "start_ns", _slo_nonnegative_int("start_ns", self.start_ns))
        object.__setattr__(self, "end_ns", _slo_nonnegative_int("end_ns", self.end_ns))
        if self.end_ns <= self.start_ns:
            raise SLOError("SLO window end must be after start")
        object.__setattr__(
            self,
            "excluded_conditions",
            _slo_tokens("excluded_condition", self.excluded_conditions),
        )

    @property
    def digest(self) -> str:
        return _slo_digest(
            {
                "window_id": self.window_id,
                "start_ns": self.start_ns,
                "end_ns": self.end_ns,
                "excluded_conditions": list(self.excluded_conditions),
            }
        )


@dataclass(frozen=True, slots=True)
class SLO:
    """Typed service-level objective bound to one exact measurement window."""

    slo_id: str
    service_id: str
    sli_name: str
    target: float
    window: SLOWindow

    def __post_init__(self) -> None:
        object.__setattr__(self, "slo_id", _slo_token("slo_id", self.slo_id))
        object.__setattr__(self, "service_id", _slo_token("service_id", self.service_id))
        object.__setattr__(self, "sli_name", _slo_token("sli_name", self.sli_name))
        object.__setattr__(self, "target", _slo_ratio("target", self.target))
        if not isinstance(self.window, SLOWindow):
            raise SLOError("window must be SLOWindow")

    @property
    def digest(self) -> str:
        return _slo_digest(
            {
                "slo_id": self.slo_id,
                "service_id": self.service_id,
                "sli_name": self.sli_name,
                "target": self.target,
                "window_digest": self.window.digest,
            }
        )


@dataclass(frozen=True, slots=True)
class SLI:
    """Authoritative count-based SLI observation for one SLO."""

    observation_id: str
    slo_id: str
    good_events: int
    total_events: int
    observed_start_ns: int
    observed_end_ns: int
    excluded_events: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_id",
            _slo_token("observation_id", self.observation_id),
        )
        object.__setattr__(self, "slo_id", _slo_token("slo_id", self.slo_id))
        for name in (
            "good_events",
            "total_events",
            "observed_start_ns",
            "observed_end_ns",
            "excluded_events",
        ):
            object.__setattr__(
                self,
                name,
                _slo_nonnegative_int(name, getattr(self, name)),
            )
        if self.observed_end_ns <= self.observed_start_ns:
            raise SLOError("SLI observation end must be after start")
        if self.excluded_events > self.total_events:
            raise SLOError("excluded_events cannot exceed total_events")
        if self.good_events > self.eligible_events:
            raise SLOError("good_events cannot exceed eligible events")

    @property
    def eligible_events(self) -> int:
        return self.total_events - self.excluded_events

    @property
    def value(self) -> float:
        return 1.0 if self.eligible_events == 0 else self.good_events / self.eligible_events

    @property
    def digest(self) -> str:
        return _slo_digest(
            {
                "observation_id": self.observation_id,
                "slo_id": self.slo_id,
                "good_events": self.good_events,
                "total_events": self.total_events,
                "excluded_events": self.excluded_events,
                "observed_start_ns": self.observed_start_ns,
                "observed_end_ns": self.observed_end_ns,
            }
        )


@dataclass(frozen=True, slots=True)
class SLOAssessment:
    """Evidence-only assessment; it carries no alert or release authority."""

    slo_digest: str
    sli_digest: str
    value: float
    met: bool

    def __post_init__(self) -> None:
        for name in ("slo_digest", "sli_digest"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise SLOError(f"{name} must be lowercase sha256")
        object.__setattr__(self, "value", _slo_ratio("value", self.value))
        if not isinstance(self.met, bool):
            raise SLOError("met must be boolean")

    @property
    def digest(self) -> str:
        return _slo_digest(
            {
                "slo_digest": self.slo_digest,
                "sli_digest": self.sli_digest,
                "value": self.value,
                "met": self.met,
            }
        )


def assess_slo(*, slo: SLO, sli: SLI) -> SLOAssessment:
    """Assess one exact SLI observation against its declared SLO window."""

    if not isinstance(slo, SLO):
        raise TypeError("slo must be SLO")
    if not isinstance(sli, SLI):
        raise TypeError("sli must be SLI")
    if sli.slo_id != slo.slo_id:
        raise SLOError("SLI observation belongs to a different SLO")
    if (
        sli.observed_start_ns < slo.window.start_ns
        or sli.observed_end_ns > slo.window.end_ns
    ):
        raise SLOError(
            "SLI observation must be contained in declared SLO window"
        )
    value = sli.value
    return SLOAssessment(
        slo_digest=slo.digest,
        sli_digest=sli.digest,
        value=value,
        met=value >= slo.target,
    )
