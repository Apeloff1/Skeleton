"""Prefrontal cortex — the small language model.

Boilerplate, working memory, inhibition, executive plan. Cheap and
structured: it never freewheels. The four templates are the entire
vocabulary of the small model; a bound backend may replace them.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List

from skeleton.cortex.port import Thought, tokens

TEMPLATES: tuple[str, ...] = (
    "INGEST: restate the operator intent in one clause.",
    "DETECT: name the era dialect or blend.",
    "PLAN: tensor → lattice → oracle → forge → emit.",
    "INHIBIT: drop anything that is not a game-builder act.",
)

_VETO = ("harm", "weaponize", "exfiltrate secret", "self-harm")


class PrefrontalCortex:
    """Small model. Miller-span working memory. Veto is a first-class output."""

    name = "pfc-local"
    scale = "small"
    slot = "pfc"

    def __init__(self, *, span: int = 7) -> None:
        self.memory: deque[str] = deque(maxlen=max(3, span))
        from skeleton.cortex.learned import LearnedWeights
        # Small LM: n-gram + 1-layer transformer (no FFN). Boilerplate stays the think() spine.
        self.weights = LearnedWeights(
            order=2, dim=8, seed=2, attn=True, ctx=4, n_heads=1, n_layers=1, d_ff=0,
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
        text = (stimulus or "").strip()
        self.memory.append(text[:80])
        low = text.lower()
        veto = any(v in low for v in _VETO) or not text
        era = str(context.get("era") or "")
        steps: List[str] = [
            f"INGEST '{text[:72]}'",
            f"DETECT {era or 'from vision'}",
            "PLAN tensor→lattice→oracle→forge→emit",
        ]
        if context.get("left"):
            steps.append("HOLD left analytic")
        if context.get("right"):
            steps.append("HOLD right gestalt")
        if veto:
            body = "INHIBIT: PFC veto. Not a builder act."
            tags = ("veto", "boilerplate", "small")
            conf = 0.95
        else:
            body = " | ".join(steps)
            xf = self.transformer
            if xf is not None and hasattr(xf, "decode"):
                draft = str(xf.decode(text, n=6, seed=2) or "").strip()
                if draft:
                    body = body + " | DRAFT " + draft
            tags = ("plan", "boilerplate", "small")
            conf = 0.72 + min(0.2, len(tokens(text)) / 80.0)
        return Thought(
            slot="pfc", kind="plan", text=body, confidence=conf,
            tags=tags, numbers=(float(len(self.memory)), 1.0 if veto else 0.0),
        )
