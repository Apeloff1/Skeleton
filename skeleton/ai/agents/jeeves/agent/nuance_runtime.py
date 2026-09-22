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

from .cognition import ContextCompiler, ContextPacket, ContextSection, RunScratchpad
from .context_pipeline import ContextResolution, LayeredContextResolver
from .interpretive_science import ScientificLensLab
from .lens_hypergraph import SemanticHypergraphSnapshot, SemanticLensHypergraph
from .memory import MemoryNamespace
from .memory_game import InteractionCard
from .perpendicular_semantics import PerpendicularExpansionPlan, PerpendicularExpansionPlanner
from .relational_memory import RelationKind, RelationTrace, SequenceObservation
from .semantic_frontier import FrontierLensRouter, FrontierSemanticRegistry, LensCompositionEngine, SemanticComposition
from .semantic_fusion_runtime import (
    SemanticForecastFusionEngine,
    SemanticForecastFusionSnapshot,
)
from .semantic_governance import SemanticLensGovernanceBridge, SemanticLensGovernanceSnapshot
from .semantic_lenses import LensSelection, SemanticFinding, SemanticObservation
from .semantic_prediction import SemanticForecast, SemanticPredictionLedger, SemanticPredictiveModel
from .semantic_tangent_bridge import SemanticRestartPacket, SemanticTangentBridge
from .tangent_graph import TangentNode
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
    relation_sequence: SequenceObservation | None = None
    lens_governance: SemanticLensGovernanceSnapshot | None = None
    semantic_domain: str | None = None


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
    hypergraph: SemanticHypergraphSnapshot | None = None
    forecast_fusion: SemanticForecastFusionSnapshot | None = None


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
        lens_lab: ScientificLensLab | None = None,
        lens_governance: SemanticLensGovernanceBridge | None = None,
        lens_hypergraph: SemanticLensHypergraph | None = None,
        forecast_fusion_engine: SemanticForecastFusionEngine | None = None,
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
        if lens_governance is not None and lens_lab is not None and lens_governance.lab is not lens_lab:
            raise ValueError("lens_governance and lens_lab must share one ScientificLensLab")
        self.lens_governance = lens_governance or SemanticLensGovernanceBridge(lab=lens_lab)
        self.lens_lab = self.lens_governance.lab
        self.lens_hypergraph = lens_hypergraph or SemanticLensHypergraph()
        self.forecast_fusion_engine = (
            forecast_fusion_engine
            or SemanticForecastFusionEngine(self.semantic_registry)
        )
        if self.forecast_fusion_engine.registry is not self.semantic_registry:
            raise ValueError(
                "forecast_fusion_engine must share the semantic registry"
            )
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
        semantic_domain: str | None = None,
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
        governance = self.lens_governance.assess(
            selection,
            observations,
            domain=semantic_domain,
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
                "lens_governance": governance.fingerprint,
                "semantic_domain": governance.domain,
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
            lens_governance=governance,
            semantic_domain=governance.domain,
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
        calibration_weights = (
            frame.lens_governance.predictive_weights
            if frame.lens_governance is not None
            else {}
        )
        hypergraph = self.lens_hypergraph.build(
            validated,
            calibration_weights=calibration_weights,
        )
        forecast_fusion = self.forecast_fusion_engine.fuse(
            forecasts,
            governance=frame.lens_governance,
        )
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
                "hypergraph": hypergraph.fingerprint,
                "forecast_fusion": forecast_fusion.fingerprint,
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
            hypergraph=hypergraph,
            forecast_fusion=forecast_fusion,
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
        domain: str | None = None,
        independent_run: str | None = None,
        negative_control: bool = False,
    ) -> SemanticForecast:
        if (domain is None) != (independent_run is None):
            raise NuanceRuntimeError(
                "domain and independent_run must be supplied together for lens calibration"
            )
        if domain is not None and not str(domain).strip():
            raise NuanceRuntimeError("calibration domain must be non-empty")
        if independent_run is not None and not str(independent_run).strip():
            raise NuanceRuntimeError("calibration independent_run must be non-empty")
        if not isinstance(negative_control, bool):
            raise NuanceRuntimeError("negative_control must be boolean")
        open_forecast = self.prediction_ledger.get(forecast_id)
        open_fingerprint = (
            open_forecast.fingerprint
            if open_forecast is not None
            else None
        )
        resolved = self.prediction_ledger.resolve(
            forecast_id,
            outcome=outcome,
            observation_id=observation_id,
        )
        if domain is not None and independent_run is not None:
            findings_by_id = {
                finding.finding_id: finding
                for update in self._updates.values()
                for finding in update.findings
            }
            for finding_id in resolved.source_finding_ids:
                finding = findings_by_id.get(finding_id)
                if finding is None:
                    continue
                self.lens_lab.record_finding_outcome(
                    finding,
                    probability_value=resolved.probability,
                    outcome=outcome,
                    domain=domain,
                    independent_run=independent_run,
                    negative_control=negative_control,
                    source_forecast_id=resolved.forecast_id,
                    source_forecast_fingerprint=open_fingerprint,
                )
        return resolved

    def lens_science_summary(self) -> Mapping[str, Any]:
        statuses = {
            key: status.value
            for key, status in self.lens_lab.status_map().items()
        }
        hypergraphs = [
            update.hypergraph
            for update in self._updates.values()
            if update.hypergraph is not None
        ]
        fusions = [
            update.forecast_fusion
            for update in self._updates.values()
            if update.forecast_fusion is not None
        ]
        fusion_groups = [
            group
            for snapshot in fusions
            for group in snapshot.fusions
        ]
        return {
            "frame_count": len(self._frames),
            "update_count": len(self._updates),
            "open_forecasts": len(self.prediction_ledger.open()),
            "resolved_forecasts": len(self.prediction_ledger.resolved()),
            "calibrated_lens_count": len(statuses),
            "lens_statuses": statuses,
            "lens_lab_fingerprint": self.lens_lab.fingerprint,
            "governance_fingerprint": self.lens_governance.fingerprint,
            "hypergraph_count": len(hypergraphs),
            "latest_hypergraph_fingerprint": (
                hypergraphs[-1].fingerprint if hypergraphs else None
            ),
            "forecast_fusion_snapshot_count": len(fusions),
            "forecast_fusion_group_count": len(fusion_groups),
            "forecast_fusion_abstention_count": sum(
                group.result.abstain for group in fusion_groups
            ),
            "forecast_fusion_engine_fingerprint": (
                self.forecast_fusion_engine.fingerprint
            ),
            "invariants": {
                "semantic_lenses_remain_interpretive": True,
                "factual_assertion_from_lens_alone_forbidden": True,
                "causal_assertion_from_lens_alone_forbidden": True,
                "predictive_weight_requires_recorded_outcomes": True,
                "hypergraph_never_creates_evidence": True,
                "forecast_fusion_requires_textually_identical_targets": True,
                "forecast_fusion_never_merges_multi_lens_interactions": True,
                "forecast_fusion_can_abstain_on_dependence_or_conflict": True,
            },
        }

    def frame_diagnostics(self, frame_id: str) -> Mapping[str, Any]:
        frame = self._frames.get(str(frame_id))
        if frame is None:
            raise NuanceRuntimeError("unknown nuance frame")
        update = self._updates.get(frame.frame_id)
        governance = {
            item.lens_key: item
            for item in (
                frame.lens_governance.records
                if frame.lens_governance is not None
                else ()
            )
        }
        lens_rows = []
        for spec in frame.lens_selection.lenses:
            record = governance.get(spec.key)
            decision = record.decision if record is not None else None
            lens_rows.append(
                {
                    "key": spec.key,
                    "family": spec.family.value,
                    "role": spec.role.value,
                    "activation": float(
                        frame.lens_selection.activation_scores.get(spec.key, 0.0)
                    ),
                    "scientific_grade": (
                        decision.grade.value if decision is not None else None
                    ),
                    "scientific_status": (
                        decision.scientific_status.value
                        if decision is not None
                        else None
                    ),
                    "global_predictive_weight": (
                        decision.predictive_weight
                        if decision is not None
                        else 0.0
                    ),
                    "predictive_weight": (
                        record.domain_predictive_weight
                        if record is not None
                        and record.domain_predictive_weight is not None
                        else decision.predictive_weight
                        if decision is not None
                        else 0.0
                    ),
                    "domain_status": (
                        record.domain_status
                        if record is not None
                        else "unspecified"
                    ),
                    "decision_feature_authorized": (
                        decision.decision_feature_authorized
                        if decision is not None
                        else False
                    ),
                    "declared_maturity": (
                        record.declared_maturity
                        if record is not None
                        else None
                    ),
                }
            )

        forecast_rows = []
        fusion_rows = []
        hypergraph_payload: Mapping[str, Any] | None = None
        perpendicular_payload: Mapping[str, Any] | None = None
        if update is not None:
            forecast_rows = [
                {
                    "forecast_id": item.forecast_id,
                    "probability": item.probability,
                    "status": item.status.value,
                    "lens_keys": list(item.source_lens_keys),
                    "calibration_group": item.calibration_group,
                }
                for item in update.forecasts
            ]
            if update.forecast_fusion is not None:
                fusion_rows = [
                    {
                        "fusion_id": item.fusion_id,
                        "forecast_ids": list(item.forecast_ids),
                        "lens_keys": list(item.lens_keys),
                        "probability": item.result.probability,
                        "sensitivity": [
                            item.result.sensitivity_low,
                            item.result.sensitivity_high,
                        ],
                        "effective_lens_count": item.result.effective_lens_count,
                        "conflict_strength": item.result.conflict_strength,
                        "abstain": item.result.abstain,
                        "abstention_reasons": list(
                            item.result.abstention_reasons
                        ),
                        "dependency_count": len(item.result.dependencies),
                    }
                    for item in update.forecast_fusion.fusions
                ]
            if update.hypergraph is not None:
                hypergraph_payload = {
                    "edge_count": len(update.hypergraph.edges),
                    "unresolved_edge_count": len(
                        update.hypergraph.unresolved_edge_ids
                    ),
                    "missing_families": [
                        item.value
                        for item in update.hypergraph.restart.missing_families
                    ],
                    "tangent_seed_count": len(
                        update.hypergraph.restart.tangent_seeds
                    ),
                    "fingerprint": update.hypergraph.fingerprint,
                }
            if update.perpendicular_plan is not None:
                perpendicular_payload = {
                    "candidate_count": len(
                        update.perpendicular_plan.candidates
                    ),
                    "fingerprint": update.perpendicular_plan.fingerprint,
                }

        relation = frame.relation_sequence
        return json_safe(
            {
                "frame_id": frame.frame_id,
                "frame_fingerprint": frame.fingerprint,
                "namespace_key": frame.namespace_key,
                "semantic_domain": frame.semantic_domain,
                "context_fingerprint": frame.context.fingerprint,
                "context_item_count": len(frame.context.items),
                "captured_card_id": frame.captured_card_id,
                "lens_governance_fingerprint": (
                    frame.lens_governance.fingerprint
                    if frame.lens_governance is not None
                    else None
                ),
                "lenses": lens_rows,
                "uncertainty_lenses": [
                    item.lens.value
                    for item in frame.uncertainty_recommendations
                ],
                "relation_sequence": (
                    None
                    if relation is None
                    else {
                        "prediction_count": len(
                            relation.transition_predictions
                        ),
                        "created_relation_count": len(
                            relation.created_relation_ids
                        ),
                        "event_boundary_count": len(
                            relation.event_boundary_ids
                        ),
                        "fingerprint": relation.fingerprint,
                    }
                ),
                "update_fingerprint": (
                    update.fingerprint if update is not None else None
                ),
                "forecast_count": len(forecast_rows),
                "forecasts": forecast_rows,
                "forecast_fusions": fusion_rows,
                "hypergraph": hypergraph_payload,
                "perpendicular": perpendicular_payload,
                "relational_hypothesis_count": (
                    len(update.relational_hypothesis_ids)
                    if update is not None
                    else 0
                ),
                "invariants": {
                    "semantic_interpretation_is_not_evidence": True,
                    "lens_weights_are_frame_snapshots": True,
                    "fusion_is_target_identity_bounded": True,
                    "hypergraph_cannot_promote_evidence": True,
                },
            }
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
                "lens_lab": self.lens_lab.fingerprint,
                "lens_governance": self.lens_governance.fingerprint,
                "forecast_fusion_engine": self.forecast_fusion_engine.fingerprint,
                "tangent_graph": self.tangent_bridge.graph.fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class ScientificContextCompilerPolicy:
    """Prompt-facing bounds for the current relational nuance workbench."""

    maximum_nuance_chars: int = 20_000
    maximum_lens_questions: int = 3
    context_priority: int = 68

    def __post_init__(self) -> None:
        for name in (
            "maximum_nuance_chars",
            "maximum_lens_questions",
            "context_priority",
        ):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=1_000_000),
            )


