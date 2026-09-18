"""Maximal semantic-science orchestration for Jeeves.

This module joins the base semantic catalog, frontier catalog, rare research
lenses, scientific calibration, high-order hypergraph composition, and durable
perpendicular tangent graph behind one explicit runtime surface.

The runtime does not generate facts. It routes observations, composes supplied
findings, applies empirical lens weights when available, and preserves research
directions across restarts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .interpretive_science import ScientificLensLab
from .lens_hypergraph import SemanticHypergraphSnapshot, SemanticLensHypergraph
from .semantic_extreme_lenses import register_rare_lenses
from .semantic_depth_lenses import register_depth_lenses
from .semantic_research_lenses import register_research_lenses
from .semantic_plane_lenses import register_plane_lenses
from .semantic_plane_interactions import plane_interaction_rules
from .semantic_depth_interactions import depth_interaction_rules
from .semantic_frontier import (
    FrontierLensRouter,
    FrontierSemanticRegistry,
    LensCompositionEngine,
    SemanticComposition,
)
from .semantic_lenses import LensFamily, LensSelection, SemanticFinding, SemanticObservation
from .tangent_graph import ExplorationAxis, FrontierSelection, TangentGraph, TangentNode
from .types import AgentContractError, positive_int, stable_fingerprint


class MaximalSemanticRegistry(FrontierSemanticRegistry):
    """Base + frontier + rare + research + plane + depth lenses, de-duplicated by stable lens key."""

    def __init__(self) -> None:
        super().__init__()
        register_rare_lenses(self, ignore_existing=True)
        register_research_lenses(self, ignore_existing=True)
        register_plane_lenses(self, ignore_existing=True)
        register_depth_lenses(self, ignore_existing=True)


class MaximalLensRouter(FrontierLensRouter):
    """Wide but bounded router that still requires cue support for rare lenses."""

    def __init__(self, registry: MaximalSemanticRegistry | None = None) -> None:
        super().__init__(registry or MaximalSemanticRegistry())

    def select_maximal(
        self,
        observations: Sequence[SemanticObservation],
        *,
        requested: Sequence[str] = (),
        max_lenses: int = 28,
        max_per_family: int = 5,
        minimum_rare_when_supported: int = 3,
    ) -> LensSelection:
        return self.select_frontier(
            observations,
            requested=requested,
            max_lenses=max_lenses,
            max_per_family=max_per_family,
            minimum_rare_when_supported=minimum_rare_when_supported,
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


@dataclass(frozen=True, slots=True)
class MaximalSemanticSnapshot:
    finding_ids: tuple[str, ...]
    pairwise: SemanticComposition
    hypergraph: SemanticHypergraphSnapshot
    tangent_ids: tuple[str, ...]
    frontier: FrontierSelection
    scientific_weights: tuple[tuple[str, float], ...]
    fingerprint: str


class MaximalSemanticRuntime:
    """Orchestrate lens selection, composition, calibration and tangent continuity."""

    def __init__(
        self,
        *,
        registry: MaximalSemanticRegistry | None = None,
        lab: ScientificLensLab | None = None,
        graph: TangentGraph | None = None,
        hypergraph: SemanticLensHypergraph | None = None,
        pairwise: LensCompositionEngine | None = None,
    ) -> None:
        self.registry = registry or MaximalSemanticRegistry()
        self.router = MaximalLensRouter(self.registry)
        self.lab = lab or ScientificLensLab()
        self.graph = graph or TangentGraph()
        self.hypergraph = hypergraph or SemanticLensHypergraph()
        self.pairwise = pairwise or LensCompositionEngine((*plane_interaction_rules(), *depth_interaction_rules()))

    def select(
        self,
        observations: Sequence[SemanticObservation],
        *,
        requested: Sequence[str] = (),
        max_lenses: int = 28,
    ) -> LensSelection:
        maximum = positive_int("max_lenses", max_lenses, maximum=100)
        return self.router.select_maximal(observations, requested=requested, max_lenses=maximum)

    def _scientific_weights(self, findings: Sequence[SemanticFinding]) -> dict[str, float]:
        keys = sorted({finding.lens_key for finding in findings})
        return {key: self.lab.routing_weight(key, default_shadow_weight=0.10) for key in keys}

    def compose(
        self,
        findings: Sequence[SemanticFinding],
        *,
        sequence: int = 0,
        frontier_limit: int = 12,
    ) -> MaximalSemanticSnapshot:
        if not findings:
            raise AgentContractError("maximal semantic composition requires findings")
        if any(not isinstance(item, SemanticFinding) for item in findings):
            raise TypeError("findings must contain SemanticFinding values")
        sequence_value = int(sequence)
        if sequence_value < 0:
            raise AgentContractError("sequence must be non-negative")
        pairwise = self.pairwise.compose(findings)
        weights = self._scientific_weights(findings)
        hypergraph = self.hypergraph.build(findings, calibration_weights=weights)

        inserted: list[TangentNode] = []
        for seed in hypergraph.restart.tangent_seeds:
            family_name = seed.lens_key.partition(":")[2]
            try:
                family = LensFamily(family_name)
            except ValueError:
                family = None
            axis = _FAMILY_AXIS.get(family, ExplorationAxis.SEMANTIC)
            inserted.append(
                self.graph.add_seed(
                    seed,
                    axis=axis,
                    family=family,
                    sequence=sequence_value,
                    trigger_terms=tuple(seed.tags),
                    evidence_gap=0.80 if family in hypergraph.restart.missing_families else 0.60,
                )
            )

        frontier = self.graph.frontier(limit=positive_int("frontier_limit", frontier_limit, maximum=1000))
        payload = {
            "findings": sorted(item.fingerprint for item in findings),
            "pairwise": pairwise.fingerprint,
            "hypergraph": hypergraph.fingerprint,
            "tangents": sorted(node.tangent_id for node in inserted),
            "frontier": frontier.fingerprint,
            "weights": sorted(weights.items()),
        }
        return MaximalSemanticSnapshot(
            finding_ids=tuple(sorted(item.finding_id for item in findings)),
            pairwise=pairwise,
            hypergraph=hypergraph,
            tangent_ids=tuple(sorted(node.tangent_id for node in inserted)),
            frontier=frontier,
            scientific_weights=tuple(sorted(weights.items())),
            fingerprint=stable_fingerprint(payload),
        )

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "registry": [spec.key for spec in self.registry.all()],
            "lab": self.lab.fingerprint,
            "graph": self.graph.fingerprint,
        })