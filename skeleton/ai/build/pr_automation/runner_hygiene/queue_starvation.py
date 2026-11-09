"""Queue / starvation hygiene for auto-merge and merge-readiness sweeps.

Filter-before-cap: allowed-base filtering precedes target caps so disallowed
bases cannot starve valid main work. Incomplete pagination stays fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence, TypeVar

from .types import Finding, HygieneVerdict

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class QueueCandidate:
    number: int
    base_ref: str
    head_sha: str
    draft: bool = False
    allowed: bool = True
    priority: int = 0


@dataclass(frozen=True, slots=True)
class QueuePressure:
    selected: tuple[QueueCandidate, ...]
    skipped_disallowed: int
    truncated: bool
    complete: bool
    findings: tuple[Finding, ...]
    verdict: HygieneVerdict

    @property
    def starved(self) -> bool:
        return self.truncated and not self.complete


def filter_before_cap(
    candidates: Sequence[QueueCandidate],
    *,
    allowed_bases: Sequence[str] = ("main",),
    max_targets: int = 50,
) -> QueuePressure:
    if max_targets <= 0:
        raise ValueError("max_targets must be positive")
    allowed = tuple(allowed_bases) or ("main",)
    eligible = [c for c in candidates if c.base_ref in allowed and c.allowed]
    skipped = len(candidates) - len(eligible)
    # Deterministic: higher priority first, then lower PR number
    eligible.sort(key=lambda c: (-c.priority, c.number))
    selected = tuple(eligible[:max_targets])
    truncated = len(eligible) > max_targets
    findings: list[Finding] = []
    if truncated:
        findings.append(
            Finding(
                code="queue.target_cap_truncation",
                severity="medium",
                message=(
                    f"eligible candidates {len(eligible)} exceeded max_targets={max_targets}; "
                    "saturation remains incomplete/fail-closed"
                ),
                subject="queue",
            )
        )
    # Truncation => incomplete (fail-closed), never pretend complete
    complete = not truncated
    verdict = HygieneVerdict.HOLD if truncated else HygieneVerdict.ALLOW
    if skipped and not eligible:
        findings.append(
            Finding(
                code="queue.no_eligible_after_base_filter",
                severity="high",
                message="no candidates remain after allowed-base filter",
                subject="queue",
            )
        )
        verdict = HygieneVerdict.DENY
        complete = False
    return QueuePressure(
        selected=selected,
        skipped_disallowed=skipped,
        truncated=truncated,
        complete=complete,
        findings=tuple(findings),
        verdict=verdict,
    )


def assess_queue_starvation(pressure: QueuePressure) -> HygieneVerdict:
    if pressure.verdict is HygieneVerdict.DENY:
        return HygieneVerdict.DENY
    if pressure.starved or not pressure.complete:
        return HygieneVerdict.HOLD
    return HygieneVerdict.ALLOW


def filter_items_before_cap(
    items: Iterable[T],
    *,
    predicate,
    max_items: int,
) -> tuple[tuple[T, ...], bool, int]:
    """Generic filter-before-cap helper. Returns (selected, truncated, skipped)."""
    if max_items <= 0:
        raise ValueError("max_items must be positive")
    eligible: list[T] = []
    skipped = 0
    for item in items:
        if predicate(item):
            eligible.append(item)
        else:
            skipped += 1
    truncated = len(eligible) > max_items
    return tuple(eligible[:max_items]), truncated, skipped


__all__ = [
    "QueueCandidate",
    "QueuePressure",
    "assess_queue_starvation",
    "filter_before_cap",
    "filter_items_before_cap",
]
