"""Prefix self-improvement — ImproveLoop over prefix-text variants (BACKLOG F-10).

Composes the generic :class:`~skeleton.intelligence.improve_loop.ImproveLoop`
with :mod:`skeleton.memory.prefix_renderer`. A seed of prefix segments is
mutated into small deterministic text variants; an injected quality scorer
(or a thin F-2 feedback / plane-weight adapter) decides which survive.
On improvement the best prefix can be registered on a
:class:`~skeleton.memory.prefix_renderer.PrefixRegistry`.

Pure domain: generator/evaluator stay callables so tests can fake them.
Does not rewrite ImproveLoop's core contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from skeleton.intelligence.improve_loop import ImproveLoop, ImproveResult
from skeleton.memory.prefix_renderer import (
    CAGPrefix,
    PrefixRegistry,
    PrefixSegment,
    build_prefix,
)


# (incumbent variant, iteration) -> candidate variant
PrefixGeneratorFn = Callable[["PrefixVariant", int], "PrefixVariant"]
# candidate -> score (higher better)
QualityScorerFn = Callable[["PrefixVariant"], float]


@dataclass(frozen=True)
class PrefixVariant:
    """One scored candidate over a prefix key + segment bodies."""

    key: str
    segments: Tuple[PrefixSegment, ...]

    @property
    def prefix(self) -> CAGPrefix:
        return build_prefix(self.key, self.segments)

    @property
    def text(self) -> str:
        return self.prefix.text

    @property
    def sha(self) -> str:
        return self.prefix.sha

    def to_dict(self) -> Dict[str, Any]:
        p = self.prefix
        return {
            "key": self.key,
            "sha": p.sha,
            "tokens": p.tokens,
            "segments": [
                {
                    "name": s.name,
                    "text": s.text,
                    "cache_breakpoint": s.cache_breakpoint,
                }
                for s in self.segments
            ],
        }


def seed_from_segments(
    key: str,
    segments: Iterable[PrefixSegment],
) -> PrefixVariant:
    """Build a seed variant from ordered segments."""
    segs = tuple(segments)
    if not segs:
        raise ValueError("seed requires at least one PrefixSegment")
    return PrefixVariant(key=key, segments=segs)


def _jeeves_segments() -> Tuple[PrefixSegment, ...]:
    from skeleton.memory.prefix_renderer import (
        JEEVES_LEARNING_STAGES_TEXT,
        JEEVES_PERSONA_TEXT,
        JEEVES_SYSTEM_LAWS_TEXT,
    )

    return (
        PrefixSegment("persona", JEEVES_PERSONA_TEXT, cache_breakpoint=True),
        PrefixSegment("system_laws", JEEVES_SYSTEM_LAWS_TEXT),
        PrefixSegment("learning_stages", JEEVES_LEARNING_STAGES_TEXT),
    )


def seed_from_renderer(
    renderer: Any,
    *,
    key: Optional[str] = None,
) -> PrefixVariant:
    """Seed from a PrefixRenderer's current system prefix.

    Uses the canonical Jeeves segment bodies when the key matches the
    renderer default; otherwise wraps registry text as a single segment so
    the loop can still mutate.
    """
    prefix_key = key or getattr(renderer, "JEEVES_SYSTEM_KEY", "jeeves:system")
    jeeves_key = getattr(renderer, "JEEVES_SYSTEM_KEY", "jeeves:system")
    if prefix_key == jeeves_key:
        return seed_from_segments(prefix_key, _jeeves_segments())

    existing = None
    if hasattr(renderer, "registry"):
        existing = renderer.registry.get(prefix_key)
    if existing is not None and existing.text:
        return seed_from_segments(
            prefix_key,
            [PrefixSegment("body", existing.text.rstrip())],
        )
    raise ValueError(f"cannot seed prefix for key={prefix_key!r}")


def _with_text(seg: PrefixSegment, text: str) -> PrefixSegment:
    return PrefixSegment(
        name=seg.name, text=text, cache_breakpoint=seg.cache_breakpoint
    )


def mutate_prefix_variant(
    incumbent: PrefixVariant,
    iteration: int,
    *,
    candidates: Optional[Mapping[str, Sequence[str]]] = None,
) -> PrefixVariant:
    """Deterministic, bounded prefix mutations for tests and offline tuning.

    Mutation families (cycled by ``iteration``):
      1. rotate segment order left by one
      2. rotate segment order right by one
      3. inject next candidate body for a named segment (if ``candidates`` given)
      4. light rephrase: move last sentence of the longest body to the front
      5. normalize internal whitespace on all bodies

    Always returns a new :class:`PrefixVariant` (never mutates ``incumbent``).
    """
    segs = list(incumbent.segments)
    n = len(segs)
    family = ((iteration - 1) % 5) + 1

    if family == 1 and n > 1:
        segs = segs[1:] + segs[:1]
    elif family == 2 and n > 1:
        segs = segs[-1:] + segs[:-1]
    elif family == 3 and candidates:
        names = [s.name for s in segs if s.name in candidates and candidates[s.name]]
        if names:
            target = names[(iteration - 1) % len(names)]
            alts = list(candidates[target])
            pick = alts[(iteration - 1) % len(alts)]
            segs = [_with_text(s, pick) if s.name == target else s for s in segs]
        else:
            segs = [_with_text(s, " ".join(s.text.split())) for s in segs]
    elif family == 4:
        idx = max(range(n), key=lambda i: len(segs[i].text))
        body = segs[idx].text.strip()
        parts = [
            p.strip()
            for p in body.replace("?", ".").replace("!", ".").split(".")
            if p.strip()
        ]
        if len(parts) >= 2:
            rotated = parts[-1:] + parts[:-1]
            new_body = ". ".join(rotated)
            if body.endswith((".", "!", "?")):
                new_body += "."
            segs[idx] = _with_text(segs[idx], new_body)
        else:
            segs[idx] = _with_text(segs[idx], body)
    else:
        segs = [_with_text(s, " ".join(s.text.split())) for s in segs]

    return PrefixVariant(key=incumbent.key, segments=tuple(segs))


def default_prefix_generator(
    candidates: Optional[Mapping[str, Sequence[str]]] = None,
) -> PrefixGeneratorFn:
    """Factory for the deterministic mutator used by :class:`PrefixImprover`."""

    def generate(incumbent: PrefixVariant, iteration: int) -> PrefixVariant:
        return mutate_prefix_variant(incumbent, iteration, candidates=candidates)

    return generate


@dataclass
class AnswerQualitySignal:
    """Thin store for downstream answer-quality scores keyed by prefix sha.

    Tests inject scores directly. Production can feed HTTP feedback / plane
    outcomes through :meth:`record` or :func:`adapt_plane_learner`.
    """

    _scores: Dict[str, List[float]] = field(default_factory=dict)
    records: int = 0

    def record(self, prefix_sha: str, score: float) -> None:
        self._scores.setdefault(prefix_sha, []).append(float(score))
        self.records += 1

    def mean(self, prefix_sha: str, default: float = 0.0) -> float:
        vals = self._scores.get(prefix_sha)
        if not vals:
            return float(default)
        return sum(vals) / len(vals)

    def scorer(self, *, default: float = 0.0) -> QualityScorerFn:
        def score(variant: PrefixVariant) -> float:
            return self.mean(variant.sha, default=default)

        return score


def adapt_plane_learner(
    learner: Any,
    *,
    signal: Optional[AnswerQualitySignal] = None,
    default: float = 0.5,
) -> QualityScorerFn:
    """Thin F-2 adapter: blend mean plane win-rates with optional answer scores.

    When ``signal`` has observations for a variant's sha, those dominate.
    Otherwise falls back to the learner's mean plane ``rate`` (Laplace-smoothed
    win rate from :class:`~skeleton.retrieval.plane_weights.PlaneWeightLearner`),
    or ``default`` if no learner/stats are available.
    """

    def _plane_mean() -> float:
        if learner is None:
            return default
        stats = learner.stats() if hasattr(learner, "stats") else None
        if not isinstance(stats, dict):
            return default
        rates = stats.get("rates") or {}
        if not rates:
            return default
        vals = [float(v) for v in rates.values()]
        return sum(vals) / len(vals) if vals else default

    def score(variant: PrefixVariant) -> float:
        if signal is not None and variant.sha in signal._scores:
            return signal.mean(variant.sha, default=default)
        return _plane_mean()

    return score


@dataclass
class PrefixImproveResult:
    """ImproveLoop result plus optional registry side-effect metadata."""

    result: ImproveResult
    registered: bool = False
    best_variant: Optional[PrefixVariant] = None

    @property
    def best_score(self) -> float:
        return self.result.best_score

    @property
    def stopped_reason(self) -> str:
        return self.result.stopped_reason

    def to_dict(self) -> Dict[str, Any]:
        out = self.result.to_dict()
        out["registered"] = self.registered
        if self.best_variant is not None:
            out["best"] = self.best_variant.to_dict()
        return out


class PrefixImprover:
    """Focused prefix-improvement surface over :class:`ImproveLoop`."""

    def __init__(
        self,
        *,
        loop: Optional[ImproveLoop] = None,
        registry: Optional[PrefixRegistry] = None,
        generate: Optional[PrefixGeneratorFn] = None,
        candidates: Optional[Mapping[str, Sequence[str]]] = None,
        register_on_improve: bool = True,
    ) -> None:
        self.loop = loop or ImproveLoop(max_iterations=8, patience=3)
        self.registry = registry
        self.generate = generate or default_prefix_generator(candidates)
        self.register_on_improve = register_on_improve
        self.runs = 0

    def improve(
        self,
        seed: PrefixVariant,
        evaluate: QualityScorerFn,
    ) -> PrefixImproveResult:
        """Run the bounded loop; optionally register the best prefix."""
        self.runs += 1
        seed_score = evaluate(seed)
        result = self.loop.run(seed, self.generate, evaluate)
        best = result.best
        if not isinstance(best, PrefixVariant):
            raise TypeError("ImproveLoop best must be a PrefixVariant")

        registered = False
        improved = result.best_score > seed_score
        if self.register_on_improve and self.registry is not None:
            if improved or self.registry.get(seed.key) is None:
                self.registry.register(best.prefix)
                registered = True

        return PrefixImproveResult(
            result=result,
            registered=registered,
            best_variant=best,
        )


def improve_prefix(
    seed: PrefixVariant,
    evaluate: QualityScorerFn,
    *,
    loop: Optional[ImproveLoop] = None,
    registry: Optional[PrefixRegistry] = None,
    generate: Optional[PrefixGeneratorFn] = None,
    candidates: Optional[Mapping[str, Sequence[str]]] = None,
    register_on_improve: bool = True,
) -> PrefixImproveResult:
    """Convenience one-shot wrapper around :class:`PrefixImprover`."""
    improver = PrefixImprover(
        loop=loop,
        registry=registry,
        generate=generate,
        candidates=candidates,
        register_on_improve=register_on_improve,
    )
    return improver.improve(seed, evaluate)
