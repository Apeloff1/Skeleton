"""Evidence-gated accelerator selection.

No accelerator is selected because it exists. Selection requires reproducible
profile evidence, exact source identity, correctness, bounded failures, and a
declared fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Any


class AccelerationSelectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProfileEvidence:
    evidence_id: str
    candidate_id: str
    source_identity: str
    environment_id: str
    sample_count: int
    reference_median_ns: int
    candidate_median_ns: int
    correctness_passed: bool
    max_abs_error: float
    crash_count: int = 0
    timeout_count: int = 0

    def __post_init__(self) -> None:
        for name in ("evidence_id", "candidate_id", "source_identity", "environment_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
            if value != value.strip():
                raise ValueError(f"{name} must be canonical text")
        for name in (
            "sample_count",
            "reference_median_ns",
            "candidate_median_ns",
            "crash_count",
            "timeout_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.sample_count == 0:
            raise ValueError("sample_count must be positive")
        if self.reference_median_ns <= 0 or self.candidate_median_ns <= 0:
            raise ValueError("profile medians must be positive")
        if not isinstance(self.correctness_passed, bool):
            raise ValueError("correctness_passed must be boolean")
        if (
            isinstance(self.max_abs_error, bool)
            or not isinstance(self.max_abs_error, (int, float))
            or not math.isfinite(float(self.max_abs_error))
            or float(self.max_abs_error) < 0.0
        ):
            raise ValueError("max_abs_error must be finite and non-negative")

    @property
    def speedup(self) -> float:
        return self.reference_median_ns / self.candidate_median_ns


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    minimum_profile_runs: int = 2
    minimum_distinct_environment_ids: int = 1
    minimum_speedup: float = 1.20
    maximum_abs_error: float = 1e-5
    maximum_crashes: int = 0
    maximum_timeouts: int = 0

    def __post_init__(self) -> None:
        for name in (
            "minimum_profile_runs",
            "minimum_distinct_environment_ids",
            "maximum_crashes",
            "maximum_timeouts",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        for name in ("minimum_speedup", "maximum_abs_error"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
        if self.minimum_profile_runs < 1:
            raise ValueError("minimum_profile_runs must be positive")
        if self.minimum_distinct_environment_ids < 1:
            raise ValueError("minimum_distinct_environment_ids must be positive")
        if not math.isfinite(float(self.minimum_speedup)) or self.minimum_speedup <= 1.0:
            raise ValueError("minimum_speedup must be finite and > 1")
        if not math.isfinite(float(self.maximum_abs_error)) or self.maximum_abs_error < 0:
            raise ValueError("maximum_abs_error must be finite and non-negative")
        if self.maximum_crashes < 0 or self.maximum_timeouts < 0:
            raise ValueError("failure budgets must be non-negative")


@dataclass(frozen=True, slots=True)
class SelectionDecision:
    candidate_id: str
    route: str
    qualified: bool
    reason_codes: tuple[str, ...]
    worst_speedup: float | None
    evidence_ids: tuple[str, ...]


def policy_from_mapping(raw: Mapping[str, Any]) -> SelectionPolicy:
    """Construct policy without coercing untrusted configuration values."""
    return SelectionPolicy(
        minimum_profile_runs=raw["minimum_profile_runs"],
        minimum_distinct_environment_ids=raw["minimum_distinct_environment_ids"],
        minimum_speedup=raw["minimum_speedup"],
        maximum_abs_error=raw["maximum_abs_error"],
        maximum_crashes=raw["maximum_crashes"],
        maximum_timeouts=raw["maximum_timeouts"],
    )


def evaluate_candidate(
    *,
    candidate_id: str,
    current_source_identity: str,
    reference_available: bool,
    isolation_satisfied: bool,
    protocol_compatible: bool,
    evidence: Iterable[ProfileEvidence],
    policy: SelectionPolicy,
) -> SelectionDecision:
    for field, value in (
        ("candidate_id", candidate_id),
        ("current_source_identity", current_source_identity),
    ):
        if not isinstance(value, str) or not value.strip():
            raise AccelerationSelectionError(f"{field} must be non-empty text")
        if value != value.strip():
            raise AccelerationSelectionError(f"{field} must be canonical text")
    for field, value in (
        ("reference_available", reference_available),
        ("isolation_satisfied", isolation_satisfied),
        ("protocol_compatible", protocol_compatible),
    ):
        if not isinstance(value, bool):
            raise TypeError(f"{field} must be boolean")
    if not isinstance(policy, SelectionPolicy):
        raise TypeError("policy must be SelectionPolicy")
    if isinstance(evidence, (str, bytes)):
        raise TypeError("evidence must be an iterable of ProfileEvidence")
    supplied = tuple(evidence)
    if any(not isinstance(item, ProfileEvidence) for item in supplied):
        raise TypeError("evidence entries must be ProfileEvidence")

    rows = tuple(item for item in supplied if item.candidate_id == candidate_id)
    reasons: list[str] = []
    if not reference_available:
        reasons.append("fallback_unavailable")
    if not isolation_satisfied:
        reasons.append("isolation_requirement_unsatisfied")
    if not protocol_compatible:
        reasons.append("protocol_incompatible")
    evidence_ids = [item.evidence_id for item in rows]
    if len(evidence_ids) != len(set(evidence_ids)):
        reasons.append("duplicate_profile_evidence")
    if len(rows) < policy.minimum_profile_runs:
        reasons.append("insufficient_profile_runs")
    if len({item.environment_id for item in rows}) < policy.minimum_distinct_environment_ids:
        reasons.append("insufficient_environment_coverage")

    stale = [item.evidence_id for item in rows if item.source_identity != current_source_identity]
    if stale:
        reasons.append("stale_source_identity")

    if any(not item.correctness_passed for item in rows):
        reasons.append("correctness_failure")
    if any(item.max_abs_error > policy.maximum_abs_error for item in rows):
        reasons.append("error_tolerance_exceeded")
    if sum(item.crash_count for item in rows) > policy.maximum_crashes:
        reasons.append("crash_budget_exceeded")
    if sum(item.timeout_count for item in rows) > policy.maximum_timeouts:
        reasons.append("timeout_budget_exceeded")

    speedups = [item.speedup for item in rows]
    worst_speedup = min(speedups) if speedups else None
    if worst_speedup is None or worst_speedup < policy.minimum_speedup:
        reasons.append("speedup_threshold_not_met")

    qualified = not reasons
    return SelectionDecision(
        candidate_id=candidate_id,
        route="accelerated" if qualified else "reference",
        qualified=qualified,
        reason_codes=tuple(sorted(set(reasons))),
        worst_speedup=worst_speedup,
        evidence_ids=tuple(sorted(item.evidence_id for item in rows)),
    )


__all__ = [
    "AccelerationSelectionError",
    "ProfileEvidence",
    "SelectionPolicy",
    "SelectionDecision",
    "policy_from_mapping",
    "evaluate_candidate",
]
