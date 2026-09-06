"""Prompt self-improvement — ImproveLoop over prefix-text variants (BACKLOG F-10).

Composes the generic :class:`~skeleton.intelligence.improve_loop.ImproveLoop`
with deterministic prefix-text mutations. Variants are scored by downstream
answer quality; optional F-2 ``feedback_stats`` (from
:class:`~skeleton.retrieval.plane_weights.PlaneWeightLearner`) provide a
bounded scoring boost when retrieval feedback looks healthy.

Pure domain: generator/evaluator stay callables so tests can fake them.
Does not rewrite ImproveLoop, VerificationLoop, Gate, WORM, lifespan,
blackboard, or outbox.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
)

from skeleton.intelligence.improve_loop import ImproveLoop, ImproveResult


# (incumbent, iteration) -> candidate
PrefixGeneratorFn = Callable[["PrefixVariant", int], "PrefixVariant"]
# candidate -> score (higher better)
QualityScorerFn = Callable[["PrefixVariant"], float]
# prefix variant -> downstream answer text (injected; production wires the LLM)
AnswerFn = Callable[["PrefixVariant"], str]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t]


@dataclass(frozen=True)
class PrefixVariant:
    """One candidate prefix-text body under a stable registry key."""

    key: str
    text: str
    generation: int = 0
    seed_used: Optional[int] = None

    @property
    def sha(self) -> str:
        return _content_hash(self.text)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "sha": self.sha,
            "generation": self.generation,
            "seed_used": self.seed_used,
            "chars": len(self.text),
            "text": self.text,
        }


def mutate_prefix(variant: PrefixVariant, *, seed: int = 0) -> PrefixVariant:
    """Deterministic, bounded prefix-text mutation under ``seed``.

    Same ``(variant.text, seed)`` always yields the same child text. Mutation
    families (selected by ``seed % 5``):

      0. whitespace normalize
      1. swap first/last sentence (when >= 2 sentences)
      2. append a short clarity cue (chosen from a fixed table)
      3. move a mid-clause marker ("Also," / "Importantly,") to the front
      4. drop a duplicated consecutive word if present; else trim trailing space

    Always returns a new :class:`PrefixVariant` (never mutates ``variant``).
    """
    rng = random.Random(int(seed))
    family = int(seed) % 5
    text = variant.text
    cues = (
        " Be precise.",
        " Prefer questions before answers.",
        " Keep cognitive load moderate.",
        " Cite uncertainty when unsure.",
    )

    if family == 0:
        new_text = " ".join(text.split())
    elif family == 1:
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
        if len(parts) >= 2:
            parts = [parts[-1]] + parts[:-1]
            new_text = " ".join(parts)
        else:
            new_text = " ".join(text.split())
    elif family == 2:
        cue = cues[rng.randrange(len(cues))]
        base = text.rstrip()
        new_text = base if base.endswith(cue.strip()) else (base + cue)
    elif family == 3:
        markers = ("Also,", "Importantly,", "Remember:")
        marker = markers[rng.randrange(len(markers))]
        stripped = text.strip()
        if stripped.startswith(marker):
            new_text = stripped
        else:
            new_text = f"{marker} {stripped}"
    else:
        tokens = text.split()
        cleaned: List[str] = []
        for tok in tokens:
            if cleaned and cleaned[-1].lower() == tok.lower():
                continue
            cleaned.append(tok)
        new_text = " ".join(cleaned) if cleaned else text.strip()

    if new_text == variant.text:
        # Guarantee a visible, still-deterministic delta for the loop.
        new_text = (variant.text.rstrip() + f" [{seed & 0xFFFF:04x}]").strip()

    return PrefixVariant(
        key=variant.key,
        text=new_text,
        generation=variant.generation + 1,
        seed_used=int(seed),
    )


def _feedback_boost(feedback_stats: Optional[Mapping[str, Any]], *, weight: float = 0.15) -> float:
    """Bounded boost from F-2 learner stats (mean Laplace plane rate)."""
    if not feedback_stats or weight <= 0:
        return 0.0
    rates = feedback_stats.get("rates")
    if not isinstance(rates, Mapping) or not rates:
        return 0.0
    vals = [float(v) for v in rates.values()]
    if not vals:
        return 0.0
    mean_rate = sum(vals) / len(vals)
    # Cold prior is ~0.5; boost only when feedback looks better than prior.
    return max(0.0, min(weight, (mean_rate - 0.5) * 2.0 * weight))


def answer_quality_score(
    answer: str,
    *,
    reference: Optional[str] = None,
    feedback_stats: Optional[Mapping[str, Any]] = None,
    feedback_boost: float = 0.15,
) -> float:
    """Score downstream answer quality in ``[0, 1]``.

    Base heuristic (no LLM): non-empty length band + optional token overlap
    with ``reference``. When ``feedback_stats`` from an F-2
    :meth:`~skeleton.retrieval.plane_weights.PlaneWeightLearner.stats` call
    is supplied, a bounded boost is applied so healthy retrieval feedback
    can tip close races.
    """
    if not answer or not str(answer).strip():
        return 0.0

    text = str(answer).strip()
    tokens = _tokenize(text)
    # Length band: prefer ~20–400 tokens; soft penalties outside.
    n = len(tokens)
    if n == 0:
        length_score = 0.0
    elif n < 5:
        length_score = 0.25
    elif n < 20:
        length_score = 0.55
    elif n <= 400:
        length_score = 0.85
    else:
        length_score = 0.65

    if reference:
        ref_toks = set(_tokenize(reference))
        ans_toks = set(tokens)
        if not ref_toks:
            overlap = 0.0
        else:
            overlap = len(ref_toks & ans_toks) / len(ref_toks)
        base = 0.35 * length_score + 0.65 * overlap
    else:
        # Structure cues without a reference.
        has_sentence = bool(re.search(r"[.!?]", text))
        structure = 0.15 if has_sentence else 0.0
        base = min(1.0, length_score + structure)

    boosted = min(1.0, base + _feedback_boost(feedback_stats, weight=feedback_boost))
    return round(boosted, 6)


@dataclass
class PromptImproveResult:
    """ImproveLoop result plus driver metadata."""

    result: ImproveResult
    best_variant: Optional[PrefixVariant] = None
    feedback_boost_applied: bool = False

    @property
    def best_score(self) -> float:
        return self.result.best_score

    @property
    def stopped_reason(self) -> str:
        return self.result.stopped_reason

    def to_dict(self) -> Dict[str, Any]:
        out = self.result.to_dict()
        out["feedback_boost_applied"] = self.feedback_boost_applied
        if self.best_variant is not None:
            out["best"] = self.best_variant.to_dict()
        return out


class PromptImproveDriver:
    """Drive :class:`ImproveLoop` over :class:`PrefixVariant` mutations (F-10)."""

    def __init__(
        self,
        *,
        loop: Optional[ImproveLoop] = None,
        feedback_stats: Optional[Mapping[str, Any]] = None,
        answer_fn: Optional[AnswerFn] = None,
        reference: Optional[str] = None,
        generate: Optional[PrefixGeneratorFn] = None,
        scores: Optional[Mapping[str, float]] = None,
    ) -> None:
        self.loop = loop or ImproveLoop(max_iterations=8, patience=3)
        self.feedback_stats = dict(feedback_stats) if feedback_stats else None
        self.answer_fn = answer_fn
        self.reference = reference
        self.generate = generate or self._default_generate
        self._scores = dict(scores or {})
        self.runs = 0

    @staticmethod
    def _default_generate(incumbent: PrefixVariant, iteration: int) -> PrefixVariant:
        # Mix iteration + incumbent sha so each step is stable but distinct.
        seed = (iteration * 1_000_003) ^ (int(incumbent.sha[:8], 16) & 0xFFFFFFFF)
        return mutate_prefix(incumbent, seed=seed)

    def record_score(self, variant: PrefixVariant, score: float) -> None:
        """Record a measured answer-quality score for ``variant.sha``."""
        self._scores[variant.sha] = float(score)

    def evaluate(self, variant: PrefixVariant) -> float:
        """Score a variant via recorded scores, answer_fn, or text fallback."""
        if variant.sha in self._scores:
            base = self._scores[variant.sha]
            return min(
                1.0,
                base + _feedback_boost(self.feedback_stats),
            )

        if self.answer_fn is not None:
            answer = self.answer_fn(variant)
            return answer_quality_score(
                answer,
                reference=self.reference,
                feedback_stats=self.feedback_stats,
            )

        # Fallback: treat the prefix body itself as a stand-in answer so the
        # loop remains usable in pure unit tests without an LLM.
        return answer_quality_score(
            variant.text,
            reference=self.reference,
            feedback_stats=self.feedback_stats,
        )

    def improve(self, seed: PrefixVariant) -> PromptImproveResult:
        """Run the bounded ImproveLoop starting from ``seed``."""
        self.runs += 1
        result = self.loop.run(seed, self.generate, self.evaluate)
        best = result.best
        if not isinstance(best, PrefixVariant):
            raise TypeError("ImproveLoop best must be a PrefixVariant")
        return PromptImproveResult(
            result=result,
            best_variant=best,
            feedback_boost_applied=bool(self.feedback_stats),
        )


def improve_prefix_prompt(
    seed: PrefixVariant,
    *,
    loop: Optional[ImproveLoop] = None,
    feedback_stats: Optional[Mapping[str, Any]] = None,
    answer_fn: Optional[AnswerFn] = None,
    reference: Optional[str] = None,
    scores: Optional[Mapping[str, float]] = None,
) -> PromptImproveResult:
    """Convenience one-shot wrapper around :class:`PromptImproveDriver`."""
    driver = PromptImproveDriver(
        loop=loop,
        feedback_stats=feedback_stats,
        answer_fn=answer_fn,
        reference=reference,
        scores=scores,
    )
    return driver.improve(seed)
