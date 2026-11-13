"""P2 cinematic and world-cognition candidate layer.

Produces deterministic action and prediction receipts from percepts.
Does not train agents or call external cognition models.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Sequence


class P2CognitionError(ValueError):
    pass


@dataclass(frozen=True)
class CognitionReceipt:
    action: str
    confidence: float
    prediction_digest: str
    receipt_id: str


def reason_cinematic(
    percepts: Sequence[str],
    *,
    goal: str,
) -> CognitionReceipt:
    """Deterministic cinematic suggestion from ordered percepts and a goal."""
    if not percepts or not goal:
        raise P2CognitionError("percepts and goal are required")
    if any(not p or len(p) > 120 for p in percepts):
        raise P2CognitionError("percept tokens must be non-empty and bounded")
    payload = json.dumps({"percepts": list(percepts), "goal": goal}, sort_keys=True, separators=(",", ":"))
    digest = sha256(payload.encode()).hexdigest()
    # Stable action choice from digest, not from a model.
    actions = ("observe", "approach", "hold", "retreat")
    action = actions[int(digest[:2], 16) % len(actions)]
    confidence = round((int(digest[2:4], 16) / 255.0), 3)
    return CognitionReceipt(
        action=action,
        confidence=confidence,
        prediction_digest=digest,
        receipt_id=sha256((action + digest).encode()).hexdigest(),
    )
