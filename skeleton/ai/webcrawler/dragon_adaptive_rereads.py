"""Adaptive reread planning using uncertainty, contradictions and source diversity.

Produces deterministic next-pass tasks, never invents completed readings.
A source's repeated passes do not count as independent evidence.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

from .dragon_knowledge_ledger import RereadTask, schedule_rereads
from .dragon_probabilistic_distillation import Belief, EvidencePass


@dataclass(frozen=True)
class RereadDecision:
    source_id: str
    revision: str
    next_pass: RereadTask | None
    priority: float
    reason: str
    exhausted: bool


def plan_adaptive_rereads(
    belief: Belief, evidence: tuple[EvidencePass, ...], *,
    authorized: bool, min_passes: int = 3,
    max_passes: int = 12, limit: int = 100,
) -> tuple[RereadDecision, ...]:
    if not authorized:
        raise PermissionError("reread planning requires authorization")
    if not 1 <= min_passes <= max_passes <= 12 or not 1 <= limit <= 1000:
        raise ValueError("invalid reread budget")
    if not isfinite(belief.probability) or not 0 <= belief.probability <= 1:
        raise ValueError("invalid belief probability")
    sources: dict[tuple[str, str], list[EvidencePass]] = {}
    for item in evidence:
        if item.claim_id != belief.claim_id:
            raise ValueError("cross-claim evidence")
        sources.setdefault((item.source_id, item.source_revision), []).append(item)
    decisions = []
    for (source_id, revision), readings in sorted(sources.items()):
        schedule = schedule_rereads(
            source_id, revision, minimum=min_passes, maximum=max_passes,
        )
        used = {reading.pass_id for reading in readings}
        if len(used) != len(readings):
            raise ValueError("duplicate reading")
        remaining = [task for task in schedule
                     if f"pass-{task.pass_index}" not in used]
        incomplete = len(readings) < min_passes
        uncertainty = 1 - abs(2 * belief.probability - 1)
        contradiction = any(x.supports for x in readings) and any(
            not x.supports for x in readings
        )
        priority = round(
            (2 if incomplete else 0)
            + (1.5 if contradiction or belief.conflicting else 0)
            + uncertainty
            + 1 / (1 + len(readings)),
            6,
        )
        reason = ("minimum coverage" if incomplete else
                  "contradiction investigation" if contradiction or belief.conflicting
                  else "uncertainty reduction")
        decisions.append(RereadDecision(
            source_id, revision, remaining[0] if remaining else None,
            priority, reason, not remaining,
        ))
    decisions.sort(key=lambda x: (-x.priority, x.source_id, x.revision))
    return tuple(decisions[:limit])
