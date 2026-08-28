"""Learned guts of a ModelPort — one object, three scales.

Small     n-gram + skip-gram
Hemisphere n-gram + skip-gram
Medium    n-gram + skip-gram + causal transformer
Neo       causal transformer on the organizer (held separately)

Ports compose this. They do not copy-paste fit/snapshot.
Restore is the interchange of weights onto an existing tract.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from skeleton.cortex.lm import NGramLM, gameforge_vocab
from skeleton.cortex.neural import NeuralLM


class LearnedWeights:
    """Trainable weights sitting behind a specialized think()."""

    def __init__(
        self,
        *,
        order: int = 2,
        dim: int = 12,
        seed: int = 0,
        attn: bool = False,
        ctx: int = 6,
        n_heads: int = 1,
        n_layers: int = 1,
        d_ff: int = 0,
    ) -> None:
        vocab = gameforge_vocab()
        self.lm = NGramLM(order=order, vocab=vocab)
        self.neural = NeuralLM(vocab=vocab, dim=dim, seed=seed)
        self.transformer = None
        if attn:
            from skeleton.cortex.transformer import TinyTransformer
            self.transformer = TinyTransformer(
                vocab=vocab, dim=min(8, dim), ctx=ctx, seed=seed + 17,
                n_heads=n_heads, n_layers=n_layers, d_ff=d_ff,
            )

    def fit(self, text: str) -> int:
        n = self.lm.fit([text])
        self.neural.fit([text])
        if self.transformer is not None:
            self.transformer.fit([text])
        return n

    def snapshot(self) -> Dict[str, Any]:
        snap = self.lm.snapshot()
        snap["neural"] = self.neural.snapshot()
        if self.transformer is not None:
            snap["transformer"] = self.transformer.snapshot()
        return snap

    def restore(self, snap: Optional[Dict[str, Any]]) -> None:
        if not snap:
            return
        neural = snap.get("neural")
        trans = snap.get("transformer")
        ngram = {k: v for k, v in snap.items() if k not in {"neural", "transformer"}}
        if ngram.get("unigrams") is not None:
            self.lm = NGramLM.from_snapshot(ngram)
        if neural:
            self.neural = NeuralLM.from_snapshot(neural)
        if trans is not None:
            from skeleton.cortex.transformer import TinyTransformer
            self.transformer = TinyTransformer.from_snapshot(trans)

    @property
    def ngram_fitted(self) -> int:
        return int(getattr(self.lm, "fitted", 0) or 0)

    @property
    def neural_steps(self) -> int:
        return int(getattr(self.neural, "steps", 0) or 0)

    @property
    def transformer_steps(self) -> int:
        t = self.transformer
        return int(getattr(t, "steps", 0) or 0) if t is not None else 0
