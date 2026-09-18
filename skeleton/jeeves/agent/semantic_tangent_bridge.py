"""Bridge semantic ambiguity into the durable perpendicular tangent frontier.

A restart, replan, provider failover, or context compaction must not silently
erase promising alternative interpretations.  This bridge converts semantic
findings and cross-lens conflicts into ordinary :class:`TangentGraph` nodes,
then snapshots a restart packet that preserves both the graph frontier and the
unresolved semantic conflict fingerprints.

Nothing here promotes a semantic tangent into evidence.  Promotion remains an
explicit later action after a tangent is tested against observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .perpendicular_semantics import PerpendicularExpansionPlan
from .semantic_frontier import SemanticComposition
from .semantic_lenses import LensFamily, SemanticFinding, TangentSeed
from .tangent_graph import ExplorationAxis, FrontierSelection, RestartContinuityBundle, TangentGraph, TangentNode
from .types import AgentContractError, positive_int, probability, stable_fingerprint, stable_id


_FAMILY_AXIS: Mapping[LensFamily, ExplorationAxis] = {
    LensFamily.FILM: ExplorationAxis.CINEMATIC,
    LensFamily.LITERATURE: ExplorationAxis.LITERARY,
    LensFamily.GAME: ExplorationAxis.LUDIC,
    LensFamily.NARRATIVE: ExplorationAxis.SEMANTIC,
    LensFamily.SEMIOTIC: ExplorationAxis.SEMANTIC,
    LensFamily.COGNITIVE: ExplorationAxis.SEMANTIC,
    LensFamily.RHETORIC: ExplorationAxis.SEMANTIC,
    LensFamily.SOCIAL: ExplorationAxis.SOCIAL,
    LensFamily.TEMPORAL: ExplorationAxis.TEMPORAL,
    LensFamily.SYSTEM: ExplorationAxis.SYSTEM,
}

_AXIS_HINTS: Mapping[str, ExplorationAxis] = {
    "causal": ExplorationAxis.CAUSAL,
    "probabilistic": ExplorationAxis.PROBABILISTIC,
    "temporal": ExplorationAxis.TEMPORAL,
    "semantic": ExplorationAxis.SEMANTIC,
    "cinematic": ExplorationAxis.CINEMATIC,
    "literary": ExplorationAxis.LITERARY,
    "ludic": ExplorationAxis.LUDIC,
    "social": ExplorationAxis.SOCIAL,
    "adversarial": ExplorationAxis.ADVERSARIAL,
    "system": ExplorationAxis.SYSTEM,
    "memory": ExplorationAxis.MEMORY,
    "compiler": ExplorationAxis.COMPILER,
}


@dataclass(frozen=True, slots=True)
class SemanticRestartPacket:
    root_fingerprint: str
    graph_bundle: RestartContinuityBundle
    frontier: FrontierSelection
    unresolved_conflict_ids: tuple[str, ...]
    unresolved_conflict_fingerprints: tuple[str, ...]
    semantic_finding_fingerprints: tuple[str, ...]
    prediction_ids: tuple[str, ...]
    packet_fingerprint: str


@dataclass(frozen=True, slots=True)
class TangentBridgePolicy:
    minimum_novelty: float = 0.25
    minimum_expected_value: float = 0.20
    minimum_ambiguity_for_tangent: float = 0.30
    default_evidence_gap: float = 0.65
    default_risk: float = 0.10
    frontier_limit: int = 12
    max_per_axis: int = 2
    max_per_family: int = 3

    def __post_init__(self) -> None:
        for name in (
            "minimum_novelty", "minimum_expected_value", "minimum_ambiguity_for_tangent",
            "default_evidence_gap", "default_risk",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        for name in ("frontier_limit", "max_per_axis", "max_per_family"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=1000))


class SemanticTangentBridge:
    def __init__(self, graph: TangentGraph | None = None, *, policy: TangentBridgePolicy | None = None) -> None:
        self.graph = graph or TangentGraph()
        self.policy = policy or TangentBridgePolicy()

    @staticmethod
    def _axis_for(family: LensFamily, *, hint: str | None = None) -> ExplorationAxis:
        if hint:
            mapped = _AXIS_HINTS.get(str(hint).casefold())
            if mapped is not None:
                return mapped
        return _FAMILY_AXIS.get(family, ExplorationAxis.SEMANTIC)

    def ingest_finding(self, finding: SemanticFinding, *, root_fingerprint: str, sequence: int) -> TangentNode | None:
        if finding.novelty < self.policy.minimum_novelty:
            return None
        if finding.ambiguity < self.policy.minimum_ambiguity_for_tangent and not finding.counterreading.strip():
            return None
        expected = max(0.0, min(1.0, finding.confidence * (0.5 + 0.5 * finding.novelty)))
        if expected < self.policy.minimum_expected_value:
            return None
        direction = (
            finding.counterreading.strip()
            or finding.prediction.strip()
            or f"Discriminate the {finding.lens_key} interpretation against a plausible alternative."
        )
        seed = TangentSeed(
            seed_id=stable_id("finding-tangent", {"finding": finding.fingerprint, "root": root_fingerprint}, length=28),
            parent_fingerprint=root_fingerprint,
            lens_key=finding.lens_key,
            direction=direction,
            rationale=(
                f"Semantic reading remains provisional: confidence={finding.confidence:.3f}, "
                f"ambiguity={finding.ambiguity:.3f}, novelty={finding.novelty:.3f}."
            ),
            novelty=finding.novelty,
            expected_value=expected,
            evidence_ids=finding.evidence_ids,
            tags=("semantic-finding", finding.family.value, finding.status.value),
        )
        return self.graph.add_seed(
            seed,
            axis=self._axis_for(finding.family),
            family=finding.family,
            sequence=sequence,
            trigger_terms=(finding.lens_key, *finding.observation_ids),
            risk=self.policy.default_risk,
            evidence_gap=max(self.policy.default_evidence_gap, finding.ambiguity),
        )

    def ingest_composition(
        self,
        composition: SemanticComposition,
        *,
        root_fingerprint: str,
        sequence: int,
    ) -> tuple[TangentNode, ...]:
        """Add composition tangents under the same durable run root.

        ``LensCompositionEngine`` fingerprints a seed from the two readings that
        generated it.  That local fingerprint is useful provenance, but a graph
        checkpoint groups by ``root_fingerprint``.  We therefore preserve the
        local fingerprint as metadata/tag material while rebinding the seed's
        graph root to the run/restart root supplied here.
        """
        added: list[TangentNode] = []
        for seed in composition.tangent_seeds:
            interaction = next(
                (item for item in composition.interactions if item.tangent and item.tangent.seed_id == seed.seed_id),
                None,
            )
            hint = interaction.rule.tangent_axis_hint if interaction is not None else None
            axis = _AXIS_HINTS.get(str(hint).casefold(), ExplorationAxis.SEMANTIC) if hint else ExplorationAxis.SEMANTIC
            normalized_seed = TangentSeed(
                seed_id=seed.seed_id,
                parent_fingerprint=root_fingerprint,
                lens_key=seed.lens_key,
                direction=seed.direction,
                rationale=seed.rationale,
                novelty=seed.novelty,
                expected_value=seed.expected_value,
                evidence_ids=seed.evidence_ids,
                tags=tuple(sorted(set(seed.tags) | {f"local-root:{seed.parent_fingerprint[:24]}"})),
            )
            try:
                node = self.graph.add_seed(
                    normalized_seed,
                    axis=axis,
                    family=None,
                    sequence=sequence,
                    trigger_terms=(seed.lens_key, *(interaction.observation_ids if interaction else ())),
                    risk=self.policy.default_risk,
                    evidence_gap=max(self.policy.default_evidence_gap, interaction.ambiguity if interaction else 0.5),
                )
            except AgentContractError as exc:
                existing_id = stable_id(
                    "tangent",
                    {
                        "seed": normalized_seed.seed_id,
                        "parent": None,
                        "root": root_fingerprint,
                        "axis": axis.value,
                        "direction": normalized_seed.direction,
                    },
                    length=32,
                )
                existing = self.graph.get(existing_id)
                if existing is None:
                    raise exc
                node = existing
            added.append(node)
        return tuple(added)

    def ingest(
        self,
        findings: Sequence[SemanticFinding],
        *,
        composition: SemanticComposition | None,
        root_fingerprint: str,
        sequence: int,
    ) -> tuple[TangentNode, ...]:
        added: list[TangentNode] = []
        for finding in findings:
            node = self.ingest_finding(finding, root_fingerprint=root_fingerprint, sequence=sequence)
            if node is not None:
                added.append(node)
        if composition is not None:
            added.extend(
                self.ingest_composition(
                    composition,
                    root_fingerprint=root_fingerprint,
                    sequence=sequence,
                )
            )
        unique = {node.tangent_id: node for node in added}
        return tuple(sorted(unique.values(), key=lambda node: node.tangent_id))

    def ingest_perpendicular(
        self,
        plan: PerpendicularExpansionPlan,
        *,
        root_fingerprint: str,
        sequence: int,
    ) -> tuple[TangentNode, ...]:
        """Persist cue-supported orthogonal directions before restart/replan."""

        if not isinstance(plan, PerpendicularExpansionPlan):
            raise TypeError("plan must be PerpendicularExpansionPlan")
        added: list[TangentNode] = []
        for candidate in plan.candidates:
            axis = (
                ExplorationAxis.ADVERSARIAL
                if candidate.role.value == "adversarial_reading"
                else self._axis_for(candidate.family)
            )
            seed = TangentSeed(
                seed_id=stable_id(
                    "perpendicular-semantic",
                    {
                        "root": root_fingerprint,
                        "plan": plan.fingerprint,
                        "lens": candidate.lens_key,
                        "direction": candidate.direction,
                    },
                    length=28,
                ),
                parent_fingerprint=root_fingerprint,
                lens_key=candidate.lens_key,
                direction=candidate.direction,
                rationale=candidate.rationale,
                novelty=max(candidate.family_novelty, candidate.role_novelty),
                expected_value=candidate.expected_value,
                evidence_ids=(),
                tags=(
                    "perpendicular",
                    "semantic-research-direction",
                    candidate.family.value,
                    candidate.role.value,
                ),
            )
            try:
                node = self.graph.add_seed(
                    seed,
                    axis=axis,
                    family=candidate.family,
                    sequence=sequence,
                    trigger_terms=(candidate.lens_key, *candidate.trigger_terms),
                    risk=self.policy.default_risk,
                    evidence_gap=candidate.evidence_gap,
                )
            except AgentContractError as exc:
                existing_id = stable_id(
                    "tangent",
                    {
                        "seed": seed.seed_id,
                        "parent": None,
                        "root": root_fingerprint,
                        "axis": axis.value,
                        "direction": seed.direction,
                    },
                    length=32,
                )
                existing = self.graph.get(existing_id)
                if existing is None:
                    raise exc
                node = existing
            added.append(node)
        unique = {node.tangent_id: node for node in added}
        return tuple(sorted(unique.values(), key=lambda node: node.tangent_id))

    def restart_packet(
        self,
        *,
        root_fingerprint: str,
        sequence: int,
        findings: Sequence[SemanticFinding] = (),
        composition: SemanticComposition | None = None,
        prediction_ids: Sequence[str] = (),
        notes: str = "semantic frontier before restart",
    ) -> SemanticRestartPacket:
        graph_bundle = self.graph.checkpoint(root_fingerprint=root_fingerprint, sequence=sequence, notes=notes)
        frontier = self.graph.frontier(
            limit=self.policy.frontier_limit,
            max_per_axis=self.policy.max_per_axis,
            max_per_family=self.policy.max_per_family,
            include_parked=True,
        )
        conflict_ids = tuple(sorted(composition.unresolved_conflicts if composition is not None else ()))
        interactions = {item.interaction_id: item for item in (composition.interactions if composition is not None else ())}
        conflict_fingerprints = tuple(
            sorted(interactions[item_id].fingerprint for item_id in conflict_ids if item_id in interactions)
        )
        finding_fingerprints = tuple(sorted(item.fingerprint for item in findings))
        predictions = tuple(sorted({str(item) for item in prediction_ids if str(item)}))
        packet_fingerprint = stable_fingerprint(
            {
                "root": root_fingerprint,
                "sequence": sequence,
                "graph": graph_bundle.graph_fingerprint,
                "frontier": frontier.fingerprint,
                "conflicts": conflict_fingerprints,
                "findings": finding_fingerprints,
                "predictions": predictions,
            }
        )
        return SemanticRestartPacket(
            root_fingerprint=root_fingerprint,
            graph_bundle=graph_bundle,
            frontier=frontier,
            unresolved_conflict_ids=conflict_ids,
            unresolved_conflict_fingerprints=conflict_fingerprints,
            semantic_finding_fingerprints=finding_fingerprints,
            prediction_ids=predictions,
            packet_fingerprint=packet_fingerprint,
        )
