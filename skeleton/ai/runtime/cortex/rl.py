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


class DPOPreferenceOptimizer:
    """Direct Preference Optimization (DPO) & Contrastive Advantage Trainer.

    Optimizes both numeric encounter-mix heads and language-model token
    log-probabilities directly from (prompt, chosen, rejected) preference
    triples without requiring a separate reward network:
        L_DPO = -log sigma(beta * ((log pi(y_w|x) - log pi_ref(y_w|x)) - (log pi(y_l|x) - log pi_ref(y_l|x))))
    """

    def __init__(self, *, beta: float = 0.25, lr: float = 0.04) -> None:
        self.beta = max(0.01, float(beta))
        self.lr = max(1e-5, float(lr))
        self.steps = 0
        self.preference_wins = 0
        self.last_margin = 0.0

    @staticmethod
    def _seq_logprob(lm, text: str) -> float:
        import math
        from skeleton.cortex.attn import softmax

        if lm is None or not hasattr(lm, "_ids") or not hasattr(lm, "_logits"):
            return 0.0
        ids = list(lm._ids(text or ""))
        if len(ids) < 2:
            return 0.0
        ctx = max(1, int(getattr(lm, "ctx", 6) or 6))
        total = 0.0
        count = 0
        for i in range(1, len(ids)):
            window = ids[max(0, i - ctx):i]
            logits = list(lm._logits(window))
            probs = softmax(logits)
            tgt = int(ids[i])
            if 0 <= tgt < len(probs):
                total += math.log(max(probs[tgt], 1e-12))
                count += 1
        return total / max(1, count)

    def step_preference_pair(
        self,
        lm,
        prompt: str,
        chosen_text: str,
        rejected_text: str,
        *,
        head: Optional[NumericHead] = None,
        hidden: Optional[Sequence[float]] = None,
        chosen_mix: Optional[Sequence[float]] = None,
        rejected_mix: Optional[Sequence[float]] = None,
    ) -> Dict[str, Any]:
        import math
        from skeleton.cortex.attn import softmax

        w_full = f"{prompt} {chosen_text}".strip()
        l_full = f"{prompt} {rejected_text}".strip()
        lp_w_before = self._seq_logprob(lm, w_full)
        lp_l_before = self._seq_logprob(lm, l_full)
        raw_margin = self.beta * (lp_w_before - lp_l_before)
        # Sigmoid(-margin) = preference gradient weight
        grad_scale = 1.0 / (1.0 + math.exp(max(-20.0, min(20.0, raw_margin))))
        dpo_loss = -math.log(max(1.0 - grad_scale + 1e-7, 1e-9))

        # Apply positive update on chosen sequence and repulsive unlikelihood step on rejected tokens
        eff_lr = self.lr * (0.4 + 0.8 * grad_scale)
        if lm is not None and hasattr(lm, "fit"):
            lm.fit([w_full], lr=eff_lr, schedule="cosine")
            if hasattr(lm, "_ids") and hasattr(lm, "_forward") and hasattr(lm, "Wout"):
                r_ids = list(lm._ids(l_full))
                ctx = max(1, int(getattr(lm, "ctx", 6) or 6))
                for i in range(1, min(len(r_ids), 6)):
                    win = r_ids[max(0, i - ctx):i]
                    h_seq, _ = lm._forward(win)
                    if not h_seq:
                        continue
                    y = h_seq[-1]
                    logits = list(lm._unembed(y))
                    probs = softmax(logits)
                    bad_tok = int(r_ids[i])
                    if 0 <= bad_tok < len(probs) and bad_tok < len(lm.Wout):
                        # Push down probability of rejected continuation token
                        repel = min(0.02, eff_lr * 0.25 * probs[bad_tok])
                        for d in range(min(len(y), len(lm.Wout[bad_tok]))):
                            lm.Wout[bad_tok][d] -= repel * float(y[d])
                        if hasattr(lm, "bout") and bad_tok < len(lm.bout):
                            lm.bout[bad_tok] -= repel

        head_loss = None
        if head is not None and hidden is not None and chosen_mix is not None:
            head_loss = head.step(hidden, chosen_mix, lr=eff_lr)
            if rejected_mix is not None:
                # Contrastive push away from rejected encounter mix toward chosen mix
                away = [
                    max(0.0, 1.15 * float(chosen_mix[i]) - 0.15 * float(rejected_mix[i]))
                    for i in range(min(len(chosen_mix), len(rejected_mix)))
                ]
                head.step(hidden, away, lr=eff_lr * 0.35)

        lp_w_after = self._seq_logprob(lm, w_full)
        lp_l_after = self._seq_logprob(lm, l_full)
        after_margin = self.beta * (lp_w_after - lp_l_after)
        self.steps += 1
        if after_margin >= raw_margin:
            self.preference_wins += 1
        self.last_margin = after_margin

        return {
            "dpo_loss": round(dpo_loss, 6),
            "margin_before": round(raw_margin, 6),
            "margin_after": round(after_margin, 6),
            "margin_improved": after_margin >= raw_margin,
            "chosen_logprob_after": round(lp_w_after, 6),
            "rejected_logprob_after": round(lp_l_after, 6),
            "head_loss": round(float(head_loss), 6) if head_loss is not None else None,
            "steps": self.steps,
        }
