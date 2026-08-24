"""Adaptive batch learner — learns how to learn from its own run history.

The meta-learner adapts to tasks; this module adapts the *learner*:
it watches the outcome history of learning runs (loss curves, wall time,
final quality) and tunes the hyperparameters of the next run — learning
rate, inner steps, and batch composition — by bandit-style exploration
over a small candidate grid.

Design
------
- Each candidate configuration is an arm in a UCB1 bandit: exploit the
  config with the best mean final-loss, explore the under-tried ones with
  an optimism bonus. Deterministic given the same history (the UCB1
  formula has no randomness).
- The reward is normalised final loss inverted, so lower loss → higher
  reward; runs that failed outright get reward 0 and count against the arm.
- The tuner is generic over the config space: any JSON-serialisable dict
  of hyperparameters can be an arm. The MetaLearner's (learning_rate,
  inner_steps) grid is the default instance, not a special case.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class Arm:
    """One candidate hyperparameter configuration with its history."""
    config: Dict[str, Any]
    pulls: int = 0
    total_reward: float = 0.0

    @property
    def mean_reward(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0

    def ucb1(self, total_pulls: int, c: float = 1.414) -> float:
        if self.pulls == 0:
            return float("inf")  # untried arms go first
        return self.mean_reward + c * math.sqrt(math.log(total_pulls) / self.pulls)

    @property
    def key(self) -> str:
        return json.dumps(self.config, sort_keys=True)


@dataclass(frozen=True)
class RunRecord:
    config_key: str
    final_loss: float
    wall_time_s: float
    reward: float


class AdaptiveLearner:
    """UCB1 tuner over hyperparameter configurations."""

    def __init__(self, candidates: List[Dict[str, Any]], *,
                 exploration: float = 1.414,
                 bus: Optional[EventBus] = None) -> None:
        if not candidates:
            raise ValueError("at least one candidate configuration is required")
        self._arms: Dict[str, Arm] = {
            json.dumps(c, sort_keys=True): Arm(config=dict(c)) for c in candidates
        }
        self._exploration = exploration
        self._bus = bus
        self._history: List[RunRecord] = []

    def suggest(self) -> Dict[str, Any]:
        """The configuration to run next (UCB1 argmax)."""
        total = sum(a.pulls for a in self._arms.values())
        best = max(self._arms.values(),
                   key=lambda a: a.ucb1(total, self._exploration))
        return dict(best.config)

    def report(self, config: Dict[str, Any], *, final_loss: float,
               wall_time_s: float, failed: bool = False) -> None:
        """Feed one run's outcome back into the bandit."""
        key = json.dumps(config, sort_keys=True)
        arm = self._arms.setdefault(key, Arm(config=dict(config)))
        reward = 0.0 if failed else 1.0 / (1.0 + max(final_loss, 0.0))
        arm.pulls += 1
        arm.total_reward += reward
        self._history.append(RunRecord(key, final_loss, wall_time_s, reward))
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="intelligence.learner.run_reported",
                    payload={"config": config, "final_loss": final_loss,
                             "reward": round(reward, 4), "pulls": arm.pulls},
                    correlation_id=f"adapt_{len(self._history)}",
                )
            )

    def best(self) -> Dict[str, Any]:
        """The current exploit-optimal configuration."""
        tried = [a for a in self._arms.values() if a.pulls > 0]
        if not tried:
            return self.suggest()
        return dict(max(tried, key=lambda a: a.mean_reward).config)

    def stats(self) -> Dict[str, Any]:
        return {
            "runs": len(self._history),
            "arms": len(self._arms),
            "tried_arms": sum(1 for a in self._arms.values() if a.pulls > 0),
            "best_mean_reward": round(
                max((a.mean_reward for a in self._arms.values()), default=0.0), 4),
        }


def default_meta_grid() -> List[Dict[str, Any]]:
    """A small sensible grid for the MetaLearner's hyperparameters."""
    return [
        {"learning_rate": lr, "inner_steps": steps}
        for lr in (0.001, 0.01, 0.1)
        for steps in (3, 5, 10)
    ]
