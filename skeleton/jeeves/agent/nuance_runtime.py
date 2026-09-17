"""Integrated nuance runtime for Jeeves.

This module is the orchestration seam between fast/deep context retrieval,
semantic lenses, typed uncertainty, predictive calibration, and restart-safe
perpendicular exploration.

Ordering is a correctness property:

1. Resolve the current query against *pre-existing* context.
2. Convert the current query + retrieved context into provenance-bearing semantic
   observations.
3. Select diverse lenses and uncertainty contracts.
4. Only after resolution, capture the current user interaction into the L0 card
   index for future turns.
5. Validate model-proposed findings against registered lenses and observation
   provenance before they can enter composition/prediction.
6. Keep semantic predictions provisional and score them only against later
   observations.
7. Preserve unresolved readings as tangent frontier state before restart/replan.

Step 1 before step 4 prevents a pathological self-hit where the current prompt
would be mistaken for prior memory and satisfy the fast context path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .associative_memory import AssociationKind, SequencePrediction
from .cognition import ContextCompiler, ContextPacket, ContextSection, RunScratchpad
from .context_pipeline import ContextResolution, ContextTier, LayeredContextResolver
from .memory import MemoryNamespace
from .memory_game import InteractionCard
from .semantic_frontier import FrontierLensRouter, FrontierSemanticRegistry, LensCompositionEngine, SemanticComposition
from .semantic_lenses import (
    JuxtapositionAnalyzer,
    JuxtapositionSignal,
    LensFamily,
    LensSelection,
    SemanticFinding,
    SemanticObservation,
    TangentSeed,
)
from .semantic_prediction import SemanticForecast, SemanticPredictionLedger, SemanticPredictiveModel
from .semantic_tangent_bridge import SemanticRestartPacket, SemanticTangentBridge
from .tangent_graph import ExplorationAxis, TangentNode
from .types import (
    AgentContractError,
    Goal,
    Plan,
    PlanStep,
    ToolObservation,
    bounded_text,
    canonical_json,
    json_safe,
    positive_int,
    probability,
    stable_fingerprint,
    stable_id,
)
from .uncertainty_frontier import FrontierLens, FrontierLensContract, FrontierLensRegistry


class NuanceRuntimeError(AgentContractError):
    pass


@dataclass(frozen=True, slots=True)
class UncertaintyRecommendation:
    lens: FrontierLens
    reason: str
    priority: float
    contract: FrontierLensContract

    def __post_init__(self) -> None:
        if not isinstance(self.lens, FrontierLens):
            object.__setattr__(self, "lens", FrontierLens(str(self.lens)))
        priority = float(self.priority)
        if not 0.0 <= priority <= 1.0:
            raise NuanceRuntimeError("uncertainty recommendation priority must lie in [0,1]")
        object.__setattr__(self, "priority", priority)


@dataclass(frozen=True, slots=True)
class NuanceFrame:
    frame_id: str
    query: str
    namespace_key: str
    context: ContextResolution
    observations: tuple[SemanticObservation, ...]
    lens_selection: LensSelection
    uncertainty_recommendations: tuple[UncertaintyRecommendation, ...]
    captured_card_id: str | None
    fingerprint: str
    juxtaposition_signals: tuple[JuxtapositionSignal, ...] = ()
    sequence_prediction: SequencePrediction | None = None


@dataclass(frozen=True, slots=True)
class NuanceUpdate:
    frame_id: str
    findings: tuple[SemanticFinding, ...]
    composition: SemanticComposition
    forecasts: tuple[SemanticForecast, ...]
    tangent_nodes: tuple[TangentNode, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class NuanceRuntimePolicy:
    max_lenses: int = 18
    max_lenses_per_family: int = 4
    minimum_rare_lenses_when_supported: int = 2
    maximum_uncertainty_recommendations: int = 8
    link_recent_cards: int = 2
    max_perpendicular_tangents: int = 8
    minimum_perpendicular_activation: float = 0.34
    capture_interactions: bool = True
    preserve_perpendicular_before_restart: bool = True
    require_selected_lens_for_findings: bool = False
    require_observation_provenance: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_lenses",
            "max_lenses_per_family",
            "minimum_rare_lenses_when_supported",
            "maximum_uncertainty_recommendations",
            "link_recent_cards",
            "max_perpendicular_tangents",
        ):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1000))
        object.__setattr__(
            self,
            "minimum_perpendicular_activation",
            probability("minimum_perpendicular_activation", self.minimum_perpendicular_activation),
        )



_FAMILY_AXIS: dict[LensFamily, ExplorationAxis] = {
    LensFamily.FILM: ExplorationAxis.CINEMATIC,
    LensFamily.LITERATURE: ExplorationAxis.LITERARY,
    LensFamily.GAME: ExplorationAxis.LUDIC,
    LensFamily.NARRATIVE: ExplorationAxis.SEMANTIC,
    LensFamily.SEMIOTIC: ExplorationAxis.SEMANTIC,
    LensFamily.COGNITIVE: ExplorationAxis.MEMORY,
    LensFamily.RHETORIC: ExplorationAxis.SEMANTIC,
    LensFamily.SOCIAL: ExplorationAxis.SOCIAL,
    LensFamily.TEMPORAL: ExplorationAxis.TEMPORAL,
    LensFamily.SYSTEM: ExplorationAxis.SYSTEM,
}


class FrontierUncertaintyRouter:
    """Cue-based contract router; it selects semantics, not numeric answers.

    The router never computes a probability by guessing a lens.  It recommends
    explicit contracts whose assumptions can then be checked by the caller.
    """

    _GROUPS: tuple[tuple[tuple[str, ...], tuple[FrontierLens, ...], str, float], ...] = (
        (("memory", "remember", "recall", "forget", "cue", "interference"),
         (FrontierLens.MEMORY_FORGETTING_HAZARD, FrontierLens.MEMORY_CUE_COMPETITION, FrontierLens.MEMORY_INTERFERENCE),
         "memory retrieval may depend on decay and competing traces", 0.92),
        (("dice", "die", "roll"),
         (FrontierLens.HETEROGENEOUS_DICE,),
         "exact finite chance mechanics are available", 0.98),
        (("card", "deck", "draw", "without replacement"),
         (FrontierLens.HYPERGEOMETRIC_GAME,),
         "sampling without replacement needs a hypergeometric model", 0.97),
        (("game", "board", "state", "reach", "hitting"),
         (FrontierLens.MARKOV_HITTING_PROBABILITY,),
         "state transitions may support an explicit hitting-probability model", 0.82),
        (("opponent", "bluff", "strategy", "player type"),
         (FrontierLens.BAYESIAN_OPPONENT_MODEL,),
         "strategic behavior can be represented as posterior uncertainty over explicit opponent models", 0.87),
        (("online", "sequential", "anytime", "stop", "stopping", "stream"),
         (FrontierLens.E_VALUE, FrontierLens.ANYTIME_CONFIDENCE_SEQUENCE, FrontierLens.PREQUENTIAL_SCORE),
         "adaptive inspection/stopping calls for time-aware inference rather than fixed-sample reuse", 0.94),
        (("missing", "unidentified", "identified", "bounds", "partial"),
         (FrontierLens.PARTIAL_IDENTIFICATION, FrontierLens.MANSKI_BOUNDS, FrontierLens.CREDAL_SET),
         "the data may justify a set/bounds rather than a false point estimate", 0.95),
        (("shift", "drift", "deployment", "distribution", "domain"),
         (FrontierLens.COVARIATE_SHIFT, FrontierLens.LABEL_SHIFT, FrontierLens.CONCEPT_SHIFT),
         "source and target regimes may differ in distinct ways", 0.90),
        (("rare", "extreme", "tail", "catastrophic"),
         (FrontierLens.RARE_EVENT_IMPORTANCE_SAMPLING, FrontierLens.EXTREME_VALUE_TAIL, FrontierLens.IMPORTANCE_WEIGHT_ESS),
         "rare events need explicit tail/sampling diagnostics", 0.92),
        (("causal", "intervention", "transport", "confound", "mediator", "spillover"),
         (FrontierLens.CAUSAL_SENSITIVITY, FrontierLens.TRANSPORTABILITY, FrontierLens.MEDIATION_EFFECTS, FrontierLens.INTERFERENCE_SPILLOVER),
         "causal claims require identification and transport/interference assumptions to remain visible", 0.91),
        (("dependence", "correlation", "joint", "mutual", "copula"),
         (FrontierLens.MUTUAL_INFORMATION_DEPENDENCE, FrontierLens.COPULA_DEPENDENCE),
         "joint dependence can remain after marginal probabilities are specified", 0.84),
        (("categorical", "class", "multinomial"),
         (FrontierLens.DIRICHLET_MULTINOMIAL,),
         "categorical outcomes support an explicit posterior predictive model", 0.78),
        (("success", "failure", "binary", "bernoulli"),
         (FrontierLens.BETA_BINOMIAL_PREDICTIVE,),
         "binary rates can retain parameter uncertainty in posterior prediction", 0.76),
    )

    def __init__(self, registry: FrontierLensRegistry | None = None) -> None:
        self.registry = registry or FrontierLensRegistry()

    def recommend(self, text: str, *, limit: int = 8) -> tuple[UncertaintyRecommendation, ...]:
        content = str(text).casefold()
        limit = positive_int("uncertainty recommendation limit", limit, maximum=100)
        scores: dict[FrontierLens, tuple[float, str]] = {}
        for cues, lenses, reason, priority in self._GROUPS:
            matches = sum(1 for cue in cues if cue in content)
            if matches <= 0:
                continue
            support = min(1.0, priority + 0.02 * max(0, matches - 1))
            for lens in lenses:
                prior = scores.get(lens)
                if prior is None or support > prior[0]:
                    scores[lens] = (support, reason)
        # Always retain a calibration lens when an explicit probability/forecast
        # question is present.  Calibration is about predictive performance, not
        # another interpretation of probability.
        if any(cue in content for cue in ("probability", "forecast", "predict", "chance", "confidence")):
            scores.setdefault(
                FrontierLens.DECISION_WEIGHTED_CALIBRATION,
                (0.72, "probabilistic predictions should be checked where downstream decisions actually matter"),
            )
        recommendations = [
            UncertaintyRecommendation(lens, reason, priority, self.registry.get(lens))
            for lens, (priority, reason) in scores.items()
        ]
        recommendations.sort(key=lambda item: (-item.priority, item.lens.value))
        return tuple(recommendations[:limit])


class ScientificNuanceRuntime:
    """High-level evidence boundary for context -> nuance -> prediction."""

    def __init__(
        self,
        resolver: LayeredContextResolver,
        *,
        semantic_registry: FrontierSemanticRegistry | None = None,
        semantic_router: FrontierLensRouter | None = None,
        composition_engine: LensCompositionEngine | None = None,
        predictive_model: SemanticPredictiveModel | None = None,
        prediction_ledger: SemanticPredictionLedger | None = None,
        tangent_bridge: SemanticTangentBridge | None = None,
        uncertainty_router: FrontierUncertaintyRouter | None = None,
        policy: NuanceRuntimePolicy | None = None,
    ) -> None:
        if not isinstance(resolver, LayeredContextResolver):
            raise TypeError("resolver must be LayeredContextResolver")
        self.resolver = resolver
        self.semantic_registry = semantic_registry or FrontierSemanticRegistry()
        self.semantic_router = semantic_router or FrontierLensRouter(self.semantic_registry)
        self.composition_engine = composition_engine or LensCompositionEngine()
        self.predictive_model = predictive_model or SemanticPredictiveModel()
        self.prediction_ledger = prediction_ledger or SemanticPredictionLedger()
        self.tangent_bridge = tangent_bridge or SemanticTangentBridge()
        self.uncertainty_router = uncertainty_router or FrontierUncertaintyRouter()
        self.policy = policy or NuanceRuntimePolicy()
        self._frames: dict[str, NuanceFrame] = {}
        self._updates: dict[str, NuanceUpdate] = {}

    @staticmethod
    def _observation_from_context(item: Any, position: int) -> SemanticObservation:
        return SemanticObservation(
            observation_id=f"context:{item.item_id}",
            content=item.content,
            position=position,
            source=item.source,
            tags=(item.tier.name.casefold(), "retrieved-context"),
            evidence_ids=item.evidence_ids,
            metadata={
                "context_item_id": item.item_id,
                "context_tier": int(item.tier),
                "score": item.score,
                "trust": item.trust,
                "confidence": item.confidence,
            },
        )

    def prepare(
        self,
        namespace: MemoryNamespace,
        query: str,
        *,
        context_tags: Sequence[str] = (),
        requested_lenses: Sequence[str] = (),
        capture_interaction: bool | None = None,
        interaction_provenance: Sequence[str] = (),
        interaction_metadata: Mapping[str, Any] | None = None,
    ) -> NuanceFrame:
        if not isinstance(namespace, MemoryNamespace):
            raise TypeError("namespace must be MemoryNamespace")
        query = bounded_text("nuance query", query, maximum=32_000)

        # Correctness boundary: resolve before capturing the current interaction.
        # Snapshot recent cards first so the newly captured prompt cannot become
        # its own predecessor in temporal/sequence memory.
        recent_preexisting = self.resolver.cards.store.namespace_cards(namespace)[: self.policy.link_recent_cards]
        context = self.resolver.resolve(namespace, query, context_tags=context_tags)
        query_observation_id = stable_id(
            "semantic-current-input",
            {"namespace": namespace.key, "query": query},
            length=28,
        )
        observations: list[SemanticObservation] = [
            SemanticObservation(
                observation_id=query_observation_id,
                content=query,
                position=0,
                source="current-user-input",
                tags=("current-input", *tuple(context_tags)),
                evidence_ids=(),
                metadata={"authoritative_current_input": True, "is_memory": False},
            )
        ]
        observations.extend(
            self._observation_from_context(item, position)
            for position, item in enumerate(context.items, start=1)
        )
        # Structural juxtaposition is measured before any model-generated
        # interpretation.  It identifies where context/contrast lenses deserve
        # attention without claiming what the juxtaposition means.
        juxtaposition_signals = tuple(
            JuxtapositionAnalyzer.compare(left, right)
            for left, right in zip(observations, observations[1:])
        )

        selection = self.semantic_router.select_frontier(
            observations,
            requested=requested_lenses,
            max_lenses=self.policy.max_lenses,
            max_per_family=self.policy.max_lenses_per_family,
            minimum_rare_when_supported=self.policy.minimum_rare_lenses_when_supported,
        )
        uncertainty = self.uncertainty_router.recommend(
            " ".join([query, *(item.content for item in context.items[:8])]),
            limit=self.policy.maximum_uncertainty_recommendations,
        )

        # Sequence prediction is read from pre-existing traces only.  The
        # current input cannot leak into a prediction about itself.
        sequence_prediction: SequencePrediction | None = None
        if self.resolver.associations is not None and recent_preexisting:
            prefix = tuple(card.card_id for card in reversed(recent_preexisting))
            candidate_prediction = self.resolver.associations.predict_next(namespace, prefix, limit=8)
            if candidate_prediction.evidence_count > 0:
                sequence_prediction = candidate_prediction

        should_capture = self.policy.capture_interactions if capture_interaction is None else bool(capture_interaction)
        captured: InteractionCard | None = None
        if should_capture:
            captured = self.resolver.cards.capture_interaction(
                namespace,
                query,
                context_tags=context_tags,
                source="user-interaction",
                trust=1.0,
                salience=0.72,
                provenance=interaction_provenance,
                metadata={
                    "captured_after_context_resolution": True,
                    "context_fingerprint": context.fingerprint,
                    **dict(interaction_metadata or {}),
                },
            )
            if self.resolver.associations is not None and recent_preexisting:
                previous_ids = tuple(card.card_id for card in reversed(recent_preexisting))
                self.resolver.associations.observe_sequence(
                    namespace,
                    (*previous_ids, captured.card_id),
                    kind=AssociationKind.TEMPORAL_FORWARD,
                    evidence_ids=interaction_provenance,
                    tags=context_tags,
                )

                # A structural context shift can be indexed as a candidate
                # relation, but never as proof that interpretation changed.
                previous = recent_preexisting[0]
                structural = JuxtapositionAnalyzer.compare(
                    SemanticObservation(
                        observation_id=previous.card_id,
                        content=previous.content,
                        position=0,
                        source=previous.source,
                        tags=previous.context_tags,
                        evidence_ids=previous.provenance,
                    ),
                    SemanticObservation(
                        observation_id=captured.card_id,
                        content=captured.content,
                        position=1,
                        source=captured.source,
                        tags=captured.context_tags,
                        evidence_ids=captured.provenance,
                    ),
                )
                if structural.changed_context or structural.contrast_signal >= 0.35:
                    self.resolver.associations.observe(
                        namespace,
                        previous.card_id,
                        captured.card_id,
                        kind=AssociationKind.CONTEXT_SHIFT,
                        strength=min(1.0, 0.35 + 0.45 * structural.contrast_signal + 0.20 * structural.novelty_signal),
                        success=None,
                        surprise=structural.novelty_signal,
                        direction_confidence=0.55,
                        evidence_ids=interaction_provenance,
                        tags=(*tuple(context_tags), "structural-context-shift"),
                        metadata={
                            "structural_probe": True,
                            "interpretation_change_not_asserted": True,
                            "juxtaposition_left": structural.left_id,
                            "juxtaposition_right": structural.right_id,
                        },
                    )

        frame_id = stable_id(
            "nuance-frame",
            {
                "namespace": namespace.key,
                "query": query,
                "context": context.fingerprint,
                "observations": [item.observation_id for item in observations],
                "lenses": [item.key for item in selection.lenses],
            },
            length=32,
        )
        fingerprint = stable_fingerprint(
            {
                "frame_id": frame_id,
                "context": context.fingerprint,
                "observations": [item.fingerprint for item in observations],
                "lenses": [item.key for item in selection.lenses],
                "uncertainty": [item.lens.value for item in uncertainty],
                "juxtaposition": [
                    (
                        item.left_id,
                        item.right_id,
                        round(item.contrast_signal, 10),
                        round(item.novelty_signal, 10),
                        item.changed_context,
                    )
                    for item in juxtaposition_signals
                ],
                "sequence_prediction": sequence_prediction.fingerprint if sequence_prediction is not None else None,
                "captured_card": captured.card_id if captured else None,
            }
        )
        frame = NuanceFrame(
            frame_id=frame_id,
            query=query,
            namespace_key=namespace.key,
            context=context,
            observations=tuple(observations),
            lens_selection=selection,
            uncertainty_recommendations=uncertainty,
            captured_card_id=captured.card_id if captured else None,
            fingerprint=fingerprint,
            juxtaposition_signals=juxtaposition_signals,
            sequence_prediction=sequence_prediction,
        )
        self._frames[frame_id] = frame
        return frame

    def _validate_findings(self, frame: NuanceFrame, findings: Sequence[SemanticFinding]) -> tuple[SemanticFinding, ...]:
        observations = {item.observation_id: item for item in frame.observations}
        selected = {item.key for item in frame.lens_selection.lenses}
        registered = {item.key for item in self.semantic_registry.all()}
        evidence_by_observation = {
            observation_id: set(item.evidence_ids) for observation_id, item in observations.items()
        }
        validated: list[SemanticFinding] = []
        seen_ids: set[str] = set()
        for finding in findings:
            if not isinstance(finding, SemanticFinding):
                raise TypeError("findings must contain SemanticFinding values")
            if finding.finding_id in seen_ids:
                raise NuanceRuntimeError(f"duplicate semantic finding id: {finding.finding_id}")
            seen_ids.add(finding.finding_id)
            if finding.lens_key not in registered:
                raise NuanceRuntimeError(f"finding uses unregistered lens: {finding.lens_key}")
            if self.policy.require_selected_lens_for_findings and finding.lens_key not in selected:
                raise NuanceRuntimeError(f"finding uses lens not selected for frame: {finding.lens_key}")
            unknown_observations = set(finding.observation_ids) - set(observations)
            if unknown_observations:
                raise NuanceRuntimeError(
                    "finding cites observations outside its nuance frame: " + ",".join(sorted(unknown_observations))
                )
            if self.policy.require_observation_provenance and finding.evidence_ids:
                allowed_evidence: set[str] = set()
                for observation_id in finding.observation_ids:
                    allowed_evidence.update(evidence_by_observation.get(observation_id, ()))
                invented = set(finding.evidence_ids) - allowed_evidence
                if invented:
                    raise NuanceRuntimeError(
                        "semantic finding cites evidence not carried by its observations: " + ",".join(sorted(invented))
                    )
            validated.append(finding)
        return tuple(validated)

    def register_findings(
        self,
        frame: NuanceFrame,
        findings: Sequence[SemanticFinding],
        *,
        sequence: int,
    ) -> NuanceUpdate:
        if not isinstance(frame, NuanceFrame):
            raise TypeError("frame must be NuanceFrame")
        stored = self._frames.get(frame.frame_id)
        if stored is None or stored.fingerprint != frame.fingerprint:
            raise NuanceRuntimeError("unknown or mutated nuance frame")
        sequence = int(sequence)
        if sequence < 0:
            raise NuanceRuntimeError("sequence must be non-negative")
        validated = self._validate_findings(frame, findings)
        composition = self.composition_engine.compose(validated)
        forecasts = self.predictive_model.propose(validated, composition=composition)
        for forecast in forecasts:
            self.prediction_ledger.add(forecast)
        tangents = self.tangent_bridge.ingest(
            validated,
            composition=composition,
            root_fingerprint=frame.fingerprint,
            sequence=sequence,
        )
        fingerprint = stable_fingerprint(
            {
                "frame": frame.fingerprint,
                "findings": [item.fingerprint for item in validated],
                "composition": composition.fingerprint,
                "forecasts": [item.fingerprint for item in forecasts],
                "tangents": [item.fingerprint for item in tangents],
            }
        )
        update = NuanceUpdate(
            frame_id=frame.frame_id,
            findings=validated,
            composition=composition,
            forecasts=forecasts,
            tangent_nodes=tangents,
            fingerprint=fingerprint,
        )
        self._updates[frame.frame_id] = update
        return update

    def _preserve_perpendicular_lens_tangents(self, frame: NuanceFrame, *, sequence: int) -> tuple[TangentNode, ...]:
        """Persist one active research direction per lens family before restart.

        Lens activation is not a semantic finding.  These nodes therefore carry
        no evidence and remain high-evidence-gap research directions.
        """
        if not self.policy.preserve_perpendicular_before_restart:
            return ()
        scores = frame.lens_selection.activation_scores
        best_by_family: dict[LensFamily, Any] = {}
        for spec in frame.lens_selection.lenses:
            score = float(scores.get(spec.key, 0.0))
            if score < self.policy.minimum_perpendicular_activation:
                continue
            current = best_by_family.get(spec.family)
            if current is None or (score, spec.key) > (float(scores.get(current.key, 0.0)), current.key):
                best_by_family[spec.family] = spec

        ranked = sorted(
            best_by_family.values(),
            key=lambda spec: (-float(scores.get(spec.key, 0.0)), spec.family.value, spec.key),
        )[: self.policy.max_perpendicular_tangents]
        nodes: list[TangentNode] = []
        for spec in ranked:
            score = float(scores.get(spec.key, 0.0))
            direction = spec.asks[0] if spec.asks else spec.predicts
            seed = TangentSeed(
                seed_id=stable_id(
                    "nuance-pre-restart",
                    {"frame": frame.fingerprint, "lens": spec.key, "family": spec.family.value},
                    length=28,
                ),
                parent_fingerprint=frame.fingerprint,
                lens_key=spec.key,
                direction=direction,
                rationale=(
                    "Perpendicular lens direction preserved before restart/replan. "
                    "Activation is a routing signal, not evidence or a semantic finding."
                ),
                novelty=min(1.0, 0.55 + (0.20 if spec.rare else 0.0) + 0.25 * score),
                expected_value=min(1.0, 0.35 + 0.55 * score),
                evidence_ids=(),
                tags=("nuance-runtime", "pre-restart", "interpretive-only", spec.family.value),
            )
            nodes.append(
                self.tangent_bridge.graph.add_seed(
                    seed,
                    axis=_FAMILY_AXIS.get(spec.family, ExplorationAxis.SEMANTIC),
                    family=spec.family,
                    sequence=sequence,
                    trigger_terms=(spec.key, *spec.activation_cues[:8]),
                    risk=0.05,
                    evidence_gap=0.90,
                )
            )
        return tuple(nodes)

    def checkpoint_before_restart(self, frame_id: str, *, sequence: int, notes: str = "nuance checkpoint before restart") -> SemanticRestartPacket:
        frame = self._frames.get(str(frame_id))
        if frame is None:
            raise NuanceRuntimeError("unknown nuance frame")
        update = self._updates.get(frame.frame_id)
        self._preserve_perpendicular_lens_tangents(frame, sequence=sequence)
        return self.tangent_bridge.restart_packet(
            root_fingerprint=frame.fingerprint,
            sequence=sequence,
            findings=update.findings if update else (),
            composition=update.composition if update else None,
            prediction_ids=tuple(item.forecast_id for item in update.forecasts) if update else (),
            notes=notes,
        )

    def resolve_forecast(
        self,
        forecast_id: str,
        *,
        outcome: bool,
        observation_id: str | None = None,
    ) -> SemanticForecast:
        return self.prediction_ledger.resolve(
            forecast_id,
            outcome=outcome,
            observation_id=observation_id,
        )

    def frame(self, frame_id: str) -> NuanceFrame | None:
        return self._frames.get(str(frame_id))

    def update(self, frame_id: str) -> NuanceUpdate | None:
        return self._updates.get(str(frame_id))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "frames": [(key, value.fingerprint) for key, value in sorted(self._frames.items())],
                "updates": [(key, value.fingerprint) for key, value in sorted(self._updates.items())],
                "prediction_ledger": self.prediction_ledger.fingerprint,
                "tangent_graph": self.tangent_bridge.graph.fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class ScientificContextCompilerPolicy:
    """Prompt-facing bounds for the scientific nuance workbench."""

    maximum_nuance_chars: int = 20_000
    maximum_juxtapositions: int = 12
    maximum_lens_questions: int = 3
    context_priority: int = 68

    def __post_init__(self) -> None:
        for name in (
            "maximum_nuance_chars",
            "maximum_juxtapositions",
            "maximum_lens_questions",
            "context_priority",
        ):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1_000_000))


class ScientificContextCompiler:
    """Runtime-compatible compiler that makes the nuance stack operational.

    The public compile contract matches ContextCompiler and returns a plain
    ContextPacket. Existing runtime code therefore keeps one control path.

    Retrieval and interpretation remain separated. The resolver decides what
    prior context is worth surfacing; the nuance runtime selects questions and
    lenses but cannot create evidence; the base compiler performs final bounded
    prompt packing.

    This compiler is read-only with respect to interaction memory. Capturing a
    new user interaction is a separate method so the host can guarantee that the
    first retrieval for a turn happens before that turn becomes memory.
    """

    def __init__(
        self,
        resolver: LayeredContextResolver,
        *,
        nuance: ScientificNuanceRuntime | None = None,
        base_compiler: ContextCompiler | None = None,
        policy: ScientificContextCompilerPolicy | None = None,
    ) -> None:
        if not isinstance(resolver, LayeredContextResolver):
            raise TypeError("resolver must be LayeredContextResolver")
        self.resolver = resolver
        self.nuance = nuance or ScientificNuanceRuntime(resolver)
        if self.nuance.resolver is not resolver:
            raise NuanceRuntimeError("nuance runtime and scientific compiler must share one resolver")
        self.base = base_compiler or ContextCompiler()
        self.policy = policy or ScientificContextCompilerPolicy()

    @staticmethod
    def _query(task_instruction: str, goal: Goal, current_step: PlanStep | None) -> str:
        parts = [goal.objective, task_instruction]
        if current_step is not None:
            parts.extend(
                (
                    current_step.title,
                    current_step.description,
                    current_step.expected_outcome,
                )
            )
        return " ".join(part for part in parts if part)

    @staticmethod
    def _context_tags(
        goal: Goal,
        plan: Plan | None,
        current_step: PlanStep | None,
    ) -> tuple[str, ...]:
        tags = {"scientific-context", "jeeves"}
        if current_step is not None:
            tags.update(("current-step", current_step.risk.value))
            if current_step.tool:
                tags.add(f"tool:{current_step.tool}")
        if plan is not None:
            tags.add(f"plan-version:{plan.version}")
        for key in ("domain", "task", "mode"):
            value = goal.metadata.get(key)
            if isinstance(value, str) and value.strip():
                tags.add(value.strip().casefold()[:128])
        return tuple(sorted(tags))

    def _workbench_section(self, frame: NuanceFrame) -> ContextSection:
        lens_rows = [
            {
                "key": spec.key,
                "family": spec.family.value,
                "role": spec.role.value,
                "lineage_year": spec.lineage_year,
                "activation": round(
                    float(frame.lens_selection.activation_scores.get(spec.key, 0.0)),
                    8,
                ),
                "rare": spec.rare,
                "questions": list(spec.asks[: self.policy.maximum_lens_questions]),
                "predicts": spec.predicts,
                "failure_mode": spec.failure_mode,
            }
            for spec in frame.lens_selection.lenses
        ]
        uncertainty_rows = [
            {
                "lens": item.lens.value,
                "priority": round(item.priority, 8),
                "reason": item.reason,
                "quantity": item.contract.quantity.value,
                "lineage_year": item.contract.lineage_year,
                "use_when": item.contract.use_when,
                "invalid_when": item.contract.invalid_when,
                "assumptions": list(item.contract.assumptions),
                "implementation": item.contract.implementation.value,
            }
            for item in frame.uncertainty_recommendations
        ]
        juxtaposition_rows = [
            {
                "left": item.left_id,
                "right": item.right_id,
                "lexical_overlap": round(item.lexical_overlap, 8),
                "contrast": round(item.contrast_signal, 8),
                "novelty": round(item.novelty_signal, 8),
                "distance": item.sequence_distance,
                "changed_context": item.changed_context,
            }
            for item in frame.juxtaposition_signals[: self.policy.maximum_juxtapositions]
        ]
        payload: dict[str, Any] = {
            "contract": {
                "interpretive_only": True,
                "semantic_readings_are_not_evidence": True,
                "associations_change_priority_not_trust": True,
                "uncertainty_lenses_require_their_stated_assumptions": True,
                "conflicting_readings_must_not_be_averaged_implicitly": True,
                "predictions_must_be_falsifiable_and_scored_later": True,
            },
            "frame_id": frame.frame_id,
            "frame_fingerprint": frame.fingerprint,
            "context_fingerprint": frame.context.fingerprint,
            "lenses": lens_rows,
            "uncertainty": uncertainty_rows,
            "juxtaposition": juxtaposition_rows,
            "sequence_prediction": None
            if frame.sequence_prediction is None
            else {
                "prefix": list(frame.sequence_prediction.prefix),
                "candidates": [list(item) for item in frame.sequence_prediction.candidates],
                "entropy_bits": frame.sequence_prediction.entropy_bits,
                "evidence_count": frame.sequence_prediction.evidence_count,
                "fingerprint": frame.sequence_prediction.fingerprint,
            },
        }
        encoded = canonical_json(payload)
        if len(encoded) > self.policy.maximum_nuance_chars:
            payload["lenses"] = [
                {
                    "key": row["key"],
                    "family": row["family"],
                    "role": row["role"],
                    "activation": row["activation"],
                    "rare": row["rare"],
                }
                for row in lens_rows
            ]
            payload["uncertainty"] = [
                {
                    "lens": row["lens"],
                    "priority": row["priority"],
                    "quantity": row["quantity"],
                    "lineage_year": row["lineage_year"],
                }
                for row in uncertainty_rows
            ]
            payload["truncated_detail"] = True
            encoded = canonical_json(payload)
        if len(encoded) > self.policy.maximum_nuance_chars:
            encoded = canonical_json(
                {
                    "contract": payload["contract"],
                    "frame_id": frame.frame_id,
                    "frame_fingerprint": frame.fingerprint,
                    "context_fingerprint": frame.context.fingerprint,
                    "lens_keys": [item.key for item in frame.lens_selection.lenses],
                    "uncertainty_lenses": [
                        item.lens.value for item in frame.uncertainty_recommendations
                    ],
                    "truncated_detail": True,
                }
            )
        return ContextSection(
            name="scientific_nuance_workbench",
            content=encoded,
            priority=self.policy.context_priority,
            required=False,
            source_ids=(frame.fingerprint,),
        )

    def compile(
        self,
        *,
        system_instruction: str,
        task_instruction: str,
        goal: Goal,
        namespace: MemoryNamespace,
        memory: Any,
        evidence: Any,
        plan: Plan | None = None,
        current_step: PlanStep | None = None,
        observations: Sequence[ToolObservation] = (),
        scratchpad: RunScratchpad | None = None,
        extra_sections: Sequence[ContextSection] = (),
    ) -> ContextPacket:
        if memory is not self.resolver.memory:
            raise NuanceRuntimeError(
                "scientific context compiler must share the runtime MemoryManager; "
                "split memory planes would make retrieval/replay non-deterministic"
            )
        frame = self.nuance.prepare(
            namespace,
            self._query(task_instruction, goal, current_step),
            context_tags=self._context_tags(goal, plan, current_step),
            capture_interaction=False,
        )
        layered = frame.context.sections(maximum_chars=self.resolver.policy.max_total_chars)
        workbench = self._workbench_section(frame)
        return self.base.compile(
            system_instruction=system_instruction,
            task_instruction=task_instruction,
            goal=goal,
            namespace=namespace,
            memory=memory,
            evidence=evidence,
            plan=plan,
            current_step=current_step,
            observations=observations,
            scratchpad=scratchpad,
            extra_sections=tuple(layered) + (workbench,) + tuple(extra_sections),
        )

    def capture_user_interaction(
        self,
        namespace: MemoryNamespace,
        content: str,
        *,
        context_tags: Sequence[str] = (),
        provenance: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> InteractionCard:
        """Capture after first-turn resolution and wire temporal continuity."""
        recent = self.resolver.cards.store.namespace_cards(namespace)[:2]
        card = self.resolver.cards.capture_interaction(
            namespace,
            content,
            context_tags=context_tags,
            source="user-interaction",
            trust=1.0,
            salience=0.72,
            provenance=provenance,
            metadata={
                "captured_by_scientific_context_compiler": True,
                **dict(metadata or {}),
            },
        )
        if self.resolver.associations is not None and recent:
            previous_ids = tuple(
                item.card_id
                for item in reversed(recent)
                if item.card_id != card.card_id
            )
            if previous_ids:
                self.resolver.associations.observe_sequence(
                    namespace,
                    (*previous_ids, card.card_id),
                    kind=AssociationKind.TEMPORAL_FORWARD,
                    evidence_ids=provenance,
                    tags=context_tags,
                )
        return card

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "resolver_policy": self.resolver.policy,
                "nuance": self.nuance.fingerprint,
                "base_budget": self.base.budget,
                "policy": self.policy,
            }
        )
