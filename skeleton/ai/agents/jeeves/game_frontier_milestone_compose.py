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


def verify_admission(value: FrontierAdmission) -> bool:
    """Verify the complete receipt relationship, not merely its digest label.

    P1 is still a supplied evidence digest: this cannot authenticate mesh bytes
    or prove the external adapter executed. Full source replay is separate.
    """
    if not isinstance(value, FrontierAdmission):
        return False
    try:
        p0, p2 = value.p0, value.p2
        if not isinstance(p0, P0RuntimeReceipt) or not isinstance(p2, CognitionReceipt):
            return False
        prediction = p2.prediction_digest
        if (type(prediction) is not str or len(prediction) != 64
                or any(ch not in "0123456789abcdef" for ch in prediction)):
            return False
        action = ("observe", "approach", "hold", "retreat")[int(prediction[:2], 16) % 4]
        confidence = round(int(prediction[2:4], 16) / 255.0, 3)
        if (p2.action != action or type(p2.confidence) is not float
                or p2.confidence != confidence
                or p2.receipt_id != sha256((action + prediction).encode()).hexdigest()):
            return False
        if type(p0.clock_fps) is not int or type(p0.lod_tier) is not int:
            return False
        expected_p0 = P0RuntimeReceipt(p0.clock_fps, p0.lod_tier, p0.weather_digest, prediction)
        if expected_p0 != p0:
            return False
        expected_p3 = qualify(p0_admission_id=p0.admission_id, p1_receipt=value.p1_receipt,
                              p2_receipt_id=p2.receipt_id)
        if value.p3 != expected_p3:
            return False
        body = {"p0": p0.admission_id, "p1": value.p1_receipt,
                "p2": p2.receipt_id, "p3": expected_p3.qualification_id}
        expected = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return value.admission_digest == expected
    except (TypeError, ValueError, AttributeError, OverflowError):
        return False
