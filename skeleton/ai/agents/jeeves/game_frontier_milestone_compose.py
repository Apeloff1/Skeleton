"""Compose P0-P3 milestone receipts into one frontier admission.

Candidate-only. Joins the runtime, world-model, cognition and
qualification modules. Does not execute GPU work or load weights.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .game_frontier_dynamics import PresentationClock
from .game_frontier_p0_runtime import admit_p0_runtime, P0RuntimeReceipt
from .game_frontier_p1_worldmodel import WorldModelEvidence, world_model_receipt
from .game_frontier_p2_cognition import reason_cinematic, CognitionReceipt
from .game_frontier_p3_harness import qualify, P3Qualification


@dataclass(frozen=True)
class FrontierAdmission:
    """Single content-addressed admission across all four milestones."""

    p0: P0RuntimeReceipt
    p1_receipt: str
    p2: CognitionReceipt
    p3: P3Qualification
    admission_digest: str


def compose_frontier(
    *,
    clock: PresentationClock,
    lod_tier: int,
    weather_digest: str,
    evidence: WorldModelEvidence,
    percepts: tuple[str, ...],
    goal: str,
) -> FrontierAdmission:
    """Build the full candidate chain. Fails closed if any stage rejects."""
    p2 = reason_cinematic(percepts, goal=goal)
    p0 = admit_p0_runtime(
        clock,
        lod_tier=lod_tier,
        weather_digest=weather_digest,
        cognition_digest=p2.prediction_digest,
    )
    p1 = world_model_receipt(evidence)
    p3 = qualify(
        p0_admission_id=p0.admission_id,
        p1_receipt=p1,
        p2_receipt_id=p2.receipt_id,
    )
    payload = json.dumps(
        {
            "p0": p0.admission_id,
            "p1": p1,
            "p2": p2.receipt_id,
            "p3": p3.qualification_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return FrontierAdmission(
        p0=p0,
        p1_receipt=p1,
        p2=p2,
        p3=p3,
        admission_digest=sha256(payload.encode()).hexdigest(),
    )
