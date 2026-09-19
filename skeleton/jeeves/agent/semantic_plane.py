"""Unified deep semantic reasoning plane for Jeeves.

The semantic plane is a deterministic orchestration layer over the existing
Jeeves lens machinery. It does not generate interpretations itself. Instead it
makes the lifecycle of externally supplied SemanticFinding objects explicit:

observations
  -> diverse lens selection
  -> scientific governance
  -> finding contract audit
  -> perpendicular research expansion
  -> pairwise interaction composition
  -> high-order hypergraph composition
  -> authority-gated semantic forecasts
  -> dependence-aware forecast fusion
  -> coverage / abstention diagnostics

The plane preserves one invariant throughout: lenses and their compositions are
not evidence. Factual and causal assertion authority remain false unless a
separate evidence/causal layer establishes them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from .epistemic_frontier import KnowledgeObligation
from .lens_fusion import LensFusionEngine, LensFusionResult, LensSignal
from .lens_hypergraph import SemanticHypergraphSnapshot, SemanticLensHypergraph
from .interpretive_science import LensOutcomeTrial, ScientificLensReport
from .perpendicular_semantics import (
    PerpendicularExpansionPlan,
    PerpendicularExpansionPlanner,
)
from .semantic_frontier import (
    LensCompositionEngine,
    LensInteractionKind,
    SemanticComposition,
    default_interaction_rules,
)
from .semantic_governance_bridge import (
    SemanticGovernanceBridge,
    SemanticGovernanceSnapshot,
)
from .semantic_lenses import (
    LensFamily,
    LensSelection,
    ReadingStatus,
    SemanticFinding,
    SemanticLensSpec,
    SemanticObservation,
    SemanticRole,
    TangentSeed,
)
from .semantic_maximal import MaximalLensRouter, MaximalSemanticRegistry
from .semantic_lens_topology import (
    LensBridgeCandidate,
    SemanticLensTopology,
    SemanticTopologySnapshot,
)
from .semantic_plane_interactions import plane_interaction_rules
from .semantic_depth_interactions import depth_interaction_rules
from .semantic_topology_learning import (
    LearnedTopologyRule,
    SemanticTopologyLearningLab,
    SemanticTopologyLearningSnapshot,
    SemanticTopologyLearningState,
    TopologyBridgePrediction,
    TopologyBridgeReport,
    TopologyBridgeTrial,
)
from .semantic_prediction import (
    PredictionStatus,
    SemanticForecast,
    SemanticPredictionLedger,
    SemanticPredictiveModel,
)
from .tangent_graph import ExplorationAxis, FrontierSelection, TangentGraph
from .types import (
    AgentContractError,
    bounded_text,
    positive_int,
    probability,
    stable_fingerprint,
    stable_id,
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
    LensFamily.CAUSAL: ExplorationAxis.CAUSAL,
    LensFamily.INFORMATION: ExplorationAxis.SEMANTIC,
    LensFamily.COMPUTATIONAL: ExplorationAxis.SYSTEM,
    LensFamily.METACOGNITIVE: ExplorationAxis.ADVERSARIAL,
    LensFamily.PROBABILITY: ExplorationAxis.PROBABILISTIC,
    LensFamily.PREDICTIVE: ExplorationAxis.PROBABILISTIC,
}



_AXIS_TAG: dict[str, ExplorationAxis] = {
    "causal": ExplorationAxis.CAUSAL,
    "probability": ExplorationAxis.PROBABILISTIC,
    "probabilistic": ExplorationAxis.PROBABILISTIC,
    "predictive": ExplorationAxis.PROBABILISTIC,
    "temporal": ExplorationAxis.TEMPORAL,
    "semantic": ExplorationAxis.SEMANTIC,
    "cinematic": ExplorationAxis.CINEMATIC,
    "literary": ExplorationAxis.LITERARY,
    "ludic": ExplorationAxis.LUDIC,
    "social": ExplorationAxis.SOCIAL,
    "adversarial": ExplorationAxis.ADVERSARIAL,
    "system": ExplorationAxis.SYSTEM,
    "memory": ExplorationAxis.MEMORY,
    "computational": ExplorationAxis.SYSTEM,
    "metacognitive": ExplorationAxis.ADVERSARIAL,
    "information": ExplorationAxis.SEMANTIC,
}


@dataclass(frozen=True, slots=True)
class SemanticPlanePolicy:
    max_lenses: int = 40
    max_per_family: int = 6
    minimum_rare_when_supported: int = 4
    max_perpendicular_axes: int = 16
    frontier_limit: int = 20
    frontier_max_per_axis: int = 3
    frontier_max_per_family: int = 3
    topology_bridge_limit: int = 12
    topology_bridge_minimum_score: float = 0.18
    enable_learned_companions: bool = True
    max_learned_companions: int = 4
    minimum_learned_companion_cue_support: float = 0.20
    minimum_learned_companion_bridge_quality: float = 0.55
    require_selected_findings: bool = True
    require_observation_overlap: bool = True
    require_observation_subset: bool = True
    require_evidence_provenance: bool = True
    include_interaction_forecasts: bool = True
    base_rate: float = 0.5

    def __post_init__(self) -> None:
        for name in (
            "max_lenses",
            "max_per_family",
            "minimum_rare_when_supported",
            "max_perpendicular_axes",
            "frontier_limit",
            "frontier_max_per_axis",
            "frontier_max_per_family",
            "topology_bridge_limit",
            "max_learned_companions",
        ):
            object.__setattr__(
                self,
                name,
                positive_int(name, getattr(self, name), maximum=10_000),
            )
        object.__setattr__(
            self,
            "topology_bridge_minimum_score",
            probability(
                "topology_bridge_minimum_score",
                self.topology_bridge_minimum_score,
            ),
        )
        object.__setattr__(
            self,
            "minimum_learned_companion_cue_support",
            probability(
                "minimum_learned_companion_cue_support",
                self.minimum_learned_companion_cue_support,
            ),
        )
        object.__setattr__(
            self,
            "minimum_learned_companion_bridge_quality",
            probability(
                "minimum_learned_companion_bridge_quality",
                self.minimum_learned_companion_bridge_quality,
            ),
        )
        if not isinstance(self.enable_learned_companions, bool):
            raise AgentContractError(
                "enable_learned_companions must be boolean"
            )
        object.__setattr__(
            self,
            "base_rate",
            probability("base_rate", self.base_rate),
        )


@dataclass(frozen=True, slots=True)
class FindingRejection:
    finding_id: str
    lens_key: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticFindingAudit:
    accepted: tuple[SemanticFinding, ...]
    rejected: tuple[FindingRejection, ...]
    unknown_lens_keys: tuple[str, ...]
    family_mismatch_ids: tuple[str, ...]
    unselected_ids: tuple[str, ...]
    orphan_observation_ids: tuple[str, ...]
    unknown_observation_reference_ids: tuple[str, ...]
    evidence_mismatch_ids: tuple[str, ...]
    duplicate_finding_ids: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class LearnedCompanionActivation:
    lens_key: str
    source_lens_key: str
    candidate_id: str
    report_id: str
    interaction_kind: LensInteractionKind
    cue_support: float
    bridge_quality: float
    activation_score: float
    fingerprint: str

    def __post_init__(self) -> None:
        for name in (
            "lens_key",
            "source_lens_key",
            "candidate_id",
            "report_id",
        ):
            value = str(getattr(self, name)).strip()
            if not value:
                raise AgentContractError(f"{name} is required")
            object.__setattr__(self, name, value)
        if not isinstance(self.interaction_kind, LensInteractionKind):
            object.__setattr__(
                self,
                "interaction_kind",
                LensInteractionKind(str(self.interaction_kind)),
            )
        for name in (
            "cue_support",
            "bridge_quality",
            "activation_score",
        ):
            object.__setattr__(
                self,
                name,
                probability(name, getattr(self, name)),
            )

    def as_json(self) -> dict[str, Any]:
        return {
            "lens_key": self.lens_key,
            "source_lens_key": self.source_lens_key,
            "candidate_id": self.candidate_id,
            "report_id": self.report_id,
            "interaction_kind": self.interaction_kind.value,
            "cue_support": self.cue_support,
            "bridge_quality": self.bridge_quality,
            "activation_score": self.activation_score,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class SemanticPlaneCoverage:
    selected_families: tuple[LensFamily, ...]
    finding_families: tuple[LensFamily, ...]
    selected_roles: tuple[SemanticRole, ...]
    missing_families: tuple[LensFamily, ...]
    missing_roles: tuple[SemanticRole, ...]
    family_coverage: float
    role_coverage: float
    rare_fraction: float
    adversarial_selected: bool
    accepted_findings: int
    rejected_findings: int
    pairwise_interactions: int
    hyperedges: int
    unresolved_conflicts: int
    perpendicular_candidates: int
    forecast_count: int
    fused_effective_lens_count: float
    tangent_count: int
    frontier_tangent_count: int
    topology_components: int
    topology_isolated_lenses: int
    topology_bridge_lenses: int
    topology_candidate_bridges: int
    topology_learned_bridges: int
    topology_active_learning_reports: int
    learned_companion_lenses: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SemanticPlaneLearningUpdate:
    forecast: SemanticForecast
    trial_ids: tuple[str, ...]
    calibrated_keys: tuple[str, ...]
    reports: tuple[ScientificLensReport, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SemanticPlaneSnapshot:
    observation_ids: tuple[str, ...]
    selection: LensSelection
    governance: SemanticGovernanceSnapshot
    finding_audit: SemanticFindingAudit
    perpendicular: PerpendicularExpansionPlan
    composition: SemanticComposition
    hypergraph: SemanticHypergraphSnapshot
    forecasts: tuple[SemanticForecast, ...]
    fusion: LensFusionResult
    coverage: SemanticPlaneCoverage
    tangent_ids: tuple[str, ...]
    frontier: FrontierSelection
    topology: SemanticTopologySnapshot
    topology_learning: SemanticTopologyLearningSnapshot
    learned_topology_rules: tuple[LearnedTopologyRule, ...]
    learned_companion_keys: tuple[str, ...]
    learned_companion_activations: tuple[
        LearnedCompanionActivation,
        ...,
    ]
    topology_bridge_candidates: tuple[LensBridgeCandidate, ...]
    runtime_state_fingerprint: str
    decision_feature_authorized: bool
    factual_assertion_authorized: bool
    causal_assertion_authorized: bool
    fingerprint: str


class SemanticLensPlane:
    """Execute the complete semantic-lens reasoning plane deterministically."""

    def __init__(
        self,
        *,
        registry: MaximalSemanticRegistry | None = None,
        router: MaximalLensRouter | None = None,
        governance: SemanticGovernanceBridge | None = None,
        perpendicular: PerpendicularExpansionPlanner | None = None,
        composition: LensCompositionEngine | None = None,
        hypergraph: SemanticLensHypergraph | None = None,
        predictive: SemanticPredictiveModel | None = None,
        prediction_ledger: SemanticPredictionLedger | None = None,
        fusion: LensFusionEngine | None = None,
        tangent_graph: TangentGraph | None = None,
        topology: SemanticLensTopology | None = None,
        topology_learning: SemanticTopologyLearningLab | None = None,
        policy: SemanticPlanePolicy | None = None,
    ) -> None:
        self.registry = registry or MaximalSemanticRegistry()
        self.router = router or MaximalLensRouter(self.registry)
        self.governance = governance or SemanticGovernanceBridge()
        self.perpendicular = perpendicular or PerpendicularExpansionPlanner(self.registry)
        self.composition = composition or LensCompositionEngine(
            (
                *default_interaction_rules(),
                *plane_interaction_rules(),
                *depth_interaction_rules(),
            )
        )
        self.hypergraph = hypergraph or SemanticLensHypergraph()
        self.predictive = predictive or SemanticPredictiveModel()
        self.prediction_ledger = prediction_ledger or SemanticPredictionLedger()
        self.fusion = fusion or LensFusionEngine()
        self.tangent_graph = tangent_graph or TangentGraph()
        self.topology = topology or SemanticLensTopology(self.registry)
        self.topology_learning = (
            topology_learning
            or SemanticTopologyLearningLab(self.topology)
        )
        if self.topology_learning.topology is not self.topology:
            raise ValueError(
                "topology_learning must share the semantic topology"
            )
        self.policy = policy or SemanticPlanePolicy()

    def select(
        self,
        observations: Sequence[SemanticObservation],
        *,
        requested: Sequence[str] = (),
    ) -> LensSelection:
        return self.router.select_maximal(
            observations,
            requested=requested,
            max_lenses=self.policy.max_lenses,
            max_per_family=self.policy.max_per_family,
            minimum_rare_when_supported=self.policy.minimum_rare_when_supported,
        )

    def audit_findings(
        self,
        findings: Sequence[SemanticFinding],
        *,
        observations: Sequence[SemanticObservation],
        selection: LensSelection,
    ) -> SemanticFindingAudit:
        if any(not isinstance(item, SemanticFinding) for item in findings):
            raise TypeError("findings must contain SemanticFinding values")

        observation_ids = {item.observation_id for item in observations}
        observation_evidence = {
            item.observation_id: set(item.evidence_ids)
            for item in observations
        }
        selected = {spec.key for spec in selection.lenses}
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding.finding_id] = counts.get(finding.finding_id, 0) + 1
        duplicate_ids = {key for key, count in counts.items() if count > 1}

        accepted: list[SemanticFinding] = []
        rejected: list[FindingRejection] = []
        unknown: set[str] = set()
        family_mismatch: set[str] = set()
        unselected: set[str] = set()
        orphan: set[str] = set()
        unknown_observation_reference: set[str] = set()
        evidence_mismatch: set[str] = set()

        for finding in findings:
            reasons: list[str] = []
            if finding.finding_id in duplicate_ids:
                reasons.append("duplicate_finding_id")

            try:
                spec = self.registry.get(finding.lens_key)
            except KeyError:
                spec = None
                unknown.add(finding.lens_key)
                reasons.append("unknown_lens_key")

            if spec is not None and spec.family is not finding.family:
                family_mismatch.add(finding.finding_id)
                reasons.append("lens_family_mismatch")

            if self.policy.require_selected_findings and finding.lens_key not in selected:
                unselected.add(finding.finding_id)
                reasons.append("lens_not_selected_for_current_observations")

            finding_observations = set(finding.observation_ids)
            unknown_refs = finding_observations - observation_ids
            if unknown_refs:
                unknown_observation_reference.add(finding.finding_id)
                if self.policy.require_observation_subset:
                    reasons.append("unknown_observation_reference")

            if (
                self.policy.require_observation_overlap
                and finding_observations
                and not (finding_observations & observation_ids)
            ):
                orphan.add(finding.finding_id)
                reasons.append("no_overlap_with_current_observations")

            if self.policy.require_evidence_provenance and finding.evidence_ids:
                referenced_evidence: set[str] = set()
                for observation_id in finding_observations & observation_ids:
                    referenced_evidence.update(
                        observation_evidence.get(observation_id, set())
                    )
                if not set(finding.evidence_ids).issubset(referenced_evidence):
                    evidence_mismatch.add(finding.finding_id)
                    reasons.append("evidence_not_provenanced_by_observations")

            reasons = list(dict.fromkeys(reasons))
            if reasons:
                rejected.append(
                    FindingRejection(
                        finding_id=finding.finding_id,
                        lens_key=finding.lens_key,
                        reasons=tuple(reasons),
                    )
                )
            else:
                accepted.append(finding)

        fingerprint = stable_fingerprint(
            {
                "accepted": [item.fingerprint for item in accepted],
                "rejected": [
                    (item.finding_id, item.lens_key, item.reasons)
                    for item in rejected
                ],
                "unknown": sorted(unknown),
                "family_mismatch": sorted(family_mismatch),
                "unselected": sorted(unselected),
                "orphan": sorted(orphan),
                "unknown_observation_reference": sorted(
                    unknown_observation_reference
                ),
                "evidence_mismatch": sorted(evidence_mismatch),
                "duplicate_finding_ids": sorted(duplicate_ids),
            }
        )
        return SemanticFindingAudit(
            accepted=tuple(accepted),
            rejected=tuple(rejected),
            unknown_lens_keys=tuple(sorted(unknown)),
            family_mismatch_ids=tuple(sorted(family_mismatch)),
            unselected_ids=tuple(sorted(unselected)),
            orphan_observation_ids=tuple(sorted(orphan)),
            unknown_observation_reference_ids=tuple(
                sorted(unknown_observation_reference)
            ),
            evidence_mismatch_ids=tuple(sorted(evidence_mismatch)),
            duplicate_finding_ids=tuple(sorted(duplicate_ids)),
            fingerprint=fingerprint,
        )

    def _forecast_allowed(
        self,
        forecast: SemanticForecast,
        governance: SemanticGovernanceSnapshot,
    ) -> bool:
        blocked = set(governance.forecast_blocked_lens_keys)
        return bool(forecast.source_lens_keys) and not (
            set(forecast.source_lens_keys) & blocked
        )

    def _family_for_forecast(self, forecast: SemanticForecast) -> LensFamily:
        families: list[LensFamily] = []
        for key in forecast.source_lens_keys:
            try:
                family = self.registry.get(key).family
            except KeyError:
                continue
            if family not in families:
                families.append(family)
        if not families:
            return LensFamily.PREDICTIVE
        if len(families) == 1:
            return families[0]
        # Cross-family interactions are derived predictive signals. Assigning
        # them to one source family would consume that family's fusion budget
        # arbitrarily and can double-count one side of the interaction.
        return LensFamily.PREDICTIVE

    def _reliability_for_forecast(
        self,
        forecast: SemanticForecast,
        governance: SemanticGovernanceSnapshot,
    ) -> float:
        weights = [
            governance.weight_for(key, 0.0)
            for key in forecast.source_lens_keys
        ]
        component_weight = min(weights) if weights else 0.0
        source_keys = tuple(sorted(set(forecast.source_lens_keys)))
        if len(source_keys) <= 1:
            return component_weight

        interaction_key = "interaction:" + "+".join(source_keys)
        interaction_trials = self.governance.registry.lab.trials(interaction_key)
        if not interaction_trials:
            return component_weight
        interaction_weight = self.governance.registry.lab.routing_weight(
            interaction_key,
            default_shadow_weight=component_weight,
        )
        # An interaction cannot become more reliable than its weakest governed
        # constituent merely because the composite accumulated favorable trials.
        return min(component_weight, interaction_weight)

    def _register_open_forecasts(
        self,
        proposals: Sequence[SemanticForecast],
        governance: SemanticGovernanceSnapshot,
    ) -> tuple[SemanticForecast, ...]:
        registered: list[SemanticForecast] = []
        for forecast in proposals:
            if not self._forecast_allowed(forecast, governance):
                continue
            existing = self.prediction_ledger.get(forecast.forecast_id)
            if existing is None:
                registered.append(self.prediction_ledger.add(forecast))
                continue
            if existing.status is PredictionStatus.OPEN:
                registered.append(self.prediction_ledger.add(forecast))
                continue
            # A resolved/invalidated semantic proposition is not silently
            # reopened. New evidence or changed epistemic state yields a new
            # forecast id; an unchanged proposition remains closed.
        return tuple(registered)

    def _signals(
        self,
        forecasts: Sequence[SemanticForecast],
        governance: SemanticGovernanceSnapshot,
    ) -> tuple[LensSignal, ...]:
        signals: list[LensSignal] = []
        for forecast in forecasts:
            families = tuple(
                sorted(
                    {
                        self.registry.get(key).family
                        for key in forecast.source_lens_keys
                        if key in {spec.key for spec in self.registry.all()}
                    },
                    key=lambda family: family.value,
                )
            )
            signals.append(
                LensSignal(
                    signal_id=forecast.forecast_id,
                    lens_key="+".join(forecast.source_lens_keys) or "semantic",
                    family=self._family_for_forecast(forecast),
                    probability=forecast.probability,
                    confidence=forecast.epistemic_strength,
                    ambiguity=forecast.ambiguity,
                    reliability=self._reliability_for_forecast(
                        forecast,
                        governance,
                    ),
                    epistemic_strength=forecast.epistemic_strength,
                    observation_ids=forecast.observation_ids,
                    evidence_ids=forecast.evidence_ids,
                    calibration_group=forecast.calibration_group,
                    provenance_ids=tuple(
                        sorted(
                            set(forecast.source_finding_ids)
                            | set(forecast.source_interaction_ids)
                        )
                    ),
                    metadata={
                        "forecast_fingerprint": forecast.fingerprint,
                        "source_families": [family.value for family in families],
                        "semantic_plane": True,
                    },
                )
            )
        return tuple(signals)

    def reasoning_signals(
        self,
        snapshot: SemanticPlaneSnapshot,
        *,
        limit: int = 24,
    ) -> tuple[LensSignal, ...]:
        """Return custody-checked semantic signals for inference escalation.

        These signals are advisory and escalation-only. They may cause frontier
        reasoning to deliberate, seek evidence, or abstain when semantic
        forecasts conflict or are sensitive. They cannot increase factual
        evidence quality or independently authorize a commit.
        """

        if not isinstance(snapshot, SemanticPlaneSnapshot):
            raise TypeError("snapshot must be SemanticPlaneSnapshot")
        maximum = positive_int("limit", limit, maximum=1_000)
        if (
            snapshot.factual_assertion_authorized
            or snapshot.causal_assertion_authorized
        ):
            raise AgentContractError(
                "semantic reasoning signals cannot carry factual/causal authority"
            )

        if (
            snapshot.runtime_state_fingerprint
            != self.runtime_state_fingerprint
        ):
            raise AgentContractError(
                "semantic reasoning snapshot state revision is stale"
            )

        open_forecasts: list[SemanticForecast] = []
        for forecast in snapshot.forecasts:
            stored = self.prediction_ledger.get(forecast.forecast_id)
            if stored is None:
                raise AgentContractError(
                    "semantic reasoning forecast is missing from prediction custody"
                )
            if stored.fingerprint != forecast.fingerprint:
                raise AgentContractError(
                    "semantic reasoning forecast differs from prediction custody"
                )
            if stored.status is not PredictionStatus.OPEN:
                continue
            open_forecasts.append(stored)

        signals = self._signals(
            tuple(open_forecasts[:maximum]),
            snapshot.governance,
        )
        return tuple(
            replace(
                signal,
                metadata={
                    **dict(signal.metadata),
                    "semantic_snapshot_fingerprint": snapshot.fingerprint,
                    "semantic_governance_fingerprint": (
                        snapshot.governance.fingerprint
                    ),
                    "semantic_topology_learning_fingerprint": (
                        snapshot.topology_learning.fingerprint
                    ),
                    "semantic_runtime_state_fingerprint": (
                        snapshot.runtime_state_fingerprint
                    ),
                    "inference_authority": "escalation_only",
                    "may_increase_evidence_quality": False,
                    "may_authorize_commit": False,
                    "factual_assertion_authorized": False,
                    "causal_assertion_authorized": False,
                },
            )
            for signal in signals
        )

    def reasoning_signal_is_current(
        self,
        signal: LensSignal,
    ) -> bool:
        """Check that an advisory still points at the same open forecast."""

        if not isinstance(signal, LensSignal):
            return False
        if signal.metadata.get("inference_authority") != "escalation_only":
            return False
        stored = self.prediction_ledger.get(signal.signal_id)
        if stored is None or stored.status is not PredictionStatus.OPEN:
            return False
        return (
            signal.metadata.get("forecast_fingerprint")
            == stored.fingerprint
            and signal.metadata.get(
                "semantic_runtime_state_fingerprint"
            )
            == self.runtime_state_fingerprint
        )

    def _seed_family(self, seed: TangentSeed) -> LensFamily | None:
        key = seed.lens_key.strip().casefold()
        try:
            return self.registry.get(key).family
        except KeyError:
            pass
        if key.startswith("perpendicular:"):
            family_name = key.partition(":")[2]
            try:
                return LensFamily(family_name)
            except ValueError:
                return None
        component_families: set[LensFamily] = set()
        for component in key.split("+"):
            try:
                component_families.add(self.registry.get(component).family)
            except KeyError:
                continue
        if len(component_families) == 1:
            return next(iter(component_families))
        return None

    @staticmethod
    def _seed_axis(
        seed: TangentSeed,
        family: LensFamily | None,
    ) -> ExplorationAxis:
        for tag in seed.tags:
            axis = _AXIS_TAG.get(str(tag).casefold())
            if axis is not None:
                return axis
        if family is not None:
            return _FAMILY_AXIS[family]
        return ExplorationAxis.SEMANTIC

    def _seed_tangent_frontier(
        self,
        *,
        observations: Sequence[SemanticObservation],
        audit: SemanticFindingAudit,
        perpendicular: PerpendicularExpansionPlan,
        composition: SemanticComposition,
        hypergraph: SemanticHypergraphSnapshot,
        sequence: int,
    ) -> tuple[tuple[str, ...], FrontierSelection]:
        parent_fingerprint = stable_fingerprint(
            {
                "observations": [item.fingerprint for item in observations],
                "findings": [item.fingerprint for item in audit.accepted],
            }
        )
        evidence_ids = tuple(
            sorted(
                {
                    evidence_id
                    for finding in audit.accepted
                    for evidence_id in finding.evidence_ids
                }
            )
        )
        inserted: list[str] = []

        for candidate in perpendicular.candidates:
            seed = TangentSeed(
                seed_id=stable_id(
                    "semantic-plane-perpendicular",
                    {
                        "parent": parent_fingerprint,
                        "lens": candidate.lens_key,
                        "direction": candidate.direction,
                    },
                    length=28,
                ),
                parent_fingerprint=parent_fingerprint,
                lens_key=candidate.lens_key,
                direction=candidate.direction,
                rationale=candidate.rationale,
                novelty=max(candidate.family_novelty, candidate.role_novelty),
                expected_value=candidate.expected_value,
                evidence_ids=evidence_ids,
                tags=(
                    "semantic-plane",
                    "perpendicular",
                    candidate.family.value,
                    candidate.role.value,
                ),
            )
            node = self.tangent_graph.add_seed(
                seed,
                axis=_FAMILY_AXIS[candidate.family],
                family=candidate.family,
                sequence=sequence,
                trigger_terms=candidate.trigger_terms,
                evidence_gap=candidate.evidence_gap,
            )
            inserted.append(node.tangent_id)

        existing_seed_ids: set[str] = set()
        for seed in (
            *composition.tangent_seeds,
            *hypergraph.restart.tangent_seeds,
        ):
            if seed.seed_id in existing_seed_ids:
                continue
            existing_seed_ids.add(seed.seed_id)
            family = self._seed_family(seed)
            node = self.tangent_graph.add_seed(
                seed,
                axis=self._seed_axis(seed, family),
                family=family,
                sequence=sequence,
                trigger_terms=seed.tags,
                evidence_gap=(
                    0.85
                    if family is not None
                    and family in hypergraph.restart.missing_families
                    else 0.65
                ),
            )
            inserted.append(node.tangent_id)

        frontier = self.tangent_graph.frontier(
            limit=self.policy.frontier_limit,
            max_per_axis=self.policy.frontier_max_per_axis,
            max_per_family=self.policy.frontier_max_per_family,
        )
        return tuple(sorted(set(inserted))), frontier

    @staticmethod
    def _decision_feature_authorized(
        *,
        forecasts: Sequence[SemanticForecast],
        governance: SemanticGovernanceSnapshot,
        composition: SemanticComposition,
        fusion: LensFusionResult,
    ) -> bool:
        if (
            not forecasts
            or fusion.abstain
            or composition.unresolved_conflicts
        ):
            return False
        decision_by_key = {
            item.lens_id: item.decision_feature_authorized
            for item in governance.decisions
        }
        source_keys = {
            key
            for forecast in forecasts
            for key in forecast.source_lens_keys
        }
        return bool(source_keys) and all(
            decision_by_key.get(key, False)
            for key in source_keys
        )

    def _cue_support(
        self,
        spec: SemanticLensSpec,
        observations: Sequence[SemanticObservation],
    ) -> float:
        if not spec.activation_cues:
            return 0.0
        observation_tokens: set[str] = set()
        for observation in observations:
            observation_tokens.update(
                self.router._tokens(observation.content)
            )
            observation_tokens.update(
                str(tag).strip().casefold()
                for tag in observation.tags
                if str(tag).strip()
            )
        matched = 0
        for cue in spec.activation_cues:
            cue_tokens = self.router._tokens(cue)
            if cue_tokens and cue_tokens.issubset(observation_tokens):
                matched += 1
        return matched / max(1, len(spec.activation_cues))

    def _augment_with_learned_companions(
        self,
        selection: LensSelection,
        observations: Sequence[SemanticObservation],
        learned_rules: Sequence[LearnedTopologyRule],
    ) -> tuple[
        LensSelection,
        tuple[LearnedCompanionActivation, ...],
    ]:
        if (
            not self.policy.enable_learned_companions
            or not learned_rules
            or len(selection.lenses) >= self.policy.max_lenses
        ):
            return selection, ()

        selected = list(selection.lenses)
        selected_keys = {item.key for item in selected}
        scores = dict(selection.activation_scores)
        family_counts: dict[LensFamily, int] = {}
        for spec in selected:
            family_counts[spec.family] = (
                family_counts.get(spec.family, 0) + 1
            )

        proposals: dict[
            str,
            tuple[
                float,
                SemanticLensSpec,
                LearnedCompanionActivation,
            ],
        ] = {}
        for learned in learned_rules:
            if (
                learned.bridge_quality
                < self.policy.minimum_learned_companion_bridge_quality
            ):
                continue
            left_key, right_key = learned.rule.key
            left_selected = left_key in selected_keys
            right_selected = right_key in selected_keys
            if left_selected == right_selected:
                continue
            source_key = left_key if left_selected else right_key
            companion_key = right_key if left_selected else left_key
            try:
                companion = self.registry.get(companion_key)
            except KeyError:
                continue
            if len(observations) < companion.minimum_observations:
                continue
            if (
                family_counts.get(companion.family, 0)
                >= self.policy.max_per_family
            ):
                continue

            cue_support = self._cue_support(companion, observations)
            if (
                cue_support
                < self.policy.minimum_learned_companion_cue_support
            ):
                continue

            pair_bonus = (
                0.07
                if companion.pairwise and len(observations) >= 2
                else 0.0
            )
            sequential_bonus = (
                0.07
                if companion.sequential and len(observations) >= 3
                else 0.0
            )
            rarity_bonus = 0.03 if companion.rare else 0.0
            activation = min(
                1.0,
                0.10
                + 0.50 * cue_support
                + 0.23 * learned.bridge_quality
                + pair_bonus
                + sequential_bonus
                + rarity_bonus,
            )
            activation_record = LearnedCompanionActivation(
                lens_key=companion.key,
                source_lens_key=source_key,
                candidate_id=learned.candidate_id,
                report_id=learned.report_id,
                interaction_kind=learned.rule.kind,
                cue_support=cue_support,
                bridge_quality=learned.bridge_quality,
                activation_score=activation,
                fingerprint=stable_fingerprint(
                    {
                        "lens": companion.key,
                        "source": source_key,
                        "candidate": learned.candidate_id,
                        "report": learned.report_fingerprint,
                        "kind": learned.rule.kind.value,
                        "cue_support": cue_support,
                        "bridge_quality": learned.bridge_quality,
                        "activation": activation,
                    }
                ),
            )
            prior = proposals.get(companion.key)
            if prior is None or activation > prior[0]:
                proposals[companion.key] = (
                    activation,
                    companion,
                    activation_record,
                )

        ordered = sorted(
            proposals.values(),
            key=lambda item: (
                -item[0],
                -item[2].bridge_quality,
                item[1].family.value,
                item[1].key,
            ),
        )
        added: list[LearnedCompanionActivation] = []
        for activation, companion, activation_record in ordered:
            if (
                len(selected) >= self.policy.max_lenses
                or len(added) >= self.policy.max_learned_companions
            ):
                break
            if companion.key in selected_keys:
                continue
            if (
                family_counts.get(companion.family, 0)
                >= self.policy.max_per_family
            ):
                continue
            selected.append(companion)
            selected_keys.add(companion.key)
            family_counts[companion.family] = (
                family_counts.get(companion.family, 0) + 1
            )
            scores[companion.key] = activation
            added.append(activation_record)

        if not added:
            return selection, ()
        return (
            LensSelection(
                lenses=tuple(selected),
                activation_scores=scores,
                families=tuple(
                    sorted(
                        {spec.family for spec in selected},
                        key=lambda family: family.value,
                    )
                ),
                perpendicular=selection.perpendicular,
            ),
            tuple(
                sorted(
                    added,
                    key=lambda item: (
                        item.lens_key,
                        item.source_lens_key,
                        item.candidate_id,
                    ),
                )
            ),
        )

    def _coverage(
        self,
        *,
        selection: LensSelection,
        audit: SemanticFindingAudit,
        perpendicular: PerpendicularExpansionPlan,
        composition: SemanticComposition,
        hypergraph: SemanticHypergraphSnapshot,
        forecasts: Sequence[SemanticForecast],
        fusion: LensFusionResult,
        tangent_ids: Sequence[str],
        frontier: FrontierSelection,
        topology: SemanticTopologySnapshot,
        topology_learning: SemanticTopologyLearningSnapshot,
        learned_topology_rules: Sequence[LearnedTopologyRule],
        learned_companion_keys: Sequence[str],
        topology_bridge_candidates: Sequence[LensBridgeCandidate],
    ) -> SemanticPlaneCoverage:
        selected_families = tuple(
            sorted({spec.family for spec in selection.lenses}, key=lambda item: item.value)
        )
        finding_families = tuple(
            sorted({item.family for item in audit.accepted}, key=lambda item: item.value)
        )
        selected_roles = tuple(
            sorted({spec.role for spec in selection.lenses}, key=lambda item: item.value)
        )
        all_families = tuple(sorted(LensFamily, key=lambda item: item.value))
        all_roles = tuple(sorted(SemanticRole, key=lambda item: item.value))
        missing_families = tuple(
            family for family in all_families if family not in selected_families
        )
        missing_roles = tuple(
            role for role in all_roles if role not in selected_roles
        )
        family_coverage = len(selected_families) / max(1, len(all_families))
        role_coverage = len(selected_roles) / max(1, len(all_roles))
        rare_fraction = (
            sum(1 for spec in selection.lenses if spec.rare)
            / max(1, len(selection.lenses))
        )
        adversarial = SemanticRole.ADVERSARIAL_READING in selected_roles
        fingerprint = stable_fingerprint(
            {
                "selected_families": [item.value for item in selected_families],
                "finding_families": [item.value for item in finding_families],
                "selected_roles": [item.value for item in selected_roles],
                "missing_families": [item.value for item in missing_families],
                "missing_roles": [item.value for item in missing_roles],
                "family_coverage": family_coverage,
                "role_coverage": role_coverage,
                "rare_fraction": rare_fraction,
                "adversarial": adversarial,
                "accepted": len(audit.accepted),
                "rejected": len(audit.rejected),
                "interactions": len(composition.interactions),
                "hyperedges": len(hypergraph.edges),
                "conflicts": len(composition.unresolved_conflicts),
                "perpendicular": len(perpendicular.candidates),
                "forecasts": len(forecasts),
                "effective_lenses": fusion.effective_lens_count,
                "tangents": sorted(tangent_ids),
                "frontier": frontier.fingerprint,
                "topology": topology.fingerprint,
                "topology_learning": topology_learning.fingerprint,
                "learned_topology_rules": [
                    item.fingerprint for item in learned_topology_rules
                ],
                "learned_companion_keys": sorted(
                    set(learned_companion_keys)
                ),
                "topology_bridge_candidates": [
                    item.candidate_id for item in topology_bridge_candidates
                ],
            }
        )
        return SemanticPlaneCoverage(
            selected_families=selected_families,
            finding_families=finding_families,
            selected_roles=selected_roles,
            missing_families=missing_families,
            missing_roles=missing_roles,
            family_coverage=family_coverage,
            role_coverage=role_coverage,
            rare_fraction=rare_fraction,
            adversarial_selected=adversarial,
            accepted_findings=len(audit.accepted),
            rejected_findings=len(audit.rejected),
            pairwise_interactions=len(composition.interactions),
            hyperedges=len(hypergraph.edges),
            unresolved_conflicts=len(composition.unresolved_conflicts),
            perpendicular_candidates=len(perpendicular.candidates),
            forecast_count=len(forecasts),
            fused_effective_lens_count=fusion.effective_lens_count,
            tangent_count=len(tuple(tangent_ids)),
            frontier_tangent_count=len(frontier.tangent_ids),
            topology_components=topology.component_count,
            topology_isolated_lenses=len(topology.isolated_lens_keys),
            topology_bridge_lenses=len(topology.bridge_lens_keys),
            topology_candidate_bridges=len(topology_bridge_candidates),
            topology_learned_bridges=len(learned_topology_rules),
            topology_active_learning_reports=len(
                topology_learning.active_report_ids
            ),
            learned_companion_lenses=len(
                tuple(set(learned_companion_keys))
            ),
            fingerprint=fingerprint,
        )

    def analyze(
        self,
        observations: Sequence[SemanticObservation],
        *,
        findings: Sequence[SemanticFinding] = (),
        requested: Sequence[str] = (),
        base_rate: float | None = None,
        sequence: int = 0,
    ) -> SemanticPlaneSnapshot:
        if not observations:
            raise AgentContractError("semantic plane requires observations")
        if any(not isinstance(item, SemanticObservation) for item in observations):
            raise TypeError("observations must contain SemanticObservation values")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise AgentContractError("sequence must be a non-negative integer")
        observation_ids = [item.observation_id for item in observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise AgentContractError("semantic observation ids must be unique")

        (
            learned_topology_rules,
            topology_learning,
        ) = self.topology_learning.evaluate()
        selection = self.select(observations, requested=requested)
        (
            selection,
            learned_companion_activations,
        ) = self._augment_with_learned_companions(
            selection,
            observations,
            learned_topology_rules,
        )
        learned_companion_keys = tuple(
            item.lens_key
            for item in learned_companion_activations
        )
        governance = self.governance.assess(
            selection,
            observations=observations,
        )
        if (
            governance.factual_assertion_authorized
            or governance.causal_assertion_authorized
        ):
            raise AgentContractError(
                "semantic governance bridge violated evidence ceiling"
            )

        audit = self.audit_findings(
            findings,
            observations=observations,
            selection=selection,
        )
        perpendicular = self.perpendicular.plan(
            observations,
            findings=audit.accepted,
            selected_lens_keys=tuple(spec.key for spec in selection.lenses),
            maximum_axes=self.policy.max_perpendicular_axes,
        )
        composition = self.composition.compose(
            audit.accepted,
            supplemental_rules=tuple(
                item.rule for item in learned_topology_rules
            ),
        )

        calibration_weights = dict(governance.predictive_weights)
        hypergraph = self.hypergraph.build(
            audit.accepted,
            calibration_weights=calibration_weights,
        )

        forecast_findings = tuple(
            finding
            for finding in audit.accepted
            if finding.status is not ReadingStatus.FALSIFIED
            and finding.lens_key not in governance.forecast_blocked_lens_keys
        )
        proposal = self.predictive.propose(
            forecast_findings,
            composition=(
                composition if self.policy.include_interaction_forecasts else None
            ),
        )
        falsified_finding_ids = {
            finding.finding_id
            for finding in audit.accepted
            if finding.status is ReadingStatus.FALSIFIED
        }
        blocked_interaction_ids = {
            interaction.interaction_id
            for interaction in composition.interactions
            if interaction.left_finding_id in falsified_finding_ids
            or interaction.right_finding_id in falsified_finding_ids
        }
        eligible_proposal = tuple(
            forecast
            for forecast in proposal
            if not (set(forecast.source_finding_ids) & falsified_finding_ids)
            and not (set(forecast.source_interaction_ids) & blocked_interaction_ids)
        )
        forecasts = self._register_open_forecasts(
            eligible_proposal,
            governance,
        )
        signals = self._signals(forecasts, governance)
        rate = self.policy.base_rate if base_rate is None else probability(
            "base_rate", base_rate
        )
        fusion = self.fusion.fuse(signals, base_rate=rate)

        tangent_ids, frontier = self._seed_tangent_frontier(
            observations=observations,
            audit=audit,
            perpendicular=perpendicular,
            composition=composition,
            hypergraph=hypergraph,
            sequence=sequence,
        )
        decision_feature_authorized = self._decision_feature_authorized(
            forecasts=forecasts,
            governance=governance,
            composition=composition,
            fusion=fusion,
        ) and not bool(audit.rejected)
        topology = self.topology.snapshot_with_rules(
            tuple(item.rule for item in learned_topology_rules)
        )
        learned_candidate_ids = {
            item.candidate_id for item in learned_topology_rules
        }
        topology_bridge_candidates = tuple(
            item
            for item in self.topology.bridge_candidates(
                limit=self.policy.topology_bridge_limit,
                minimum_score=self.policy.topology_bridge_minimum_score,
                focus_keys=tuple(spec.key for spec in selection.lenses),
            )
            if item.candidate_id not in learned_candidate_ids
        )
        coverage = self._coverage(
            selection=selection,
            audit=audit,
            perpendicular=perpendicular,
            composition=composition,
            hypergraph=hypergraph,
            forecasts=forecasts,
            fusion=fusion,
            tangent_ids=tangent_ids,
            frontier=frontier,
            topology=topology,
            topology_learning=topology_learning,
            learned_topology_rules=learned_topology_rules,
            learned_companion_keys=learned_companion_keys,
            learned_companion_activations=(
                learned_companion_activations
            ),
            topology_bridge_candidates=topology_bridge_candidates,
        )
        runtime_state_fingerprint = self.runtime_state_fingerprint
        fingerprint = stable_fingerprint(
            {
                "observations": [item.fingerprint for item in observations],
                "selection": [
                    (
                        spec.key,
                        selection.activation_scores.get(spec.key, 0.0),
                    )
                    for spec in selection.lenses
                ],
                "governance": governance.fingerprint,
                "audit": audit.fingerprint,
                "perpendicular": perpendicular.fingerprint,
                "composition": composition.fingerprint,
                "hypergraph": hypergraph.fingerprint,
                "forecasts": [item.fingerprint for item in forecasts],
                "fusion": fusion.fingerprint,
                "tangents": tangent_ids,
                "frontier": frontier.fingerprint,
                "topology": topology.fingerprint,
                "topology_learning": topology_learning.fingerprint,
                "learned_topology_rules": [
                    item.fingerprint for item in learned_topology_rules
                ],
                "learned_companion_keys": learned_companion_keys,
                "learned_companion_activations": [
                    item.fingerprint
                    for item in learned_companion_activations
                ],
                "topology_bridge_candidates": [
                    item.candidate_id for item in topology_bridge_candidates
                ],
                "runtime_state_fingerprint": runtime_state_fingerprint,
                "coverage": coverage.fingerprint,
                "decision_feature_authorized": decision_feature_authorized,
                "factual": False,
                "causal": False,
            }
        )
        return SemanticPlaneSnapshot(
            observation_ids=tuple(observation_ids),
            selection=selection,
            governance=governance,
            finding_audit=audit,
            perpendicular=perpendicular,
            composition=composition,
            hypergraph=hypergraph,
            forecasts=forecasts,
            fusion=fusion,
            coverage=coverage,
            tangent_ids=tangent_ids,
            frontier=frontier,
            topology=topology,
            topology_learning=topology_learning,
            learned_topology_rules=learned_topology_rules,
            learned_companion_keys=learned_companion_keys,
            learned_companion_activations=(
                learned_companion_activations
            ),
            topology_bridge_candidates=topology_bridge_candidates,
            runtime_state_fingerprint=runtime_state_fingerprint,
            decision_feature_authorized=decision_feature_authorized,
            factual_assertion_authorized=False,
            causal_assertion_authorized=False,
            fingerprint=fingerprint,
        )

    def declare_topology_candidate_prediction(
        self,
        candidate_id: str,
        *,
        kind: LensInteractionKind,
        predicted_probability: float,
        domain: str,
        independent_run: str,
        predicted_at: float,
        negative_control: bool = False,
        source_finding_ids: Sequence[str] = (),
        source_forecast_ids: Sequence[str] = (),
        evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgePrediction:
        """Create and persist one canonical topology experiment prediction."""

        return self.topology_learning.declare_candidate_prediction(
            candidate_id,
            kind=kind,
            predicted_probability=predicted_probability,
            domain=domain,
            independent_run=independent_run,
            predicted_at=predicted_at,
            negative_control=negative_control,
            source_finding_ids=source_finding_ids,
            source_forecast_ids=source_forecast_ids,
            evidence_ids=evidence_ids,
            metadata=metadata,
        )

    def unresolved_topology_predictions(
        self,
        *,
        candidate_id: str | None = None,
    ) -> tuple[TopologyBridgePrediction, ...]:
        return self.topology_learning.unresolved_predictions(
            candidate_id=candidate_id,
        )

    def declare_topology_bridge_prediction(
        self,
        prediction: TopologyBridgePrediction,
    ) -> TopologyBridgePrediction:
        """Persist a topology bridge prediction before outcome observation."""

        return self.topology_learning.declare(prediction)

    def resolve_topology_bridge_prediction(
        self,
        prediction_id: str,
        *,
        outcome: bool,
        observed_at: float,
        outcome_evidence_ids: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> TopologyBridgeReport:
        """Resolve a declared bridge prediction and return its current report."""

        trial = self.topology_learning.resolve(
            prediction_id,
            outcome=outcome,
            observed_at=observed_at,
            outcome_evidence_ids=outcome_evidence_ids,
            metadata=metadata,
        )
        return self.topology_learning.report(
            trial.candidate_id,
            trial.kind,
        )

    def record_topology_bridge_trial(
        self,
        trial: TopologyBridgeTrial,
    ) -> TopologyBridgeReport:
        """Import a resolved trial only when its prediction is already declared."""

        recorded = self.topology_learning.record(trial)
        return self.topology_learning.report(
            recorded.candidate_id,
            recorded.kind,
        )

    def topology_learning_diagnostics(
        self,
        *,
        candidate_id: str | None = None,
        kind: LensInteractionKind | None = None,
        limit: int = 100,
    ) -> Mapping[str, Any]:
        return self.topology_learning.diagnostics(
            candidate_id=candidate_id,
            kind=kind,
            limit=limit,
        )

    def topology_research_obligations(
        self,
        *,
        limit: int = 24,
        minimum_candidate_score: float = 0.18,
        include_rejected: bool = False,
    ) -> tuple[KnowledgeObligation, ...]:
        """Emit unresolved semantic-topology gaps for the research frontier."""

        return self.topology_learning.research_obligations(
            limit=limit,
            minimum_candidate_score=minimum_candidate_score,
            include_rejected=include_rejected,
        )

    def export_topology_learning_state(
        self,
    ) -> SemanticTopologyLearningState:
        """Export topology-learning state for contract-bound persistence."""

        return self.topology_learning.export_state()

    def restore_topology_learning_state(
        self,
        state: SemanticTopologyLearningState | Mapping[str, Any],
    ) -> SemanticTopologyLearningSnapshot:
        """Restore topology learning only when the runtime contract matches."""

        return self.topology_learning.restore_state(state)

    def topology_learning_summary(self) -> Mapping[str, Any]:
        snapshot = self.topology_learning.snapshot()
        return {
            "prediction_count": snapshot.prediction_count,
            "unresolved_prediction_count": snapshot.unresolved_prediction_count,
            "trial_count": snapshot.trial_count,
            "tested_bridge_count": snapshot.tested_bridge_count,
            "active_report_ids": snapshot.active_report_ids,
            "restricted_report_ids": snapshot.restricted_report_ids,
            "rejected_report_ids": snapshot.rejected_report_ids,
            "candidate_report_ids": snapshot.candidate_report_ids,
            "ambiguous_active_candidate_ids": (
                snapshot.ambiguous_active_candidate_ids
            ),
            "learned_rule_keys": snapshot.learned_rule_keys,
            "snapshot_fingerprint": snapshot.fingerprint,
            "contract_fingerprint": (
                self.topology_learning.contract_fingerprint
            ),
            "invariants": {
                "cue_overlap_never_auto_promotes": True,
                "outcomes_require_predeclared_predictions": True,
                "each_prediction_resolves_at_most_once": True,
                "learned_bridges_remain_interpretive": True,
                "negative_controls_are_required": True,
                "replication_across_runs_and_domains_is_required": True,
                "learned_bridges_never_create_evidence": True,
            },
        }

    def resolve_forecast(
        self,
        forecast_id: str,
        *,
        outcome: bool,
        domain: str,
        independent_run: str,
        observed_at: float | None = None,
        observation_id: str | None = None,
        negative_control: bool = False,
    ) -> SemanticPlaneLearningUpdate:
        """Resolve a semantic forecast and feed its outcome back to lens science.

        Single-lens forecasts update that lens directly. Multi-lens interaction
        forecasts are calibrated under a composite key so one interaction
        outcome cannot be double-counted as independent evidence for each
        constituent lens.
        """
        domain_value = bounded_text("domain", domain, maximum=256).casefold()
        run_value = bounded_text(
            "independent_run", independent_run, maximum=512
        )
        resolved = self.prediction_ledger.resolve(
            forecast_id,
            outcome=outcome,
            observed_at=observed_at,
            observation_id=observation_id,
        )
        source_keys = tuple(sorted(set(resolved.source_lens_keys)))
        calibration_keys = (
            source_keys
            if len(source_keys) == 1
            else ("interaction:" + "+".join(source_keys),)
        )
        trials: list[LensOutcomeTrial] = []
        reports: list[ScientificLensReport] = []
        for key in calibration_keys:
            trial_id = stable_id(
                "semantic-plane-outcome",
                {
                    "forecast": resolved.forecast_id,
                    "forecast_fingerprint": resolved.fingerprint,
                    "lens_key": key,
                    "outcome": outcome,
                    "domain": domain_value,
                    "run": run_value,
                    "negative_control": negative_control,
                },
                length=32,
            )
            trial = LensOutcomeTrial(
                trial_id=trial_id,
                lens_key=key,
                probability=resolved.probability,
                outcome=outcome,
                domain=domain_value,
                independent_run=run_value,
                proposition=resolved.proposition,
                negative_control=negative_control,
                source_finding_id=(
                    resolved.source_finding_ids[0]
                    if len(resolved.source_finding_ids) == 1
                    else None
                ),
                observation_ids=resolved.observation_ids,
                evidence_ids=resolved.evidence_ids,
                metadata={
                    "semantic_plane": True,
                    "forecast_id": resolved.forecast_id,
                    "forecast_fingerprint": resolved.fingerprint,
                    "source_lens_keys": list(source_keys),
                    "interaction_calibration": len(source_keys) > 1,
                },
            )
            recorded = self.governance.registry.lab.record(trial)
            trials.append(recorded)
            reports.append(self.governance.registry.lab.report(key))

        fingerprint = stable_fingerprint(
            {
                "forecast": resolved.fingerprint,
                "trials": [trial.fingerprint for trial in trials],
                "reports": [report.fingerprint for report in reports],
            }
        )
        return SemanticPlaneLearningUpdate(
            forecast=resolved,
            trial_ids=tuple(trial.trial_id for trial in trials),
            calibrated_keys=calibration_keys,
            reports=tuple(reports),
            fingerprint=fingerprint,
        )

    @property
    def runtime_state_fingerprint(self) -> str:
        """Fingerprint mutable semantic state that can affect run behavior."""

        return stable_fingerprint(
            {
                "contract": self.fingerprint,
                "governance": self.governance.registry.fingerprint,
                "prediction_ledger": self.prediction_ledger.fingerprint,
                "tangent_graph": self.tangent_graph.fingerprint,
                "topology_learning": self.topology_learning.fingerprint,
            }
        )

    @property
    def fingerprint(self) -> str:
        # Runtime/checkpoint identity binds the semantic contract, not mutable
        # calibration outcomes. Scientific trial ledgers may legitimately grow
        # between runs without changing which operators or safety rules exist.
        return stable_fingerprint(
            {
                "registry": [
                    (
                        spec.key,
                        spec.family.value,
                        spec.role.value,
                        spec.lineage_year,
                        spec.minimum_observations,
                        spec.pairwise,
                        spec.sequential,
                        spec.rare,
                    )
                    for spec in self.registry.all()
                ],
                "topology": self.topology.fingerprint,
                "topology_learning_contract": (
                    self.topology_learning.contract_fingerprint
                ),
                "interaction_rules": [
                    (
                        rule.key,
                        rule.kind.value,
                        rule.symmetric,
                        rule.tangent_axis_hint,
                    )
                    for rule in (
                        *default_interaction_rules(),
                        *plane_interaction_rules(),
                        *depth_interaction_rules(),
                    )
                ],
                "policy": {
                    "max_lenses": self.policy.max_lenses,
                    "max_per_family": self.policy.max_per_family,
                    "minimum_rare": self.policy.minimum_rare_when_supported,
                    "max_axes": self.policy.max_perpendicular_axes,
                    "frontier_limit": self.policy.frontier_limit,
                    "frontier_max_per_axis": self.policy.frontier_max_per_axis,
                    "frontier_max_per_family": self.policy.frontier_max_per_family,
                    "topology_bridge_limit": self.policy.topology_bridge_limit,
                    "topology_bridge_minimum_score": self.policy.topology_bridge_minimum_score,
                    "enable_learned_companions": self.policy.enable_learned_companions,
                    "max_learned_companions": self.policy.max_learned_companions,
                    "minimum_learned_companion_cue_support": (
                        self.policy.minimum_learned_companion_cue_support
                    ),
                    "minimum_learned_companion_bridge_quality": (
                        self.policy.minimum_learned_companion_bridge_quality
                    ),
                    "require_selected": self.policy.require_selected_findings,
                    "require_overlap": self.policy.require_observation_overlap,
                    "require_observation_subset": self.policy.require_observation_subset,
                    "require_evidence_provenance": self.policy.require_evidence_provenance,
                    "interaction_forecasts": self.policy.include_interaction_forecasts,
                    "base_rate": self.policy.base_rate,
                },
            }
        )
