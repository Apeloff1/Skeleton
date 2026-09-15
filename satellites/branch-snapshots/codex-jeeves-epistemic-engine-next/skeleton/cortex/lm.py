"""Tiny language models for the PFC (small) and midbrain (medium) ports.

We are building a model, not wrapping one. Count-based n-grams with
Laplace smoothing: order-2 is the small boilerplate model, order-3 is
the medium coordinator. Fit on the GameForge closed world (templates,
era names, TTK identity, curriculum pairs). Perplexity on held-out
in-domain text must drop. Snapshot/restore is the interchange: acquire
copies weights, not a prompt.
"""
from __future__ import annotations

import math
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from skeleton.cortex.port import Thought, fingerprint, tokens

START, END = "<s>", "</s>"


def gameforge_corpus() -> List[str]:
    from skeleton.forge.eras import ERA_IDS
    from skeleton.cortex.pfc import TEMPLATES
    texts = list(TEMPLATES)
    texts += [e.replace("_", " ") for e in ERA_IDS]
    texts += [
        "HP DPS TTK compile recipe sim extract collapse heat vent",
        "plan tensor lattice oracle forge emit jeeves cortex",
        "COORD arousal left right inhibit midbrain",
        "bias loot combat heat balanced spatial gestalt era",
        "mix trash elite boss slack thermal walk cores hops",
        "soulslike extraction ttk elite dread rest",
        "spawn weapon extract late lock door bound",
        "INGEST DETECT PLAN INHIBIT boilerplate prefrontal",
        "like extraction_now bias=loot face=heat",
        "HP = DPS x TTK mix trash=2 elite=1 boss=0",
    ]
    try:
        from skeleton.cortex.curriculum import CORE_PAIRS
        texts += [a for a, b in CORE_PAIRS] + [b for a, b in CORE_PAIRS]
    except Exception:
        pass
    return texts


def gameforge_vocab() -> Tuple[str, ...]:
    bag = set()
    for t in gameforge_corpus():
        bag.update(tokens(t))
    bag.update({START, END})
    return tuple(sorted(bag))


class NGramLM:
    """Laplace-smoothed n-gram. Weights are the counts. No transformer."""

    def __init__(self, order: int = 2, *, vocab: Optional[Iterable[str]] = None) -> None:
        self.order = max(1, min(5, int(order)))
        self.unigrams: Dict[str, int] = {str(t): 0 for t in (vocab or ())}
        self.counts: Dict[Tuple[str, ...], Dict[str, int]] = {}
        self.total = 0
        self.fitted = 0

    def fit(self, texts: Iterable[str]) -> int:
        n = 0
        pad = (START,) * max(0, self.order - 1)
        for raw in texts:
            body = tokens(raw)
            if not body:
                continue
            for tok in body:
                self.unigrams[tok] = self.unigrams.get(tok, 0) + 1
                self.total += 1
            if self.order >= 2:
                stream = pad + body + (END,)
                width = self.order - 1
                for i in range(len(stream) - width):
                    ctx = stream[i:i + width]
                    nxt = stream[i + width]
                    bucket = self.counts.setdefault(ctx, {})
                    bucket[nxt] = bucket.get(nxt, 0) + 1
            n += 1
        self.fitted += n
        return n

    def _vocab_size(self) -> int:
        return max(1, len(self.unigrams))

    def logprob(self, text: str) -> float:
        body = tokens(text)
        if not body:
            return math.log(1.0 / self._vocab_size())
        pad = (START,) * max(0, self.order - 1)
        stream = pad + body + (END,)
        width = max(0, self.order - 1)
        V = self._vocab_size()
        lp = 0.0
        n = 0
        for i in range(width, len(stream)):
            ctx = stream[i - width:i] if width else ()
            nxt = stream[i]
            if self.order <= 1 or not ctx:
                c = self.unigrams.get(nxt, 0)
                s = max(1, self.total)
                p = (c + 1.0) / (s + V)
            else:
                bucket = self.counts.get(ctx) or {}
                c = bucket.get(nxt, 0)
                s = sum(bucket.values())
                p = (c + 1.0) / (s + V)
            lp += math.log(max(p, 1e-12))
            n += 1
        return lp / max(1, n)

    def perplexity(self, texts: Iterable[str] | str) -> float:
        if isinstance(texts, str):
            seq = [texts]
        else:
            seq = [t for t in texts if t]
        if not seq:
            return float(self._vocab_size())
        mean = sum(self.logprob(t) for t in seq) / len(seq)
        return math.exp(-mean)

    def generate(self, prefix: str | Sequence[str], n: int = 16, *, seed: int = 0) -> Tuple[str, ...]:
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        if isinstance(prefix, str):
            toks = list(tokens(prefix))
        else:
            toks = [str(t) for t in prefix]
        width = max(0, self.order - 1)
        guard = 0
        while len(toks) < max(1, n) and guard < n + 8:
            guard += 1
            ctx = tuple(toks[-width:]) if width and toks else ()
            bucket = self.counts.get(ctx) if ctx else None
            dist: Dict[str, int] = dict(bucket) if bucket else dict(self.unigrams)
            dist = {w: c for w, c in dist.items() if w not in {START} and c > 0}
            if not dist:
                dist = {w: max(1, c) for w, c in self.unigrams.items() if w not in {START, END}}
            if not dist:
                break
            total = sum(dist.values())
            r = rng.randrange(max(1, total))
            acc = 0
            choice = next(iter(dist))
            for w, c in dist.items():
                acc += c
                if acc > r:
                    choice = w
                    break
            if choice == END:
                break
            toks.append(choice)
        return tuple(toks[:n] or toks)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "order": self.order,
            "total": self.total,
            "fitted": self.fitted,
            "unigrams": dict(self.unigrams),
            "counts": {"|".join(k): dict(v) for k, v in self.counts.items()},
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "NGramLM":
        lm = cls(order=int((data or {}).get("order") or 2),
                 vocab=((data or {}).get("unigrams") or {}).keys())
        lm.unigrams = {str(k): int(v) for k, v in ((data or {}).get("unigrams") or {}).items()}
        lm.total = int((data or {}).get("total") or 0)
        lm.fitted = int((data or {}).get("fitted") or 0)
        lm.counts = {}
        for k, bucket in ((data or {}).get("counts") or {}).items():
            ctx = tuple(str(k).split("|")) if str(k) else ()
            lm.counts[ctx] = {str(w): int(c) for w, c in (bucket or {}).items()}
        return lm


