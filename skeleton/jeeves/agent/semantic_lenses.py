"""Cross-domain semantic lenses for high-nuance Jeeves reasoning.

The runtime needs more than a single semantic similarity score.  Film editing,
literary narration, games, rhetoric, and cognitive science all contain useful
ways to ask *how context changes meaning*.  This module makes those ways of
looking explicit and typed.

A lens never upgrades an interpretation into evidence.  It proposes a reading,
a prediction, and possible tangent directions while retaining the observations
that activated it.  Multiple incompatible readings are preserved until later
evidence discriminates between them.

The catalog intentionally mixes old and modern ideas.  ``lineage_year`` is an
orientation marker for when a lens entered a recognizable intellectual lineage;
it is not a claim that the modern formulation was invented in that exact year.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .types import AgentContractError, bounded_text, json_safe, positive_int, probability, stable_fingerprint, stable_id

_TOKEN_RE = re.compile(r"[A-Za-z0-9_'-]+")


class LensFamily(str, Enum):
    FILM = "film"
    LITERATURE = "literature"
    GAME = "game"
    NARRATIVE = "narrative"
    SEMIOTIC = "semiotic"
    COGNITIVE = "cognitive"
    RHETORIC = "rhetoric"
    SOCIAL = "social"
    TEMPORAL = "temporal"
    SYSTEM = "system"


class SemanticRole(str, Enum):
    CONTEXTUALIZATION = "contextualization"
    PERSPECTIVE = "perspective"
    CONTRAST = "contrast"
    STRUCTURE = "structure"
    CAUSAL_HINT = "causal_hint"
    PREDICTION = "prediction"
    INTERPRETATION = "interpretation"
    ADVERSARIAL_READING = "adversarial_reading"
    PLAYER_MODEL = "player_model"
    META = "meta"


class ReadingStatus(str, Enum):
    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    FALSIFIED = "falsified"


@dataclass(frozen=True, slots=True)
class SemanticLensSpec:
    key: str
    family: LensFamily
    role: SemanticRole
    lineage_year: int
    description: str
    activation_cues: tuple[str, ...]
    asks: tuple[str, ...]
    predicts: str
    failure_mode: str
    minimum_observations: int = 1
    pairwise: bool = False
    sequential: bool = False
    rare: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", str(self.key).strip().casefold())
        if not self.key:
            raise AgentContractError("semantic lens requires key")
        if not isinstance(self.family, LensFamily):
            object.__setattr__(self, "family", LensFamily(str(self.family)))
        if not isinstance(self.role, SemanticRole):
            object.__setattr__(self, "role", SemanticRole(str(self.role)))
        if isinstance(self.lineage_year, bool) or not isinstance(self.lineage_year, int):
            raise AgentContractError("lineage_year must be integer")
        object.__setattr__(self, "description", bounded_text("lens description", self.description, maximum=4096))
        object.__setattr__(self, "activation_cues", tuple(sorted({str(x).casefold() for x in self.activation_cues if str(x).strip()})))
        object.__setattr__(self, "asks", tuple(str(x).strip() for x in self.asks if str(x).strip()))
        object.__setattr__(self, "predicts", bounded_text("predicts", self.predicts, maximum=2048))
        object.__setattr__(self, "failure_mode", bounded_text("failure_mode", self.failure_mode, maximum=2048))
        object.__setattr__(self, "minimum_observations", positive_int("minimum_observations", self.minimum_observations, maximum=1000))


@dataclass(frozen=True, slots=True)
class SemanticObservation:
    observation_id: str
    content: str
    position: int
    source: str = "runtime"
    tags: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.observation_id).strip():
            raise AgentContractError("semantic observation requires id")
        object.__setattr__(self, "content", bounded_text("observation content", self.content, maximum=32_000))
        if isinstance(self.position, bool) or not isinstance(self.position, int) or self.position < 0:
            raise AgentContractError("observation position must be non-negative integer")
        object.__setattr__(self, "source", bounded_text("observation source", self.source, maximum=512))
        object.__setattr__(self, "tags", tuple(sorted({str(x).casefold() for x in self.tags if str(x).strip()})))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "observation_id": self.observation_id,
                "content": self.content,
                "position": self.position,
                "source": self.source,
                "tags": self.tags,
                "evidence_ids": self.evidence_ids,
                "metadata": self.metadata,
            }
        )


@dataclass(frozen=True, slots=True)
class TangentSeed:
    seed_id: str
    parent_fingerprint: str
    lens_key: str
    direction: str
    rationale: str
    novelty: float
    expected_value: float
    evidence_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.seed_id).strip() or not str(self.parent_fingerprint).strip():
            raise AgentContractError("tangent seed requires ids")
        object.__setattr__(self, "lens_key", str(self.lens_key).strip().casefold())
        object.__setattr__(self, "direction", bounded_text("tangent direction", self.direction, maximum=4096))
        object.__setattr__(self, "rationale", bounded_text("tangent rationale", self.rationale, maximum=4096))
        object.__setattr__(self, "novelty", probability("tangent novelty", self.novelty))
        object.__setattr__(self, "expected_value", probability("tangent expected_value", self.expected_value))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "tags", tuple(sorted({str(x).casefold() for x in self.tags if str(x).strip()})))


@dataclass(frozen=True, slots=True)
class SemanticFinding:
    finding_id: str
    lens_key: str
    family: LensFamily
    observation_ids: tuple[str, ...]
    interpretation: str
    prediction: str
    confidence: float
    ambiguity: float
    novelty: float
    status: ReadingStatus = ReadingStatus.CANDIDATE
    evidence_ids: tuple[str, ...] = ()
    counterreading: str = ""
    tangent_seeds: tuple[TangentSeed, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.finding_id).strip():
            raise AgentContractError("semantic finding requires id")
        object.__setattr__(self, "lens_key", str(self.lens_key).strip().casefold())
        if not isinstance(self.family, LensFamily):
            object.__setattr__(self, "family", LensFamily(str(self.family)))
        observations = tuple(str(x) for x in self.observation_ids if str(x))
        if not observations:
            raise AgentContractError("semantic finding requires observations")
        object.__setattr__(self, "observation_ids", observations)
        object.__setattr__(self, "interpretation", bounded_text("interpretation", self.interpretation, maximum=16_000))
        object.__setattr__(self, "prediction", bounded_text("prediction", self.prediction, maximum=8_000, allow_empty=True))
        object.__setattr__(self, "counterreading", bounded_text("counterreading", self.counterreading, maximum=8_000, allow_empty=True))
        for name in ("confidence", "ambiguity", "novelty"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if not isinstance(self.status, ReadingStatus):
            object.__setattr__(self, "status", ReadingStatus(str(self.status)))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        if any(not isinstance(seed, TangentSeed) for seed in self.tangent_seeds):
            raise AgentContractError("tangent_seeds must contain TangentSeed values")
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "lens": self.lens_key,
                "family": self.family.value,
                "observations": self.observation_ids,
                "interpretation": self.interpretation,
                "prediction": self.prediction,
                "counterreading": self.counterreading,
                "evidence": self.evidence_ids,
            }
        )


@dataclass(frozen=True, slots=True)
class JuxtapositionSignal:
    left_id: str
    right_id: str
    lexical_overlap: float
    contrast_signal: float
    novelty_signal: float
    sequence_distance: int
    shared_tags: tuple[str, ...]
    changed_context: bool


class JuxtapositionAnalyzer:
    """Deterministic pair analysis before any model-generated interpretation.

    The analyzer does not claim to infer cinematic meaning.  It identifies the
    structural conditions under which a contextual/contrast reading is worth
    considering.  This keeps a Kuleshov-like effect separate from unsupported
    mind-reading.
    """

    NEGATION = frozenset({"not", "never", "no", "without", "fail", "failed", "opposite", "but", "however"})

    @staticmethod
    def _tokens(text: str) -> Counter[str]:
        return Counter(token.casefold() for token in _TOKEN_RE.findall(text or ""))

    @staticmethod
    def _cosine(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        dot = sum(count * right.get(token, 0) for token, count in left.items())
        ln = math.sqrt(sum(v * v for v in left.values()))
        rn = math.sqrt(sum(v * v for v in right.values()))
        return 0.0 if not ln or not rn else max(0.0, min(1.0, dot / (ln * rn)))

    @classmethod
    def compare(cls, left: SemanticObservation, right: SemanticObservation) -> JuxtapositionSignal:
        lt = cls._tokens(left.content)
        rt = cls._tokens(right.content)
        overlap = cls._cosine(lt, rt)
        left_neg = sum(lt.get(token, 0) for token in cls.NEGATION)
        right_neg = sum(rt.get(token, 0) for token in cls.NEGATION)
        negation_mismatch = min(1.0, abs(left_neg - right_neg) / 2.0)
        tag_left, tag_right = set(left.tags), set(right.tags)
        shared = tuple(sorted(tag_left & tag_right))
        tag_distance = 0.0
        if tag_left or tag_right:
            tag_distance = 1.0 - len(tag_left & tag_right) / max(1, len(tag_left | tag_right))
        contrast = min(1.0, 0.55 * (1.0 - overlap) + 0.25 * negation_mismatch + 0.20 * tag_distance)
        novelty = min(1.0, 0.7 * (1.0 - overlap) + 0.3 * tag_distance)
        return JuxtapositionSignal(
            left_id=left.observation_id,
            right_id=right.observation_id,
            lexical_overlap=overlap,
            contrast_signal=contrast,
            novelty_signal=novelty,
            sequence_distance=abs(right.position - left.position),
            shared_tags=shared,
            changed_context=bool(tag_distance > 0.3 or contrast > 0.45),
        )


@dataclass(frozen=True, slots=True)
class LensSelection:
    lenses: tuple[SemanticLensSpec, ...]
    activation_scores: Mapping[str, float]
    families: tuple[LensFamily, ...]
    perpendicular: bool


class SemanticLensRegistry:
    def __init__(self, specs: Iterable[SemanticLensSpec] = ()) -> None:
        self._specs: dict[str, SemanticLensSpec] = {}
        for spec in default_semantic_lenses():
            self.register(spec)
        for spec in specs:
            self.register(spec)

    def register(self, spec: SemanticLensSpec) -> None:
        if spec.key in self._specs:
            raise AgentContractError(f"duplicate semantic lens: {spec.key}")
        self._specs[spec.key] = spec

    def get(self, key: str) -> SemanticLensSpec:
        return self._specs[str(key).strip().casefold()]

    def all(self) -> tuple[SemanticLensSpec, ...]:
        return tuple(sorted(self._specs.values(), key=lambda x: (x.lineage_year, x.family.value, x.key)))

    def family(self, family: LensFamily) -> tuple[SemanticLensSpec, ...]:
        return tuple(spec for spec in self.all() if spec.family is family)


class SemanticLensRouter:
    """Select a diverse set of lenses instead of overfitting one interpretation."""

    def __init__(self, registry: SemanticLensRegistry | None = None) -> None:
        self.registry = registry or SemanticLensRegistry()

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token.casefold() for token in _TOKEN_RE.findall(text or "")}

    def select(
        self,
        observations: Sequence[SemanticObservation],
        *,
        requested: Sequence[str] = (),
        max_lenses: int = 12,
        max_per_family: int = 3,
        perpendicular: bool = True,
    ) -> LensSelection:
        max_lenses = positive_int("max_lenses", max_lenses, maximum=100)
        max_per_family = positive_int("max_per_family", max_per_family, maximum=20)
        if not observations:
            return LensSelection((), {}, (), perpendicular)
        tokens = set().union(*(self._tokens(item.content) | set(item.tags) for item in observations))
        requested_set = {str(x).casefold() for x in requested}
        scored: list[tuple[float, SemanticLensSpec]] = []
        for spec in self.registry.all():
            if len(observations) < spec.minimum_observations:
                continue
            cue_set = set(spec.activation_cues)
            cue_overlap = len(tokens & cue_set) / max(1, len(cue_set)) if cue_set else 0.0
            explicit = 1.0 if spec.key in requested_set else 0.0
            pair_bonus = 0.08 if spec.pairwise and len(observations) >= 2 else 0.0
            sequential_bonus = 0.08 if spec.sequential and len(observations) >= 3 else 0.0
            rarity_bonus = 0.04 if spec.rare else 0.0
            base = 0.18 + 0.56 * cue_overlap + 0.70 * explicit + pair_bonus + sequential_bonus + rarity_bonus
            scored.append((min(1.0, base), spec))
        scored.sort(key=lambda item: (-item[0], item[1].family.value, item[1].key))

        selected: list[SemanticLensSpec] = []
        family_counts: defaultdict[LensFamily, int] = defaultdict(int)
        if perpendicular:
            # First pass: one useful lens from as many independent families as possible.
            seen: set[LensFamily] = set()
            for score, spec in scored:
                if len(selected) >= max_lenses:
                    break
                if spec.family in seen:
                    continue
                selected.append(spec)
                seen.add(spec.family)
                family_counts[spec.family] += 1
        selected_keys = {spec.key for spec in selected}
        for score, spec in scored:
            if len(selected) >= max_lenses:
                break
            if spec.key in selected_keys or family_counts[spec.family] >= max_per_family:
                continue
            selected.append(spec)
            selected_keys.add(spec.key)
            family_counts[spec.family] += 1
        score_map = {spec.key: score for score, spec in scored if spec.key in selected_keys}
        return LensSelection(tuple(selected), score_map, tuple(sorted(family_counts, key=lambda x: x.value)), perpendicular)


@dataclass(frozen=True, slots=True)
class ReadingCluster:
    cluster_id: str
    finding_ids: tuple[str, ...]
    families: tuple[LensFamily, ...]
    confidence_range: tuple[float, float]
    contested: bool


class SemanticEnsemble:
    """Preserve plural readings; detect convergence without false averaging."""

    @staticmethod
    def cluster(findings: Sequence[SemanticFinding]) -> tuple[ReadingCluster, ...]:
        if not findings:
            return ()
        # Group by evidence/observation footprint, not by embedding guesses.  Meaning
        # equivalence belongs to a separate entailment-capable component.
        groups: defaultdict[tuple[str, ...], list[SemanticFinding]] = defaultdict(list)
        for finding in findings:
            groups[tuple(sorted(finding.observation_ids))].append(finding)
        result: list[ReadingCluster] = []
        for footprint, items in sorted(groups.items()):
            low = min(item.confidence for item in items)
            high = max(item.confidence for item in items)
            counterreadings = sum(bool(item.counterreading.strip()) for item in items)
            statuses = {item.status for item in items}
            contested = counterreadings > 0 or ReadingStatus.CONTESTED in statuses or ReadingStatus.FALSIFIED in statuses
            cluster_id = stable_id(
                "reading-cluster",
                {"footprint": footprint, "findings": sorted(item.fingerprint for item in items)},
                length=24,
            )
            result.append(
                ReadingCluster(
                    cluster_id,
                    tuple(sorted(item.finding_id for item in items)),
                    tuple(sorted({item.family for item in items}, key=lambda x: x.value)),
                    (low, high),
                    contested,
                )
            )
        return tuple(result)


def _lens(
    key: str,
    family: LensFamily,
    role: SemanticRole,
    year: int,
    description: str,
    cues: Sequence[str],
    asks: Sequence[str],
    predicts: str,
    failure: str,
    *,
    minimum: int = 1,
    pairwise: bool = False,
    sequential: bool = False,
    rare: bool = False,
) -> SemanticLensSpec:
    return SemanticLensSpec(key, family, role, year, description, tuple(cues), tuple(asks), predicts, failure, minimum, pairwise, sequential, rare)


def default_semantic_lenses() -> tuple[SemanticLensSpec, ...]:
    """A broad catalog spanning cinema, literature, games, and cognition."""

    return (
        # Film / editing / visual narrative.
        _lens("kuleshov_context", LensFamily.FILM, SemanticRole.CONTEXTUALIZATION, 1920, "Adjacent context can change interpretation of an otherwise ambiguous item.", ("before", "after", "scene", "face", "context", "adjacent", "sequence"), ("Would this item be read differently beside another?", "Is the middle context carrying affect or intent into the target?"), "A changed neighbor changes interpretation while the target stays constant.", "Attributing context-induced interpretation to the target as intrinsic fact.", minimum=2, pairwise=True),
        _lens("montage_collision", LensFamily.FILM, SemanticRole.CONTRAST, 1923, "Meaning can emerge from collision/contrast between shots or concepts rather than either item alone.", ("contrast", "collision", "cut", "opposite", "juxtaposition", "montage"), ("What third idea appears only when A and B are contrasted?",), "The joint sequence evokes a concept not explicit in either element.", "Inventing a synthetic meaning with no audience/context support.", minimum=2, pairwise=True),
        _lens("cross_cutting", LensFamily.FILM, SemanticRole.STRUCTURE, 1903, "Alternating streams imply relation, comparison, or simultaneity.", ("meanwhile", "parallel", "alternating", "simultaneous", "thread", "cut"), ("Do alternating threads imply temporal or causal linkage?",), "Changes in one thread alter expectations about the other.", "Assuming simultaneity from presentation order alone.", minimum=3, sequential=True),
        _lens("shot_reverse_shot", LensFamily.FILM, SemanticRole.PERSPECTIVE, 1910, "Alternating viewpoints construct relational perspective.", ("perspective", "view", "reply", "response", "back", "forth"), ("Whose viewpoint frames each observation?",), "Interpretation changes when viewpoint ownership changes.", "Confusing viewpoint with objective state.", minimum=2, pairwise=True),
        _lens("match_cut_analogy", LensFamily.FILM, SemanticRole.INTERPRETATION, 1920, "Formal similarity across a transition can imply analogy despite different content.", ("match", "similar", "shape", "echo", "transition", "parallel"), ("What structural feature survives the cut?",), "Shared form predicts an intended conceptual bridge.", "Mistaking coincidental similarity for semantic relation.", minimum=2, pairwise=True, rare=True),
        _lens("sound_image_counterpoint", LensFamily.FILM, SemanticRole.CONTRAST, 1928, "Different channels can deliberately disagree, producing irony or a second reading.", ("audio", "sound", "says", "shows", "music", "contradict"), ("Do channels reinforce or contradict each other?",), "Cross-channel mismatch predicts irony, unreliability, or reframing.", "Privileging one channel without evidence.", minimum=2, pairwise=True, rare=True),
        _lens("offscreen_negative_space", LensFamily.FILM, SemanticRole.PREDICTION, 1940, "What is deliberately absent/out of frame may structure expectation.", ("missing", "absent", "unseen", "offscreen", "silence", "gap"), ("What expected element is conspicuously absent?",), "An omitted but cued element may appear later or constrain interpretation.", "Treating every absence as intentional.", rare=True),
        _lens("mise_en_scene", LensFamily.FILM, SemanticRole.CONTEXTUALIZATION, 1940, "Arrangement, environment, props, and staging jointly frame interpretation.", ("setting", "prop", "layout", "background", "environment", "staging"), ("Which contextual elements repeatedly co-occur with this action?",), "Stable contextual arrangements predict role/affect associations.", "Over-reading incidental environmental details."),
        _lens("continuity_violation", LensFamily.FILM, SemanticRole.ADVERSARIAL_READING, 1915, "A break in established continuity can signal error, hidden transition, or deliberate emphasis.", ("continuity", "jump", "inconsistent", "suddenly", "mismatch", "changed"), ("Is the discontinuity an error, omitted event, or deliberate signal?",), "A verified discontinuity predicts missing state or changed regime.", "Calling every state change a continuity error.", minimum=2, pairwise=True),
        # Narrative / literary.
        _lens("focalization", LensFamily.NARRATIVE, SemanticRole.PERSPECTIVE, 1972, "Information is filtered by a perspective with bounded access.", ("knows", "sees", "thinks", "perspective", "view", "narrator"), ("Who has access to this information?", "What lies outside this perspective?"), "Predictions should be conditioned on what the focalizer can know.", "Treating filtered knowledge as omniscient fact."),
        _lens("unreliable_narrator", LensFamily.LITERATURE, SemanticRole.ADVERSARIAL_READING, 1961, "The reporting source may be sincere yet systematically mistaken, biased, or deceptive.", ("claims", "insists", "contradiction", "denies", "memory", "narrator"), ("What independent observations test the narrator?",), "Future independent evidence may diverge from narrated claims.", "Declaring unreliability from mere disagreement."),
        _lens("free_indirect_discourse", LensFamily.LITERATURE, SemanticRole.PERSPECTIVE, 1850, "Narrator and character voice can partially blend without explicit quotation.", ("thought", "felt", "surely", "obviously", "voice", "character"), ("Is evaluative language owned by narrator or character?",), "Apparent objective language may track one character's belief state.", "Attributing all stylistic language to a character.", rare=True),
        _lens("defamiliarization", LensFamily.LITERATURE, SemanticRole.INTERPRETATION, 1917, "An ordinary thing presented strangely can force renewed attention to hidden assumptions.", ("strange", "unusual", "as if", "ordinary", "unexpected", "alien"), ("What familiar assumption becomes visible when phrasing is made strange?",), "A re-description may reveal unnoticed constraints or affordances.", "Mistaking decorative novelty for analytic value.", rare=True),
        _lens("intertextuality", LensFamily.LITERATURE, SemanticRole.CONTEXTUALIZATION, 1966, "A text can gain meaning through relation to other texts/conventions.", ("reference", "echo", "quote", "allusion", "genre", "like"), ("Which prior pattern is being invoked or inverted?",), "Recognized source patterns alter likely intent/expectation.", "Hallucinating an allusion from weak resemblance.", rare=True),
        _lens("motif_recurrence", LensFamily.LITERATURE, SemanticRole.PREDICTION, 1900, "Repeated elements can accumulate thematic or predictive weight.", ("again", "repeat", "recurring", "motif", "same", "pattern"), ("Which element recurs across otherwise different contexts?",), "Recurrence increases the chance the element matters later.", "Frequency alone does not prove symbolic intent.", minimum=2, sequential=True),
        _lens("foreshadowing_payoff", LensFamily.NARRATIVE, SemanticRole.PREDICTION, 1800, "Early cues can constrain later plausible developments.", ("hint", "later", "promise", "setup", "payoff", "warning"), ("Which current detail would become diagnostic if a later event occurs?",), "A planted cue raises expectation of a related future event.", "Retrospective hindsight can manufacture false foreshadowing.", sequential=True),
        _lens("dramatic_irony", LensFamily.NARRATIVE, SemanticRole.PERSPECTIVE, 1750, "Different agents can possess different knowledge about the same situation.", ("doesn't know", "unknown", "audience", "secret", "believes", "actually"), ("Who knows what, and who incorrectly assumes shared knowledge?",), "Actions diverge because agents optimize under different beliefs.", "Assuming privileged observer knowledge is available to actors."),
        _lens("analepsis_prolepsis", LensFamily.TEMPORAL, SemanticRole.STRUCTURE, 1972, "Narrative order can differ from event order through retrospection or anticipation.", ("before", "earlier", "later", "future", "remembered", "flashback"), ("What is event time versus telling time?",), "Reordering restores causal/temporal dependencies hidden by narration.", "Forcing a chronology where order is genuinely uncertain.", sequential=True, rare=True),
        _lens("ellipsis_gap", LensFamily.NARRATIVE, SemanticRole.PREDICTION, 1900, "A meaningful gap can hide an event or leave underdetermination.", ("gap", "omitted", "missing", "skip", "between", "unknown"), ("What state transition is required between observed endpoints?",), "Candidate hidden events can be ranked by consistency with endpoints.", "Filling gaps with the most narratively satisfying rather than evidenced event.", minimum=2, pairwise=True),
        _lens("polyphony", LensFamily.LITERATURE, SemanticRole.INTERPRETATION, 1929, "Multiple voices can remain genuinely independent rather than collapsing to one authorial truth.", ("voices", "perspectives", "disagree", "dialogue", "multiple", "views"), ("Which voices retain independent assumptions and goals?",), "Persistent disagreement predicts multiple coherent interpretations.", "Prematurely averaging incompatible viewpoints.", rare=True),
        _lens("aporia_ambiguity", LensFamily.LITERATURE, SemanticRole.META, 1960, "Some ambiguity is structurally unresolved and should remain represented as such.", ("ambiguous", "unclear", "undecidable", "both", "neither", "unknown"), ("Is uncertainty removable with evidence or intrinsic to the representation?",), "The correct output may be a maintained set of readings.", "Treating all ambiguity as a failure to reason.", rare=True),
        _lens("genre_expectation", LensFamily.NARRATIVE, SemanticRole.PREDICTION, 1920, "Genre conventions act as priors over plausible structures and payoffs.", ("genre", "pattern", "convention", "typical", "trope", "formula"), ("Which convention supplies a prior, and what evidence would overturn it?",), "Convention changes prior odds but not factual evidence.", "Treating a trope as deterministic law."),
        # Games / interaction.
        _lens("mechanics_dynamics_aesthetics", LensFamily.GAME, SemanticRole.SYSTEM, 2004, "Separate rules/mechanics, emergent runtime dynamics, and experienced outcomes.", ("mechanic", "rule", "dynamic", "experience", "player", "system"), ("Is this property coded, emergent, or experienced?",), "Changing a mechanic predicts downstream dynamics and player experience, not one-to-one outcomes.", "Collapsing mechanics, dynamics, and aesthetics into one layer."),
        _lens("affordance_action", LensFamily.GAME, SemanticRole.PREDICTION, 1977, "Perceived action possibilities depend on agent capabilities and environment.", ("can", "action", "available", "afford", "control", "option"), ("What action does the state invite or permit for this actor?",), "Visible affordances predict likely attempted actions.", "Assuming perceived affordance equals actual capability."),
        _lens("ludonarrative_alignment", LensFamily.GAME, SemanticRole.CONTRAST, 2007, "Compare what the rules reward with what the narrative claims to value.", ("reward", "story", "mechanic", "narrative", "goal", "dissonance"), ("Do incentives and stated values align?",), "Misalignment predicts behavior that contradicts declared narrative intent.", "Treating any tension between play and story as design failure.", pairwise=True, rare=True),
        _lens("resource_economy", LensFamily.GAME, SemanticRole.CAUSAL_HINT, 1980, "Scarcity, sinks, sources, and exchange rates shape strategy.", ("resource", "cost", "scarce", "spend", "gain", "budget"), ("What is produced, consumed, hoarded, or bottlenecked?",), "Strategy shifts near scarcity thresholds and exchange-rate changes.", "Ignoring non-resource motivations."),
        _lens("fog_of_war_partial_observability", LensFamily.GAME, SemanticRole.PERSPECTIVE, 1980, "Players act on hidden-state beliefs, not the true full state.", ("hidden", "unknown", "fog", "observe", "partial", "belief"), ("What state is hidden and what observations update belief about it?",), "Actions reveal information as well as changing state.", "Evaluating decisions with hindsight/full-state information."),
        _lens("exploration_exploitation", LensFamily.GAME, SemanticRole.PREDICTION, 1933, "Actions trade immediate return against information about uncertain options.", ("explore", "try", "known", "unknown", "reward", "uncertain"), ("Is an action valuable because of outcome, information, or both?",), "Higher uncertainty can rationally increase exploratory actions.", "Exploration for novelty with no decision value."),
        _lens("opponent_modeling", LensFamily.GAME, SemanticRole.PLAYER_MODEL, 1944, "Predict another actor by maintaining hypotheses over strategy/type.", ("opponent", "player", "strategy", "bluff", "respond", "adversary"), ("What strategy class best predicts the actor's recent choices?",), "Posterior over opponent strategies predicts response distribution.", "Assuming stationary or perfectly rational opponents."),
        _lens("metagame", LensFamily.GAME, SemanticRole.META, 1970, "Behavior depends on beliefs about the population of strategies outside the immediate local state.", ("meta", "popular", "counter", "strategy", "community", "trend"), ("What strategies are common enough to shape counter-strategy?",), "Population shifts change locally optimal choices.", "Projecting a stale population meta into a new regime.", rare=True),
        _lens("branching_consequence", LensFamily.GAME, SemanticRole.PREDICTION, 1980, "Choices create path-dependent branches with delayed consequences.", ("choice", "branch", "consequence", "path", "later", "decision"), ("Which choice irreversibly changes reachable futures?",), "Branch-defining actions should be evaluated on reachable future sets, not immediate reward.", "Inventing branches not supported by transition rules."),
        _lens("save_load_counterfactual", LensFamily.GAME, SemanticRole.CAUSAL_HINT, 1980, "Replay from a shared state under alternative actions approximates controlled counterfactual comparison.", ("save", "load", "replay", "retry", "alternative", "same state"), ("Can the same starting state be replayed under another action?",), "Repeated controlled replays improve action-effect estimates.", "Treating simulator/replay behavior as external-world causal proof.", rare=True),
        _lens("emergence_vs_script", LensFamily.GAME, SemanticRole.SYSTEM, 1990, "Distinguish behavior produced by interacting rules from explicitly authored progression.", ("emergent", "script", "generated", "system", "rule", "event"), ("Was this outcome directly authored or generated by subsystem interaction?",), "Emergent outcomes vary under small state changes more than scripted beats.", "Calling complex scripted behavior emergent."),
        _lens("diegetic_interface", LensFamily.GAME, SemanticRole.PERSPECTIVE, 2000, "Some interface information exists within the represented world; other information is external/meta.", ("hud", "interface", "screen", "diegetic", "display", "indicator"), ("Does the actor know this value, or only the user/system?",), "Diegetic information can affect in-world actor beliefs; meta UI should not.", "Leaking privileged UI state into actor cognition.", rare=True),
        # General semantic/cognitive/rhetorical lenses.
        _lens("figure_ground", LensFamily.COGNITIVE, SemanticRole.CONTEXTUALIZATION, 1912, "Attention separates foreground target from background context.", ("foreground", "background", "focus", "salient", "attention", "context"), ("What is being treated as figure, and what disappears into ground?",), "Changing attentional framing changes retrieved/weighted features.", "Assuming salience equals importance."),
        _lens("gestalt_closure", LensFamily.COGNITIVE, SemanticRole.INTERPRETATION, 1920, "Observers tend to complete incomplete patterns.", ("incomplete", "pattern", "close", "missing", "shape", "complete"), ("What completion is being supplied rather than observed?",), "Missing elements may be inferred from a strong pattern prior.", "Mistaking perceptual completion for evidence.", rare=True),
        _lens("schema_violation", LensFamily.COGNITIVE, SemanticRole.PREDICTION, 1932, "A schema supplies expectations; violations create diagnostic prediction error.", ("expected", "unexpected", "schema", "normal", "surprise", "violation"), ("What expectation was violated, and is the schema wrong or the event unusual?",), "Repeated violations predict regime/schema revision.", "Over-updating from a single anomaly."),
        _lens("semiotic_signifier_signified", LensFamily.SEMIOTIC, SemanticRole.INTERPRETATION, 1916, "Separate observable sign form from the concept/convention it invokes.", ("symbol", "sign", "means", "label", "representation", "signal"), ("What is observed directly, and what meaning is conventionally assigned?",), "Meaning changes across communities even when sign stays fixed.", "Treating conventional meaning as intrinsic property.", rare=True),
        _lens("index_icon_symbol", LensFamily.SEMIOTIC, SemanticRole.CAUSAL_HINT, 1903, "Distinguish resemblance, causal/indexical linkage, and conventional symbolism.", ("resembles", "trace", "indicator", "symbol", "icon", "evidence"), ("Does the sign resemble, result from, or merely conventionally denote its object?",), "Indexical signs support different causal inferences than symbols/icons.", "Inferring causal linkage from symbolic association.", rare=True),
        _lens("framing_effect", LensFamily.COGNITIVE, SemanticRole.CONTEXTUALIZATION, 1981, "Equivalent choices can be evaluated differently under gain/loss framing.", ("gain", "loss", "frame", "wording", "risk", "choice"), ("Would an equivalent reframe change the apparent preference?",), "Preference instability under reframing predicts framing sensitivity.", "Calling any wording difference a cognitive bias."),
        _lens("grice_implicature", LensFamily.RHETORIC, SemanticRole.INTERPRETATION, 1975, "Speakers often convey meaning through cooperative inference beyond literal content.", ("imply", "hint", "why say", "literal", "answer", "relevant"), ("What would make this utterance relevant/informative in context?",), "Pragmatic context predicts intended implications beyond literal proposition.", "Inferring implicature when cooperation assumptions fail.", rare=True),
        _lens("rhetorical_contrast", LensFamily.RHETORIC, SemanticRole.CONTRAST, 350, "Antithesis/contrast highlights dimensions by placing alternatives together.", ("but", "rather", "whereas", "yet", "contrast", "instead"), ("Which dimension is made salient by the contrast?",), "Contrast predicts which attribute the speaker wants foregrounded.", "Treating rhetoric as proof of the contrasted claim.", pairwise=True),
        _lens("steelman_counterreading", LensFamily.SYSTEM, SemanticRole.ADVERSARIAL_READING, 2020, "Generate the strongest coherent alternative reading before committing.", ("alternative", "counter", "other", "maybe", "uncertain", "interpret"), ("What is the strongest incompatible explanation consistent with observations?",), "If a counterreading predicts different observations, it becomes a useful discriminator.", "Producing weak straw alternatives merely to look balanced."),
        _lens("semantic_entropy_cluster", LensFamily.SYSTEM, SemanticRole.META, 2024, "Group generations by meaning before estimating uncertainty over answers.", ("meaning", "equivalent", "paraphrase", "uncertainty", "entropy", "cluster"), ("Do diverse strings express the same proposition or genuinely different answers?",), "High meaning-level dispersion predicts semantic uncertainty/confabulation risk.", "Bad entailment clustering can manufacture or hide uncertainty."),
        _lens("counterfactual_narrative", LensFamily.NARRATIVE, SemanticRole.CAUSAL_HINT, 2000, "Alternate-story reasoning tests which events are structurally necessary for later outcomes.", ("if", "otherwise", "alternate", "counterfactual", "without", "changed"), ("If this event were removed, which later events would cease to follow?",), "Events whose removal changes downstream reachability are structurally important.", "Narrative necessity is not causal identification.", rare=True),
        _lens("perspective_inversion", LensFamily.SYSTEM, SemanticRole.ADVERSARIAL_READING, 2020, "Re-evaluate a state from another actor's goals, information, and constraints.", ("perspective", "other side", "user", "opponent", "stakeholder", "view"), ("What becomes rational under another actor's objective and information set?",), "Different objective/information sets predict different action choices.", "Projecting one's own utility function onto the other actor."),
        _lens("temporal_scale", LensFamily.TEMPORAL, SemanticRole.PREDICTION, 2000, "The same pattern can reverse meaning across short, medium, and long horizons.", ("short term", "long term", "later", "immediate", "trend", "horizon"), ("Does the conclusion survive a change in prediction horizon?",), "A locally useful action can have globally harmful delayed effects and vice versa.", "Mixing evidence measured at incompatible horizons."),
    )
