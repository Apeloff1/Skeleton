"""Context-window characterization from controlled black-box trials."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ContextTrial:
    trial_id: str
    context_units: int
    success: bool
    fidelity: float
    output_digest: str
    condition: str = "default"

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise ReverseEngineeringError("context trial requires trial_id")
        if self.context_units < 0:
            raise ReverseEngineeringError("context_units must be non-negative")
        if not 0.0 <= self.fidelity <= 1.0:
            raise ReverseEngineeringError("fidelity must be within [0, 1]")
        if len(self.output_digest) != 64:
            raise ReverseEngineeringError("output_digest must be sha256 length")


@dataclass(frozen=True)
class ContextBoundaryReport:
    condition: str
    trial_count: int
    max_success_units: int | None
    first_failure_units: int | None
    max_high_fidelity_units: int | None
    monotonicity_violations: int
    lower_bound_units: int
    upper_bound_units: int | None
    confidence: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "trial_count": self.trial_count,
            "max_success_units": self.max_success_units,
            "first_failure_units": self.first_failure_units,
            "max_high_fidelity_units": self.max_high_fidelity_units,
            "monotonicity_violations": self.monotonicity_violations,
            "lower_bound_units": self.lower_bound_units,
            "upper_bound_units": self.upper_bound_units,
            "confidence": self.confidence,
            "digest": self.digest,
        }


def characterize_context(
    trials: Sequence[ContextTrial],
    *,
    fidelity_threshold: float = 0.9,
) -> tuple[ContextBoundaryReport, ...]:
    if not 0.0 <= fidelity_threshold <= 1.0:
        raise ReverseEngineeringError("fidelity_threshold must be within [0, 1]")
    if not trials:
        raise ReverseEngineeringError("context characterization requires trials")

    grouped: dict[str, list[ContextTrial]] = {}
    for trial in trials:
        grouped.setdefault(trial.condition, []).append(trial)

    reports: list[ContextBoundaryReport] = []
    for condition, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: (item.context_units, item.trial_id))
        successes = [item.context_units for item in ordered if item.success]
        failures = [item.context_units for item in ordered if not item.success]
        high = [
            item.context_units
            for item in ordered
            if item.success and item.fidelity >= fidelity_threshold
        ]
        violations = 0
        seen_failure = False
        for item in ordered:
            if not item.success:
                seen_failure = True
            elif seen_failure:
                violations += 1

        max_success = max(successes) if successes else None
        first_failure = min(failures) if failures else None
        lower = max(high) if high else 0
        upper_candidates = [
            item.context_units
            for item in ordered
            if (not item.success) or item.fidelity < fidelity_threshold
        ]
        upper = min(upper_candidates) if upper_candidates else None

        coverage = min(1.0, len(ordered) / 8.0)
        bracket_bonus = 0.2 if upper is not None and lower > 0 else 0.0
        penalty = min(0.4, violations * 0.1)
        confidence = round(max(0.0, min(1.0, 0.35 + 0.4 * coverage + bracket_bonus - penalty)), 6)
        payload = {
            "condition": condition,
            "trials": [
                {
                    "trial_id": item.trial_id,
                    "context_units": item.context_units,
                    "success": item.success,
                    "fidelity": round(item.fidelity, 9),
                    "output_digest": item.output_digest,
                }
                for item in ordered
            ],
            "fidelity_threshold": fidelity_threshold,
        }
        reports.append(
            ContextBoundaryReport(
                condition=condition,
                trial_count=len(ordered),
                max_success_units=max_success,
                first_failure_units=first_failure,
                max_high_fidelity_units=max(high) if high else None,
                monotonicity_violations=violations,
                lower_bound_units=lower,
                upper_bound_units=upper,
                confidence=confidence,
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