class LanguageModelBackend:
    """ModelPort wrapping an NGramLM. Small (order≤2) or medium (order≥3)."""

    def __init__(self, lm: NGramLM, *, slot: str, name: str = "ngram") -> None:
        self.lm = lm
        self.slot = slot
        self.name = name
        self.scale = "small" if lm.order <= 2 else "medium"

    def fit(self, text: str) -> int:
        return self.lm.fit([text])

    def snapshot(self) -> Dict[str, Any]:
        snap = self.lm.snapshot()
        snap["slot"] = self.slot
        snap["name"] = self.name
        snap["scale"] = self.scale
        return snap

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        if hasattr(self.lm, "generate"):
            return " ".join(self.lm.generate(stimulus or "", n=n))
        return (stimulus or "")[:160]

    def perplexity(self, texts) -> float:
        if hasattr(self.lm, "perplexity"):
            return float(self.lm.perplexity(texts))
        return float("inf")

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "LanguageModelBackend":
        lm = NGramLM.from_snapshot(data or {})
        sl = slot or str((data or {}).get("slot") or "pfc")
        return cls(lm, slot=sl, name=str((data or {}).get("name") or "imported-lm"))

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        text = stimulus or ""
        low = text.lower()
        if self.slot == "pfc":
            from skeleton.cortex.pfc import _VETO
            veto = any(v in low for v in _VETO) or not text.strip()
            if veto:
                return Thought(
                    slot="pfc", kind="plan",
                    text="INHIBIT: PFC veto. Not a builder act.",
                    confidence=0.95,
                    tags=("veto", "boilerplate", "small", "lm"),
                    numbers=(0.0, 1.0),
                )
        seed = int(fingerprint(text)[:8], 16) if text else 0
        gen = " ".join(self.lm.generate(text, n=18, seed=seed))
        if self.slot == "midbrain":
            from skeleton.cortex.midbrain import _weights
            arousal, lw, rw = _weights(text)
            to_left, to_right = lw >= 0.25, rw >= 0.25
            return Thought(
                slot="midbrain", kind="route",
                text=f"COORD {gen}",
                confidence=0.80,
                tags=("route", "coordinator", "medium", "lm")
                + (("left",) if to_left else ())
                + (("right",) if to_right else ()),
                numbers=(arousal, lw, rw),
            )
        kind = "plan" if self.slot == "pfc" else "lm"
        return Thought(
            slot=self.slot, kind=kind,
            text=gen or text[:160],
            confidence=0.70,
            tags=("lm", self.scale, self.slot),
            numbers=(float(self.lm.order), float(self.lm.fitted)),
        )
