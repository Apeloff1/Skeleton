"""REINFORCE — walk slack is the reward the numeric head eats.

The left mix head is a policy. Action = (trash, elite, boss). Reward =
thermal slack of a walk that used that mix. Baseline is an EMA of
reward. Advantage ≥ 0 steps the head toward the action; advantage < 0
steps it toward its current prediction (stay). That is the closed loop
at gradient resolution: the sim trains the model, not a search table.

Also credits the MoE router for the left expert when the walk extracts.
Pure Python.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from skeleton.cortex.heads import NumericHead, clamp_mix

Mix = Tuple[int, int, int]


class ReinforceState:
    """EMA baseline + step counter. One object per neocortex."""

    def __init__(self, *, alpha: float = 0.15, baseline: float = 0.50) -> None:
        self.alpha = float(alpha)
        self.baseline = float(baseline)
        self.steps = 0
        self.last_adv = 0.0
        self.last_reward = 0.0
        self.wins = 0
        self.trials = 0

    def step(
        self,
        head: NumericHead,
        hidden: Sequence[float],
        action: Sequence[float],
        reward: float,
        *,
        lr: float = 0.08,
    ) -> Dict[str, Any]:
        r = float(reward)
        adv = r - self.baseline
        self.baseline += self.alpha * (r - self.baseline)
        self.last_adv = adv
        self.last_reward = r
        self.steps += 1
        self.trials += 1
        tgt: Sequence[float]
        used_lr = lr
        if adv >= 0.0:
            tgt = action
            used_lr = lr * min(1.5, 0.25 + adv)
            self.wins += 1
        else:
            pred = head.activate(head.raw(hidden))
            tgt = pred
            used_lr = lr * 0.15
        loss = head.step(hidden, tgt, lr=used_lr)
        return {
            "loss": loss,
            "adv": adv,
            "reward": r,
            "baseline": self.baseline,
            "toward": "action" if adv >= 0.0 else "stay",
            "steps": self.steps,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "alpha": self.alpha,
            "baseline": self.baseline,
            "steps": self.steps,
            "last_adv": self.last_adv,
            "last_reward": self.last_reward,
            "wins": self.wins,
            "trials": self.trials,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "ReinforceState":
        st = cls(
            alpha=float((data or {}).get("alpha") or 0.15),
            baseline=float((data or {}).get("baseline") or 0.50),
        )
        st.steps = int((data or {}).get("steps") or 0)
        st.last_adv = float((data or {}).get("last_adv") or 0.0)
        st.last_reward = float((data or {}).get("last_reward") or 0.0)
        st.wins = int((data or {}).get("wins") or 0)
        st.trials = int((data or {}).get("trials") or 0)
        return st

    def to_dict(self) -> Dict[str, Any]:
        rate = (self.wins / self.trials) if self.trials else 0.0
        return {
            "baseline": round(self.baseline, 4),
            "steps": self.steps,
            "wins": self.wins,
            "trials": self.trials,
            "rate": round(rate, 4),
            "last_adv": round(self.last_adv, 4),
        }


def reinforce_mix(
    head: NumericHead,
    hidden: Sequence[float],
    action: Sequence[float],
    reward: float,
    state: ReinforceState,
    *,
    lr: float = 0.08,
) -> Dict[str, Any]:
    """Convenience: step + return the new prediction."""
    info = state.step(head, hidden, action, reward, lr=lr)
    info["predict"] = head.predict(hidden)
    info["action"] = clamp_mix(float(action[0]), float(action[1]), float(action[2]))
    return info
