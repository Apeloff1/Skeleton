"""Adaptive plane weights — learn RRF fusion weights from retrieval outcomes.

Static per-plane weights are tuned by hand; this module learns them. Each
plane is a bandit arm: after a retrieval, callers report which plane's fragment
the consumer actually used, and the arm's weight moves by exponential moving
average toward reward (used) / penalty (unused).

Learner state is explicitly serializable so feedback survives process restarts.
The quad retriever owns cache invalidation when weights change; callers should
feed outcomes through QuadRetriever.observe rather than mutating the learner
behind the retriever.

Pure domain, deterministic under a seeded test clock (no randomness).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

PLANES: Tuple[str, ...] = ("rag", "cag", "mag", "kag")
STATE_VERSION = 1


def _finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


@dataclass
class PlaneArm:
    """One retrieval plane's learning state."""

    plane: str
    weight: float = 1.0
    wins: int = 0
    trials: int = 0

    @property
    def rate(self) -> float | None:
        if self.trials == 0:
            return None
        return self.wins / self.trials


class PlaneWeightLearner:
    """EMA bandit over retrieval planes with validated, durable state."""

    def __init__(
        self,
        base_weights: Optional[Dict[str, float]] = None,
        *,
        lr: float = 0.15,
        floor: float = 0.3,
        ceil: float = 2.0,
    ) -> None:
        learning_rate = _finite_number("lr", lr)
        lower = _finite_number("floor", floor)
        upper = _finite_number("ceil", ceil)
        if not 0.0 < learning_rate <= 1.0:
            raise ValueError("lr must be in (0, 1]")
        if lower < 0.0:
            raise ValueError("floor must be non-negative")
        if upper <= lower:
            raise ValueError("ceil must be greater than floor")

        if base_weights is None:
            base = {plane: 1.0 for plane in PLANES}
        elif not isinstance(base_weights, dict):
            raise ValueError("base weights must be an object")
        else:
            missing = [plane for plane in PLANES if plane not in base_weights]
            if missing:
                raise ValueError("base weights are incomplete")
            base = dict(base_weights)
        unknown = sorted(set(base) - set(PLANES))
        if unknown:
            raise ValueError(f"unknown plane weight(s): {', '.join(unknown)}")

        self.lr = learning_rate
        self.floor = lower
        self.ceil = upper
        self._arms: Dict[str, PlaneArm] = {}
        for plane in PLANES:
            weight = _finite_number(f"base weight for {plane}", base[plane])
            if not self.floor <= weight <= self.ceil:
                raise ValueError(
                    f"base weight for {plane} must be within [{self.floor}, {self.ceil}]"
                )
            self._arms[plane] = PlaneArm(plane=plane, weight=weight)
        self.updates = 0

    @staticmethod
    def _plane_set(values: Iterable[str], *, field: str) -> set[str]:
        planes = set(values)
        if any(not isinstance(plane, str) for plane in planes):
            raise ValueError(f"{field} must contain plane names")
        unknown = sorted(planes - set(PLANES))
        if unknown:
            raise ValueError(f"unknown plane(s) in {field}: {', '.join(unknown)}")
        return planes

    def observe(
        self,
        used_planes: Iterable[str],
        *,
        all_planes: Optional[Iterable[str]] = None,
    ) -> None:
        """Record one retrieval outcome (used planes up, unused candidates down)."""
        used = self._plane_set(used_planes, field="used_planes")
        considered = (
            self._plane_set(all_planes, field="all_planes")
            if all_planes is not None
            else set(PLANES)
        )
        if not considered:
            raise ValueError("all_planes must contain at least one plane")
        missing = sorted(used - considered)
        if missing:
            raise ValueError(
                "used_planes must be a subset of all_planes; missing: "
                + ", ".join(missing)
            )

        for plane in considered:
            arm = self._arms[plane]
            arm.trials += 1
            target = self.ceil if plane in used else self.floor
            arm.weight += self.lr * (target - arm.weight)
            arm.weight = min(self.ceil, max(self.floor, arm.weight))
            if plane in used:
                arm.wins += 1
        self.updates += 1

    def effective_weights(self) -> Dict[str, float]:
        return {plane: round(arm.weight, 4) for plane, arm in self._arms.items()}

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable learner checkpoint."""
        return {
            "version": STATE_VERSION,
            "lr": self.lr,
            "floor": self.floor,
            "ceil": self.ceil,
            "updates": self.updates,
            "arms": {
                plane: {
                    "weight": arm.weight,
                    "wins": arm.wins,
                    "trials": arm.trials,
                }
                for plane, arm in self._arms.items()
            },
        }

    @classmethod
    def from_snapshot(cls, state: Mapping[str, Any]) -> "PlaneWeightLearner":
        """Restore a learner checkpoint, rejecting corrupt or incompatible state."""
        if not isinstance(state, Mapping):
            raise ValueError("learner state must be a mapping")
        if state.get("version") != STATE_VERSION:
            raise ValueError(f"unsupported learner state version: {state.get('version')!r}")

        arms = state.get("arms")
        if not isinstance(arms, Mapping) or set(arms) != set(PLANES):
            raise ValueError("learner state must contain exactly the known retrieval planes")

        floor = _finite_number("floor", state.get("floor"))
        ceil = _finite_number("ceil", state.get("ceil"))
        lr = _finite_number("lr", state.get("lr"))

        base: Dict[str, float] = {}
        counts: Dict[str, Tuple[int, int]] = {}
        for plane in PLANES:
            row = arms.get(plane)
            if not isinstance(row, Mapping):
                raise ValueError(f"learner state for {plane} must be a mapping")
            weight = _finite_number(f"{plane}.weight", row.get("weight"))
            wins = _nonnegative_int(f"{plane}.wins", row.get("wins"))
            trials = _nonnegative_int(f"{plane}.trials", row.get("trials"))
            if wins > trials:
                raise ValueError(f"{plane}.wins cannot exceed trials")
            base[plane] = weight
            counts[plane] = (wins, trials)

        learner = cls(base, lr=lr, floor=floor, ceil=ceil)
        updates = _nonnegative_int("updates", state.get("updates"))
        if max((trials for _, trials in counts.values()), default=0) > updates:
            raise ValueError("plane trials cannot exceed learner updates")

        learner.updates = updates
        for plane, (wins, trials) in counts.items():
            learner._arms[plane].wins = wins
            learner._arms[plane].trials = trials
        return learner

    def stats(self) -> Dict[str, object]:
        return {
            "state_version": STATE_VERSION,
            "updates": self.updates,
            "weights": self.effective_weights(),
            "rates": {
                plane: None if arm.rate is None else round(arm.rate, 4)
                for plane, arm in self._arms.items()
            },
        }


def attach_learner(
    quad: Any,
    learner: Optional[PlaneWeightLearner] = None,
) -> PlaneWeightLearner:
    """Attach a weight learner and invalidate any rankings fused without it."""
    existing = getattr(quad, "_weight_learner", None)
    if learner is None and existing is not None:
        return existing

    learner = learner or PlaneWeightLearner(getattr(quad, "weights", None))
    attach = getattr(quad, "attach_weight_learner", None)
    if callable(attach):
        attach(learner)
    else:
        quad._weight_learner = learner
    return learner