class ScientificContextCompiler:
    """Compile current relational nuance state into the normal runtime context."""

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
            raise NuanceRuntimeError(
                "nuance runtime and scientific compiler must share one resolver"
            )
        self.base = base_compiler or ContextCompiler()
        self.policy = policy or ScientificContextCompilerPolicy()

    @staticmethod
    def _query(
        task_instruction: str,
        goal: Goal,
        current_step: PlanStep | None,
    ) -> str:
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
        governance_by_lens = {
            item.lens_key: item
            for item in (
                frame.lens_governance.records
                if frame.lens_governance is not None
                else ()
            )
        }
        lenses = []
        for spec in frame.lens_selection.lenses:
            governed = governance_by_lens.get(spec.key)
            decision = governed.decision if governed is not None else None
            lenses.append(
                {
                    "key": spec.key,
                    "family": spec.family.value,
                    "role": spec.role.value,
                    "activation": round(
                        float(frame.lens_selection.activation_scores.get(spec.key, 0.0)),
                        8,
                    ),
                    "rare": spec.rare,
                    "matched_cues": list(governed.matched_cues) if governed else [],
                    "scientific_grade": (
                        decision.grade.value if decision else "interpretive"
                    ),
                    "scientific_status": (
                        decision.scientific_status.value if decision else "shadow"
                    ),
                    "declared_maturity": (
                        governed.declared_maturity if governed else None
                    ),
                    "transfer_warning": (
                        governed.transfer_warning if governed else ""
                    ),
                    "lineage": list(governed.lineage) if governed else [],
                    "permissions": (
                        [item.value for item in decision.permissions]
                        if decision
                        else []
                    ),
                    "governance_reasons": (
                        list(decision.reasons[:3]) if decision else []
                    ),
                    "global_predictive_weight": round(
                        decision.predictive_weight if decision else 0.0,
                        8,
                    ),
                    "predictive_weight": round(
                        (
                            governed.domain_predictive_weight
                            if governed
                            and governed.domain_predictive_weight is not None
                            else decision.predictive_weight
                            if decision
                            else 0.0
                        ),
                        8,
                    ),
                    "domain_status": (
                        governed.domain_status if governed else "unspecified"
                    ),
                    "decision_feature_authorized": (
                        decision.decision_feature_authorized if decision else False
                    ),
                    "factual_assertion_authorized": False,
                    "causal_assertion_authorized": False,
                    "questions": list(spec.asks[: self.policy.maximum_lens_questions]),
                    "predicts": spec.predicts,
                    "failure_mode": spec.failure_mode,
                }
            )
        uncertainty = [
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
        relation = frame.relation_sequence
        payload: dict[str, Any] = {
            "contract": {
                "interpretive_only": True,
                "semantic_readings_are_not_evidence": True,
                "relations_change_retrieval_priority_not_factual_trust": True,
                "relational_transitions_are_scored_before_learning": True,
                "uncertainty_lenses_require_their_stated_assumptions": True,
                "predictions_must_be_falsifiable_and_scored_later": True,
                "lens_predictive_influence_is_empirically_gated": True,
                "lens_hypergraphs_never_create_evidence": True,
                "forecast_fusion_requires_textually_identical_targets": True,
                "forecast_fusion_may_abstain": True,
            },
            "frame_id": frame.frame_id,
            "frame_fingerprint": frame.fingerprint,
            "context_fingerprint": frame.context.fingerprint,
            "semantic_domain": frame.semantic_domain,
            "lens_governance_fingerprint": (
                frame.lens_governance.fingerprint
                if frame.lens_governance is not None
                else None
            ),
            "lenses": lenses,
            "uncertainty": uncertainty,
            "relation_sequence": None
            if relation is None
            else {
                "created_relation_ids": list(relation.created_relation_ids),
                "event_boundary_ids": list(relation.event_boundary_ids),
                "prediction_count": len(relation.transition_predictions),
                "fingerprint": relation.fingerprint,
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
                    "scientific_grade": row["scientific_grade"],
                    "scientific_status": row["scientific_status"],
                    "declared_maturity": row["declared_maturity"],
                    "global_predictive_weight": row["global_predictive_weight"],
                    "predictive_weight": row["predictive_weight"],
                    "domain_status": row["domain_status"],
                    "decision_feature_authorized": row["decision_feature_authorized"],
                }
                for row in lenses
            ]
            payload["uncertainty"] = [
                {
                    "lens": row["lens"],
                    "priority": row["priority"],
                    "quantity": row["quantity"],
                    "lineage_year": row["lineage_year"],
                }
                for row in uncertainty
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
                    "semantic_domain": frame.semantic_domain,
                    "lens_governance_fingerprint": (
                        frame.lens_governance.fingerprint
                        if frame.lens_governance is not None
                        else None
                    ),
                    "lens_keys": [item.key for item in frame.lens_selection.lenses],
                    "uncertainty_lenses": [
                        item.lens.value
                        for item in frame.uncertainty_recommendations
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
                "scientific context compiler must share the runtime MemoryManager"
            )
        domain_value = goal.metadata.get("domain")
        frame = self.nuance.prepare(
            namespace,
            self._query(task_instruction, goal, current_step),
            context_tags=self._context_tags(goal, plan, current_step),
            semantic_domain=(
                domain_value
                if isinstance(domain_value, str) and domain_value.strip()
                else None
            ),
            capture_interaction=False,
        )
        layered = frame.context.sections(
            maximum_chars=self.resolver.policy.max_total_chars
        )
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
            extra_sections=(
                tuple(layered)
                + (self._workbench_section(frame),)
                + tuple(extra_sections)
            ),
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
        domain_value = dict(metadata or {}).get("domain")
        frame = self.nuance.prepare(
            namespace,
            content,
            context_tags=context_tags,
            semantic_domain=(
                domain_value
                if isinstance(domain_value, str) and domain_value.strip()
                else None
            ),
            capture_interaction=True,
            interaction_provenance=provenance,
            interaction_metadata={
                "captured_by_scientific_context_compiler": True,
                **dict(metadata or {}),
            },
        )
        if not frame.captured_card_id:
            raise NuanceRuntimeError("scientific interaction capture produced no card")
        card = self.resolver.cards.store.get(frame.captured_card_id)
        if card is None:
            raise NuanceRuntimeError("captured scientific interaction card is missing")
        return card

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "resolver_policy": {
                    "card_limit": self.resolver.policy.card_limit,
                    "memory_limit": self.resolver.policy.memory_limit,
                    "repository_limit": self.resolver.policy.repository_limit,
                    "source_limit_per_tier": self.resolver.policy.source_limit_per_tier,
                    "minimum_item_score": self.resolver.policy.minimum_item_score,
                    "stop_coverage": self.resolver.policy.stop_coverage,
                    "stop_confidence": self.resolver.policy.stop_confidence,
                    "stop_trust": self.resolver.policy.stop_trust,
                    "maximum_tier": int(self.resolver.policy.maximum_tier),
                    "max_total_chars": self.resolver.policy.max_total_chars,
                },
                "nuance": self.nuance.fingerprint,
                "base_budget": {
                    "total_chars": self.base.budget.total_chars,
                    "memory_chars": self.base.budget.memory_chars,
                    "evidence_chars": self.base.budget.evidence_chars,
                },
                "policy": {
                    "maximum_nuance_chars": self.policy.maximum_nuance_chars,
                    "maximum_lens_questions": self.policy.maximum_lens_questions,
                    "context_priority": self.policy.context_priority,
                },
            }
        )
