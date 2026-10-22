"""skeleton/ai/runtime/weight_candidate_loop.py
Fail-closed weight candidate evaluation loop starter.
Records source/eval receipts. Never claims trained or promoted weights.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Final

try:
    from skeleton.kernel.errors import SkeletonError
except ImportError:
    class SkeletonError(Exception):
        pass

try:
    from skeleton.provenance.chronicle import emit_receipt
except ImportError:
    def emit_receipt(**kwargs):
        return kwargs.get("digest", "")

_MAX_CANDIDATES: Final[int] = 8

class WeightLoopError(SkeletonError):
    code = "AI_WEIGHT"
    severity = "high"

@dataclass
class CandidateCard:
    candidate_id: str
    source_receipt: str
    eval_receipt: str = ""
    score: float = 0.0
    promoted: bool = False
    digest: str = ""
    created_at: float = field(default_factory=time.time)

class WeightCandidateLoop:
    def __init__(self) -> None:
        self.candidates: dict[str, CandidateCard] = {}

    def admit(self, candidate_id: str, source_receipt: str) -> CandidateCard:
        if len(self.candidates) >= _MAX_CANDIDATES:
            raise WeightLoopError("candidate limit reached")
        if candidate_id in self.candidates:
            raise WeightLoopError("duplicate candidate")
        card = CandidateCard(candidate_id=candidate_id, source_receipt=source_receipt)
        payload = f"{candidate_id}:{source_receipt}"
        card.digest = hashlib.sha256(payload.encode()).hexdigest()
        self.candidates[candidate_id] = card
        emit_receipt(
            kind="weight_admit",
            target=candidate_id,
            digest=card.digest,
            source=source_receipt,
            stored_prose=0,
        )
        return card

    def evaluate(self, candidate_id: str, score: float, eval_receipt: str) -> CandidateCard:
        card = self.candidates.get(candidate_id)
        if not card:
            raise WeightLoopError("unknown candidate")
        if not (0.0 <= score <= 1.0):
            raise WeightLoopError("score out of bounds")
        card.score = score
        card.eval_receipt = eval_receipt
        payload = f"{candidate_id}:{score}:{eval_receipt}"
        card.digest = hashlib.sha256(payload.encode()).hexdigest()
        # never auto-promote
        card.promoted = False
        emit_receipt(
            kind="weight_eval",
            target=candidate_id,
            digest=card.digest,
            score=score,
            stored_prose=0,
        )
        return card

    def rollback(self, candidate_id: str) -> None:
        card = self.candidates.pop(candidate_id, None)
        if card:
            emit_receipt(kind="weight_rollback", target=candidate_id, stored_prose=0)
