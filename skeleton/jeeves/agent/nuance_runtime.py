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

from .context_pipeline import ContextResolution, LayeredContextResolver
from .memory import MemoryNamespace
from .memory_game import InteractionCard
from .perpendicular_semantics import PerpendicularExpansionPlan, PerpendicularExpansionPlanner
from .relational_memory import RelationKind, RelationTrace, SequenceObservation
from .semantic_frontier import FrontierLensRouter, FrontierSemanticRegistry, LensCompositionEngine, SemanticComposition
from .semantic_lenses import LensSelection, SemanticFinding, SemanticObservation
from .semantic_prediction import SemanticForecast, SemanticPredictionLedger, SemanticPredictiveModel
from .semantic_tangent_bridge import SemanticRestartPacket, SemanticTangentBridge
from .tangent_graph import TangentNode
from .types import AgentContractError, bounded_text, json_safe, positive_int, stable_fingerprint, stable_id
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
    relation_sequence: SequenceObservation | None = None


@dataclass(frozen=True, slots=True)
class NuanceUpdate:
    frame_id: str
    findings: tuple[SemanticFinding, ...]
    composition: SemanticComposition
    forecasts: tuple[SemanticForecast, ...]
    tangent_nodes: tuple[TangentNode, ...]
    fingerprint: str
    perpendicular_plan: PerpendicularExpansionPlan | None = None
    relational_hypothesis_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NuanceRuntimePolicy:
    max_lenses: int = 18
    max_lenses_per_family: int = 4
    minimum_rare_lenses_when_supported: int = 2
    maximum_uncertainty_recommendations: int = 8
    capture_interactions: bool = True
    require_selected_lens_for_findings: bool = False
    require_observation_provenance: bool = True

    def __post_init__(self) -> None:
        for name in (
            "max_lenses",
            "max_lenses_per_family",
            "minimum_rare_lenses_when_supported",
            "maximum_uncertainty_recommendations",
        ):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1000))


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
        perpendicular_planner: PerpendicularExpansionPlanner | None = None,
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
        self.perpendicular_planner = perpendicular_planner or PerpendicularExpansionPlanner(self.semantic_registry)
        self.policy = policy or NuanceRuntimePolicy()
        self._frames: dict[str, NuanceFrame] = {}
        self._updates: dict[str, NuanceUpdate] = {}
        # Streaming chronology is deliberately separate from card timestamps:
        # re-exposure updates an existing card timestamp and must not rewrite
        # interaction order. Only the last two ids are needed for pair/triad
        # learning; durable relation traces remain in the relational index.
        self._recent_cards: dict[str, tuple[str, ...]] = {}

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

        should_capture = self.policy.capture_interactions if capture_interaction is None else bool(capture_interaction)
        captured: InteractionCard | None = None
        relation_sequence: SequenceObservation | None = None
        if should_capture:
            prior_cards = self._recent_cards.get(namespace.key, ())
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
                    "prior_card_ids": prior_cards,
                    **dict(interaction_metadata or {}),
                },
            )
            if self.resolver.relations is not None:
                # Prequential invariant: context was resolved before the card
                # existed; the previous->current transition is scored before it
                # is learned by observe_stream_step.
                relation_sequence = self.resolver.relations.observe_stream_step(
                    namespace,
                    captured.card_id,
                    previous_card_ids=prior_cards,
                    context_tags=context_tags,
                    provenance=interaction_provenance,
                )
            self._recent_cards[namespace.key] = (*prior_cards[-1:], captured.card_id)

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
                "captured_card": captured.card_id if captured else None,
                "relation_sequence": relation_sequence.fingerprint if relation_sequence else None,
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
            relation_sequence=relation_sequence,
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

    def _bridge_findings_to_relations(
        self,
        frame: NuanceFrame,
        findings: Sequence[SemanticFinding],
    ) -> tuple[RelationTrace, ...]:
        """Store validated pairwise readings as non-authoritative relation hypotheses."""

        relations = self.resolver.relations
        if relations is None or frame.captured_card_id is None:
            return ()
        captured_card = self.resolver.cards.store.get(frame.captured_card_id)
        if captured_card is None:
            # A bounded fast-memory store may evict a card between prepare()
            # and model-returned finding registration. Never reconstruct or
            # guess an evicted identity from semantic text.
            return ()

        observation_to_card: dict[str, str] = {}
        for observation in frame.observations:
            if observation.source == "current-user-input":
                observation_to_card[observation.observation_id] = frame.captured_card_id
                continue
            item_id = str(observation.metadata.get("context_item_id", ""))
            if item_id and self.resolver.cards.store.get(item_id) is not None:
                observation_to_card[observation.observation_id] = item_id

        created: list[RelationTrace] = []
        namespace = captured_card.namespace
        for finding in findings:
            spec = self.semantic_registry.get(finding.lens_key)
            if not spec.pairwise:
                continue
            card_ids = tuple(
                dict.fromkeys(
                    observation_to_card[observation_id]
                    for observation_id in finding.observation_ids
                    if observation_id in observation_to_card
                )
            )
            if len(card_ids) != 2 or card_ids[0] == card_ids[1]:
                continue

            if spec.role.value == "contrast":
                kind = RelationKind.CONTRAST
            elif spec.role.value == "causal_hint":
                kind = RelationKind.CAUSAL_CANDIDATE
            elif "reversal" in spec.key:
                kind = RelationKind.REVERSAL
            elif "reinforc" in spec.key:
                kind = RelationKind.REINFORCEMENT
            else:
                kind = RelationKind.JUXTAPOSITION

            created.append(
                relations.register_semantic_pair(
                    namespace,
                    card_ids[0],
                    card_ids[1],
                    relation=kind,
                    rationale=finding.interpretation,
                    confidence=finding.confidence,
                    salience=max(0.55, finding.novelty),
                    provenance=finding.evidence_ids,
                    metadata={
                        "finding_id": finding.finding_id,
                        "lens_key": finding.lens_key,
                        "reading_status": finding.status.value,
                        "prediction": finding.prediction,
                        "counterreading": finding.counterreading,
                        "ambiguity": finding.ambiguity,
                        "novelty": finding.novelty,
                        "validated_frame": frame.frame_id,
                    },
                )
            )
        unique = {trace.relation_id: trace for trace in created}
        return tuple(sorted(unique.values(), key=lambda trace: trace.relation_id))

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
        relational_hypotheses = self._bridge_findings_to_relations(frame, validated)
        forecasts = self.predictive_model.propose(validated, composition=composition)
        for forecast in forecasts:
            self.prediction_ledger.add(forecast)
        tangents = list(
            self.tangent_bridge.ingest(
                validated,
                composition=composition,
                root_fingerprint=frame.fingerprint,
                sequence=sequence,
            )
        )
        perpendicular_plan = self.perpendicular_planner.plan(
            frame.observations,
            findings=validated,
            selected_lens_keys=tuple(item.key for item in frame.lens_selection.lenses),
        )
        tangents.extend(
            self.tangent_bridge.ingest_perpendicular(
                perpendicular_plan,
                root_fingerprint=frame.fingerprint,
                sequence=sequence,
            )
        )
        tangent_tuple = tuple(
            sorted({item.tangent_id: item for item in tangents}.values(), key=lambda item: item.tangent_id)
        )
        fingerprint = stable_fingerprint(
            {
                "frame": frame.fingerprint,
                "findings": [item.fingerprint for item in validated],
                "composition": composition.fingerprint,
                "forecasts": [item.fingerprint for item in forecasts],
                "tangents": [item.fingerprint for item in tangent_tuple],
                "perpendicular_plan": perpendicular_plan.fingerprint,
                "relational_hypotheses": [item.fingerprint for item in relational_hypotheses],
            }
        )
        update = NuanceUpdate(
            frame_id=frame.frame_id,
            findings=validated,
            composition=composition,
            forecasts=forecasts,
            tangent_nodes=tangent_tuple,
            fingerprint=fingerprint,
            perpendicular_plan=perpendicular_plan,
            relational_hypothesis_ids=tuple(item.relation_id for item in relational_hypotheses),
        )
        self._updates[frame.frame_id] = update
        return update

    def checkpoint_before_restart(self, frame_id: str, *, sequence: int, notes: str = "nuance checkpoint before restart") -> SemanticRestartPacket:
        frame = self._frames.get(str(frame_id))
        if frame is None:
            raise NuanceRuntimeError("unknown nuance frame")
        update = self._updates.get(frame.frame_id)
        if update is None:
            # Even if no semantic findings were registered, a restart must not
            # discard cue-supported orthogonal directions that were visible in
            # the frame. Persist them before checkpointing.
            restart_plan = self.perpendicular_planner.plan(
                frame.observations,
                findings=(),
                selected_lens_keys=tuple(item.key for item in frame.lens_selection.lenses),
            )
            self.tangent_bridge.ingest_perpendicular(
                restart_plan,
                root_fingerprint=frame.fingerprint,
                sequence=sequence,
            )
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
