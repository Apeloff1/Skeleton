"""Milestone registry for the Jeeves delivery quality plane.

Catalogs the mandatory pre-delivery stages. Candidate-only.
Does not execute reviews or claim certification.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryMilestone:
    milestone_id: str
    stage: str
    contract: str
    claim: str = "candidate-only"


DELIVERY_MILESTONES: tuple[DeliveryMilestone, ...] = (
    DeliveryMilestone("D1", "working-memory", "scope-limited no-found compaction"),
    DeliveryMilestone("D2", "dual-verification", "independent verification pair"),
    DeliveryMilestone("D3", "adversarial-probe", "mutation probes on retained notes"),
    DeliveryMilestone("D4", "quality-gate", "six-axis code/game quality"),
    DeliveryMilestone("D5", "provenance", "license and origin inventory"),
    DeliveryMilestone("D6", "copyright-check", "independent copyright/origin"),
    DeliveryMilestone("D7", "creative-rewrite", "voice and canon checker"),
    DeliveryMilestone("D8", "final-receipt", "hash-linked JVR serial"),
)


def delivery_ids() -> tuple[str, ...]:
    return tuple(m.milestone_id for m in DELIVERY_MILESTONES)


def require_delivery(milestone_id: str) -> DeliveryMilestone:
    for entry in DELIVERY_MILESTONES:
        if entry.milestone_id == milestone_id:
            return entry
    raise KeyError(milestone_id)
