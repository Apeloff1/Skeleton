"""Adaptive plane weights — learn RRF fusion weights from retrieval outcomes.

Static per-plane weights (``DEFAULT_WEIGHTS``) are tuned by hand; this module
learns them. Each plane is a bandit arm: after a retrieval, callers report
which plane's fragment the consumer actually used, and the arm's weight
moves by exponential moving average toward reward (used) / penalty (unused).
The quad retriever reads :meth:`effective_weights` instead of its static
table whenever a learner is attached.

Pure domain, deterministic under a seeded test clock (no randomness).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

PLANES: Tuple[str, ...] = ("rag", "cag", "mag", "kag")


@dataclass
class PlaneArm:
    """One retrieval plane's learning state."""
    plane: str
    weight: float = 1.0
    wins: int = 0
    trials: int = 0

    @property
    def rate(self) -> float:
        """Laplace-smoothed win rate; 0.5 prior keeps cold planes explorable."""
        return (self.wins + 1) / (self.trials + 2)


class PlaneWeightLearner:
    """EMA bandit over retrieval planes. See module docstring."""

    def __init__(
        self,
        base_weights: Optional[Dict[str, float]] = None,
        *,
        lr: float = 0.15,
        floor: float = 0.3,
        ceil: float = 2.0,
    ) -> None:
        if lr <= 0 or lr > 1:
            raise ValueError("lr must be in (0, 1]")
        base = dict(base_weights or {})
        self._arms: Dict[str, PlaneArm] = {
            p: PlaneArm(plane=p, weight=float(base.get(p, 1.0))) for p in PLANES
        }
        self.lr = float(lr)
        self.floor = float(floor)
        self.ceil = float(ceil)
        self.updates = 0

    def observe(self, used_planes: Iterable[str], *, all_planes: Optional[Iterable[str]] = None) -> None:
        """Record one retrieval outcome (used planes up, unused candidates down)."""
        used = set(used_planes)
        considered = set(all_planes) if all_planes is not None else set(PLANES)
        for plane in considered:
            arm = self._arms.get(plane)
            if arm is None:
                continue
            arm.trials += 1
            target = self.ceil if plane in used else self.floor
            arm.weight += self.lr * (target - arm.weight)
            arm.weight = min(self.ceil, max(self.floor, arm.weight))
            if plane in used:
                arm.wins += 1
        self.updates += 1

    def effective_weights(self) -> Dict[str, float]:
        return {p: round(a.weight, 4) for p, a in self._arms.items()}

    def stats(self) -> Dict[str, object]:
        return {
            "updates": self.updates,
            "weights": self.effective_weights(),
            "rates": {p: round(a.rate, 4) for p, a in self._arms.items()},
        }


# ---------------------------------------------------------------------------
# QuadRetriever integration (F-2: the feedback loop, closed)
# ---------------------------------------------------------------------------

def attach_learner(quad, learner: Optional[PlaneWeightLearner] = None) -> PlaneWeightLearner:
    """Attach a weight learner to a QuadRetriever.

    After attachment, ``quad.retrieve`` fuses with the learner's effective
    weights instead of the static table, and ``quad.observe(...)`` feeds
    outcomes back. Idempotent.
    """
    learner = learner or PlaneWeightLearner(getattr(quad, "weights", None))
    quad._weight_learner = learner
    return learner
