"""Midbrain — the medium language model.

Coordinator, not author. Salience splits the stimulus onto left (analytic)
and right (gestalt) tracts, sets arousal, and may ask PFC to inhibit.
It never answers the operator.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from skeleton.cortex.port import Thought, tokens

LEFT_CUE = (
    "ttk", "hp", "dps", "recipe", "compile", "number", "logic", "sequence",
    "code", "parse", "proof", "math", "rpm", "heat", "collapse", "sim",
)
RIGHT_CUE = (
    "feel", "era", "room", "layout", "oracle", "gestalt", "analog", "spatial",
    "dread", "cozy", "soul", "spectacle", "intimacy", "authorial", "palette",
)


def _weights(stim: str) -> Tuple[float, float, float]:
    toks = tokens(stim)
    bag = set(toks)
    left = sum(1 for c in LEFT_CUE if c in bag)
    right = sum(1 for c in RIGHT_CUE if c in bag)
    n = max(1, left + right)
    lw, rw = left / n, right / n
    if left == 0 and right == 0:
        lw, rw = 0.55, 0.55  # mixed default — both tracts
    arousal = min(1.0, len(toks) / 36.0 + len(bag) / 24.0)
    return arousal, lw, rw


class Midbrain:
    """Medium model. Routes. Does not speak."""

    name = "midbrain-local"
    scale = "medium"
    slot = "midbrain"

    def __init__(self) -> None:
        from skeleton.cortex.learned import LearnedWeights
        self.weights = LearnedWeights(
            order=3, dim=8, seed=3, attn=True, ctx=6,
            n_heads=2, n_layers=1, d_ff=16,
        )

    @property
    def lm(self):
        return self.weights.lm

    @property
    def neural(self):
        return self.weights.neural

    @property
    def transformer(self):
        return self.weights.transformer

    def fit(self, text: str) -> int:
        return self.weights.fit(text)

    def snapshot(self) -> dict:
        return self.weights.snapshot()

    def perplexity(self, texts) -> float:
        xf = self.transformer
        if xf is not None and hasattr(xf, "perplexity"):
            return float(xf.perplexity(texts))
        if hasattr(self.lm, "perplexity"):
            return float(self.lm.perplexity(texts))
        return float("inf")

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        arousal, lw, rw = _weights(stimulus or "")
        to_left = lw >= 0.25
        to_right = rw >= 0.25
        inhibit = not (stimulus or "").strip()
        bits = [
            f"arousal={arousal:.2f}",
            f"left={lw:.2f}{'*' if to_left else ''}",
            f"right={rw:.2f}{'*' if to_right else ''}",
        ]
        if inhibit:
            bits.append("INHIBIT")
        xf = self.transformer
        if xf is not None and hasattr(xf, "decode") and (stimulus or "").strip():
            draft = str(xf.decode(stimulus, n=4, seed=3) or "").strip()
            if draft:
                bits.append("DRAFT " + draft)
        return Thought(
            slot="midbrain", kind="route",
            text="COORD " + " ".join(bits),
            confidence=0.80,
            tags=("route", "coordinator", "medium") + (("left",) if to_left else ()) + (("right",) if to_right else ()),
            numbers=(arousal, lw, rw),
        )
