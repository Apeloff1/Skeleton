"""Deterministic error-budget evidence derived from typed SLO/SLI data.

Budget state is advisory evidence only. It cannot waive safety/reliability
checks, grant release authority, or mutate alerting/release configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json

from skeleton.observability.slo import SLI, SLO, assess_slo


_PPM = 1_000_000


class ErrorBudgetPolicyError(ValueError):
    """An error-budget evidence invariant failed."""


def _sha256(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ErrorBudgetPolicyError(f"{name} must be lowercase sha256")
    return value


def _nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ErrorBudgetPolicyError(f"{name} must be a non-negative integer")
    return value


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
        raise ErrorBudgetPolicyError(
            "error-budget evidence must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _allowed_bad_ppm(target: float) -> int:
    result = (
        (Decimal("1") - Decimal(str(target))) * Decimal(_PPM)
    ).to_integral_value(rounding=ROUND_FLOOR)
    return max(0, int(result))


def _observed_bad_ppm(*, bad_events: int, eligible_events: int) -> int:
    if eligible_events == 0:
        return 0
    return (bad_events * _PPM + eligible_events - 1) // eligible_events


@dataclass(frozen=True, slots=True)
class ErrorBudget:
    """Deterministic budget snapshot for one exact SLO/SLI pair."""

    slo_digest: str
    sli_digest: str
    eligible_events: int
    bad_events: int
    allowed_bad_ppm: int
    observed_bad_ppm: int
    remaining_bad_ppm: int
    exhausted: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "slo_digest", _sha256("slo_digest", self.slo_digest))
        object.__setattr__(self, "sli_digest", _sha256("sli_digest", self.sli_digest))
        for name in (
            "eligible_events",
            "bad_events",
            "allowed_bad_ppm",
            "observed_bad_ppm",
            "remaining_bad_ppm",
        ):
            object.__setattr__(
                self,
                name,
                _nonnegative_int(name, getattr(self, name)),
            )
        if self.bad_events > self.eligible_events:
            raise ErrorBudgetPolicyError("bad_events cannot exceed eligible_events")
        if self.allowed_bad_ppm > _PPM or self.observed_bad_ppm > _PPM:
            raise ErrorBudgetPolicyError("bad-event ppm must be within [0, 1000000]")
        expected_remaining = max(0, self.allowed_bad_ppm - self.observed_bad_ppm)
        if self.remaining_bad_ppm != expected_remaining:
            raise ErrorBudgetPolicyError("remaining budget does not match ppm evidence")
        expected_exhausted = self.observed_bad_ppm > self.allowed_bad_ppm
        if self.exhausted is not expected_exhausted:
            raise ErrorBudgetPolicyError("exhausted state does not match ppm evidence")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "slo_digest": self.slo_digest,
                "sli_digest": self.sli_digest,
                "eligible_events": self.eligible_events,
                "bad_events": self.bad_events,
                "allowed_bad_ppm": self.allowed_bad_ppm,
                "observed_bad_ppm": self.observed_bad_ppm,
                "remaining_bad_ppm": self.remaining_bad_ppm,
                "exhausted": self.exhausted,
            }
        )


@dataclass(frozen=True, slots=True)
class BurnRate:
    """Observed bad-event rate relative to the declared SLO allowance."""

    budget_digest: str
    burn_multiple_ppm: int | None
    unbounded: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "budget_digest",
            _sha256("budget_digest", self.budget_digest),
        )
        if self.burn_multiple_ppm is not None:
            object.__setattr__(
                self,
                "burn_multiple_ppm",
                _nonnegative_int("burn_multiple_ppm", self.burn_multiple_ppm),
            )
        if not isinstance(self.unbounded, bool):
            raise ErrorBudgetPolicyError("unbounded must be boolean")
        if self.unbounded != (self.burn_multiple_ppm is None):
            raise ErrorBudgetPolicyError(
                "unbounded burn must be represented by a null multiple"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "budget_digest": self.budget_digest,
                "burn_multiple_ppm": self.burn_multiple_ppm,
                "unbounded": self.unbounded,
            }
        )


@dataclass(frozen=True, slots=True)
class BudgetDecision:
    """Advisory evidence that cannot override independent gates."""

    budget_digest: str
    burn_rate_digest: str
    status: str
    blocking_reasons: tuple[str, ...]
    safety_gate_passed: bool
    reliability_gate_passed: bool
    budget_exhausted: bool
    safety_override: bool = False
    reliability_override: bool = False
    promotion_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "budget_digest",
            _sha256("budget_digest", self.budget_digest),
        )
        object.__setattr__(
            self,
            "burn_rate_digest",
            _sha256("burn_rate_digest", self.burn_rate_digest),
        )
        if self.status not in {"healthy", "exhausted", "blocked"}:
            raise ErrorBudgetPolicyError("unknown budget decision status")
        reasons = tuple(sorted(set(self.blocking_reasons)))
        if any(not isinstance(item, str) or not item for item in reasons):
            raise ErrorBudgetPolicyError(
                "blocking_reasons must contain non-empty strings"
            )
        object.__setattr__(self, "blocking_reasons", reasons)
        for name in (
            "safety_gate_passed",
            "reliability_gate_passed",
            "budget_exhausted",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ErrorBudgetPolicyError(f"{name} must be boolean")

        expected_reasons: list[str] = []
        if self.budget_exhausted:
            expected_reasons.append("error-budget-exhausted")
        if not self.safety_gate_passed:
            expected_reasons.append("safety-gate-failed")
        if not self.reliability_gate_passed:
            expected_reasons.append("reliability-gate-failed")
        if self.blocking_reasons != tuple(sorted(expected_reasons)):
            raise ErrorBudgetPolicyError(
                "blocking reasons do not match budget/gate evidence"
            )

        if not self.safety_gate_passed or not self.reliability_gate_passed:
            expected_status = "blocked"
        elif self.budget_exhausted:
            expected_status = "exhausted"
        else:
            expected_status = "healthy"
        if self.status != expected_status:
            raise ErrorBudgetPolicyError(
                "status does not match budget/gate evidence"
            )

        if self.safety_override is not False:
            raise ErrorBudgetPolicyError("error budget cannot override safety gate")
        if self.reliability_override is not False:
            raise ErrorBudgetPolicyError("error budget cannot override reliability gate")
        if self.promotion_authority is not False:
            raise ErrorBudgetPolicyError("error budget has no promotion authority")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "budget_digest": self.budget_digest,
                "burn_rate_digest": self.burn_rate_digest,
                "status": self.status,
                "blocking_reasons": list(self.blocking_reasons),
                "safety_gate_passed": self.safety_gate_passed,
                "reliability_gate_passed": self.reliability_gate_passed,
                "budget_exhausted": self.budget_exhausted,
                "safety_override": False,
                "reliability_override": False,
                "promotion_authority": False,
            }
        )


def calculate_error_budget(*, slo: SLO, sli: SLI) -> ErrorBudget:
    assessment = assess_slo(slo=slo, sli=sli)
    eligible = sli.eligible_events
    bad = eligible - sli.good_events
    allowed_ppm = _allowed_bad_ppm(slo.target)
    observed_ppm = _observed_bad_ppm(
        bad_events=bad,
        eligible_events=eligible,
    )
    return ErrorBudget(
        slo_digest=assessment.slo_digest,
        sli_digest=assessment.sli_digest,
        eligible_events=eligible,
        bad_events=bad,
        allowed_bad_ppm=allowed_ppm,
        observed_bad_ppm=observed_ppm,
        remaining_bad_ppm=max(0, allowed_ppm - observed_ppm),
        exhausted=observed_ppm > allowed_ppm,
    )


def calculate_burn_rate(budget: ErrorBudget) -> BurnRate:
    if not isinstance(budget, ErrorBudget):
        raise TypeError("budget must be ErrorBudget")
    if budget.allowed_bad_ppm == 0:
        if budget.observed_bad_ppm == 0:
            return BurnRate(
                budget_digest=budget.digest,
                burn_multiple_ppm=0,
                unbounded=False,
            )
        return BurnRate(
            budget_digest=budget.digest,
            burn_multiple_ppm=None,
            unbounded=True,
        )
    multiple = (
        budget.observed_bad_ppm * _PPM + budget.allowed_bad_ppm - 1
    ) // budget.allowed_bad_ppm
    return BurnRate(
        budget_digest=budget.digest,
        burn_multiple_ppm=multiple,
        unbounded=False,
    )


def evaluate_budget_decision(
    *,
    budget: ErrorBudget,
    burn_rate: BurnRate,
    safety_gate_passed: bool,
    reliability_gate_passed: bool,
) -> BudgetDecision:
    if not isinstance(budget, ErrorBudget):
        raise TypeError("budget must be ErrorBudget")
    if not isinstance(burn_rate, BurnRate):
        raise TypeError("burn_rate must be BurnRate")
    if burn_rate.budget_digest != budget.digest:
        raise ErrorBudgetPolicyError("burn rate belongs to a different budget")
    if not isinstance(safety_gate_passed, bool) or not isinstance(
        reliability_gate_passed, bool
    ):
        raise ErrorBudgetPolicyError("gate states must be boolean")

    reasons: list[str] = []
    if budget.exhausted:
        reasons.append("error-budget-exhausted")
    if not safety_gate_passed:
        reasons.append("safety-gate-failed")
    if not reliability_gate_passed:
        reasons.append("reliability-gate-failed")

    if not safety_gate_passed or not reliability_gate_passed:
        status = "blocked"
    elif budget.exhausted:
        status = "exhausted"
    else:
        status = "healthy"

    return BudgetDecision(
        budget_digest=budget.digest,
        burn_rate_digest=burn_rate.digest,
        status=status,
        blocking_reasons=tuple(reasons),
        safety_gate_passed=safety_gate_passed,
        reliability_gate_passed=reliability_gate_passed,
        budget_exhausted=budget.exhausted,
    )


__all__ = [
    "BudgetDecision",
    "BurnRate",
    "ErrorBudget",
    "ErrorBudgetPolicyError",
    "calculate_burn_rate",
    "calculate_error_budget",
    "evaluate_budget_decision",
]
