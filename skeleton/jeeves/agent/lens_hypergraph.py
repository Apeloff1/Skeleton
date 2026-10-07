"""Hypergraph composition for high-order semantic nuance.

Pairwise lens interactions miss structures that only appear when three or more
independent views constrain the same observations. This module builds bounded
hyperedges over SemanticFinding objects, preserves contradiction, applies
calibration caps, and emits perpendicular tangents for missing lens families.

Hyperedges remain interpretive structures. They cannot create evidence or raise
source trust. Their main jobs are search control, falsifier generation, and
predictive feature construction.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .semantic_lenses import LensFamily, ReadingStatus, SemanticFinding, TangentSeed
from .types import AgentContractError, json_safe, positive_int, probability, stable_fingerprint, stable_id


class HyperedgeKind(str, Enum):
    CONVERGENCE = "convergence"
    CONDITIONAL = "conditional"
    CONTRADICTION = "contradiction"
    PERSPECTIVE_SPLIT = "perspective_split"
    TEMPORAL_CHAIN = "temporal_chain"
    SYSTEMIC = "systemic"
    CAUSAL_CHAIN = "causal_chain"
    INFORMATION_FLOW = "information_flow"
    COMPUTATIONAL_CONSTRAINT = "computational_constraint"
    EPISTEMIC_CONTROL = "epistemic_control"
    PROBABILISTIC_DEPENDENCE = "probabilistic_dependence"
    PREDICTIVE_REGIME = "predictive_regime"
    EXPLORATORY = "exploratory"


@dataclass(frozen=True, slots=True)
class LensHyperedge:
    edge_id: str
    finding_ids: tuple[str, ...]
    lens_keys: tuple[str, ...]
    families: tuple[LensFamily, ...]
    observation_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    kind: HyperedgeKind
    confidence: float
    ambiguity: float
    family_diversity: float
    calibration_support: float
    overlap: float
    unresolved: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.edge_id or len(self.finding_ids) < 2:
            raise AgentContractError("hyperedge requires id and at least two findings")
        if not isinstance(self.kind, HyperedgeKind):
            object.__setattr__(self, "kind", HyperedgeKind(str(self.kind)))
        for name in ("confidence", "ambiguity", "family_diversity", "calibration_support", "overlap"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(self, "finding_ids", tuple(sorted({str(x) for x in self.finding_ids if str(x)})))
        object.__setattr__(self, "lens_keys", tuple(sorted({str(x).casefold() for x in self.lens_keys if str(x)})))
        object.__setattr__(self, "families", tuple(sorted(set(self.families), key=lambda x: x.value)))
        object.__setattr__(self, "observation_ids", tuple(sorted({str(x) for x in self.observation_ids if str(x)})))
        object.__setattr__(self, "evidence_ids", tuple(sorted({str(x) for x in self.evidence_ids if str(x)})))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "findings": self.finding_ids,
            "lenses": self.lens_keys,
            "families": [x.value for x in self.families],
            "observations": self.observation_ids,
            "evidence": self.evidence_ids,
            "kind": self.kind.value,
            "confidence": self.confidence,
            "ambiguity": self.ambiguity,
            "calibration": self.calibration_support,
            "overlap": self.overlap,
            "unresolved": self.unresolved,
        })


@dataclass(frozen=True, slots=True)
class HypergraphPolicy:
    max_order: int = 5
    max_findings: int = 64
    max_edges: int = 512
    minimum_observation_overlap: float = 0.20
    minimum_edge_confidence: float = 0.18
    minimum_family_diversity: float = 0.20
    default_calibration_weight: float = 0.10
    contradiction_ambiguity_floor: float = 0.60
    confidence_cap: float = 0.78
    tangent_limit: int = 16

    def __post_init__(self) -> None:
        for name in ("max_order", "max_findings", "max_edges", "tangent_limit"):
            object.__setattr__(self, name, positive_int(name, getattr(self, name), maximum=10_000))
        if self.max_order < 2 or self.max_order > 8:
            raise AgentContractError("max_order must be in [2, 8]")
        for name in (
            "minimum_observation_overlap", "minimum_edge_confidence", "minimum_family_diversity",
            "default_calibration_weight", "contradiction_ambiguity_floor", "confidence_cap",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class PerpendicularRestartBundle:
    parent_fingerprint: str
    represented_families: tuple[LensFamily, ...]
    missing_families: tuple[LensFamily, ...]
    tangent_seeds: tuple[TangentSeed, ...]
    edge_ids: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class SemanticHypergraphSnapshot:
    finding_ids: tuple[str, ...]
    edges: tuple[LensHyperedge, ...]
    restart: PerpendicularRestartBundle
    unresolved_edge_ids: tuple[str, ...]
    fingerprint: str


_FAMILY_QUESTIONS: dict[LensFamily, str] = {
    LensFamily.FILM: "Re-read the same observations as an ordering, framing, cut, sound, or viewpoint problem.",
    LensFamily.LITERATURE: "Test voice, textual layering, trope, narration, and implied-reader alternatives.",
    LensFamily.GAME: "Translate the state into rules, affordances, information sets, incentives, and reachable actions.",
    LensFamily.NARRATIVE: "Separate event order, telling order, focal access, setup/payoff, and omitted transitions.",
    LensFamily.SEMIOTIC: "Separate observed sign, relation type, convention, referent, and inferred meaning.",
    LensFamily.COGNITIVE: "Test retrieval, attention, prediction error, framing, interference, and memory-source explanations.",
    LensFamily.RHETORIC: "Test scope, implicature, presupposition, contrast, speech act, and audience assumptions.",
    LensFamily.SOCIAL: "Test actor-specific incentives, norms, roles, common knowledge, and strategic signaling.",
    LensFamily.TEMPORAL: "Change the time scale and reconstruct ordering, delay, recurrence, and horizon effects.",
    LensFamily.SYSTEM: "Search for invariants, feedback loops, interfaces, hidden state, failure modes, and alternative abstractions.",
    LensFamily.CAUSAL: "Construct competing causal graphs, interventions, confounders, mediators, and reverse-direction alternatives.",
    LensFamily.INFORMATION: "Measure uncertainty reduction, redundancy, synergy, bottlenecks, and value of additional observations.",
    LensFamily.COMPUTATIONAL: "Test complexity, concurrency, transactional boundaries, representation invariance, and abstraction leakage.",
    LensFamily.METACOGNITIVE: "Audit calibration, stopping, hypothesis diversity, reasoning loops, and unresolved epistemic debt.",
    LensFamily.PROBABILITY: "Reconstruct priors, dependence, tail mass, sequential validity, model mixtures, and uncertainty decomposition.",
    LensFamily.PREDICTIVE: "Stress horizons, dataset shift, regime change, indicators, interval coverage, and forecast coherence.",
}


class SemanticLensHypergraph:
    def __init__(self, *, policy: HypergraphPolicy | None = None) -> None:
        self.policy = policy or HypergraphPolicy()

    @staticmethod
    def _jaccard(groups: Sequence[set[str]]) -> float:
        nonempty = [group for group in groups if group]
        if not nonempty:
            return 0.0
        union = set().union(*nonempty)
        if not union:
            return 0.0
        # Multi-way overlap is intentionally permissive: use average pairwise Jaccard.
        if len(nonempty) == 1:
            return 1.0
        scores: list[float] = []
        for left, right in itertools.combinations(nonempty, 2):
            scores.append(len(left & right) / max(1, len(left | right)))
        return sum(scores) / len(scores)

    def _kind(self, items: Sequence[SemanticFinding]) -> HyperedgeKind:
        statuses = {item.status for item in items}
        if ReadingStatus.CONTESTED in statuses or ReadingStatus.FALSIFIED in statuses or any(item.counterreading.strip() for item in items):
            return HyperedgeKind.CONTRADICTION
        families = {item.family for item in items}
        roles = {item.metadata.get("role") for item in items if item.metadata.get("role")}
        if LensFamily.TEMPORAL in families or any("temporal" in item.lens_key for item in items):
            return HyperedgeKind.TEMPORAL_CHAIN
        if LensFamily.CAUSAL in families:
            return HyperedgeKind.CAUSAL_CHAIN
        if LensFamily.INFORMATION in families:
            return HyperedgeKind.INFORMATION_FLOW
        if LensFamily.COMPUTATIONAL in families:
            return HyperedgeKind.COMPUTATIONAL_CONSTRAINT
        if LensFamily.METACOGNITIVE in families:
            return HyperedgeKind.EPISTEMIC_CONTROL
        if LensFamily.PROBABILITY in families:
            return HyperedgeKind.PROBABILISTIC_DEPENDENCE
        if LensFamily.PREDICTIVE in families:
            return HyperedgeKind.PREDICTIVE_REGIME
        if sum(item.family in {LensFamily.NARRATIVE, LensFamily.FILM, LensFamily.LITERATURE} for item in items) >= 2:
            return HyperedgeKind.PERSPECTIVE_SPLIT
        if LensFamily.SYSTEM in families or LensFamily.GAME in families:
            return HyperedgeKind.SYSTEMIC
        if len(families) >= 3:
            return HyperedgeKind.CONVERGENCE
        if roles:
            return HyperedgeKind.CONDITIONAL
        return HyperedgeKind.EXPLORATORY

    def _edge(
        self,
        items: Sequence[SemanticFinding],
        calibration_weights: Mapping[str, float],
    ) -> LensHyperedge | None:
        observation_sets = [set(item.observation_ids) for item in items]
        overlap = self._jaccard(observation_sets)
        if overlap < self.policy.minimum_observation_overlap:
            return None
        families = {item.family for item in items}
        # Diversity must be intrinsic to this edge. Using the size of the
        # global LensFamily enum made existing edges weaker whenever the
        # catalog gained a new family. Normalize by the maximum diversity the
        # current edge order can express instead.
        family_diversity = (
            1.0
            if len(items) <= 1
            else (len(families) - 1) / max(1, len(items) - 1)
        )
        if family_diversity < self.policy.minimum_family_diversity:
            return None
        calibration = [
            probability("calibration weight", calibration_weights.get(item.lens_key, self.policy.default_calibration_weight))
            for item in items
        ]
        calibration_support = sum(calibration) / len(calibration)
        # Geometric mean penalizes one weak member and avoids a single high score dominating.
        raw_confidence = math.prod(max(1e-9, item.confidence) for item in items) ** (1.0 / len(items))
        ambiguity = max(item.ambiguity for item in items)
        kind = self._kind(items)
        if kind is HyperedgeKind.CONTRADICTION:
            ambiguity = max(ambiguity, self.policy.contradiction_ambiguity_floor)
        diversity_bonus = 0.15 * family_diversity
        calibration_factor = 0.45 + 0.55 * calibration_support
        confidence = min(
            self.policy.confidence_cap,
            max(0.0, raw_confidence * calibration_factor + diversity_bonus * (1.0 - ambiguity)),
        )
        if confidence < self.policy.minimum_edge_confidence:
            return None
        finding_ids = tuple(sorted(item.finding_id for item in items))
        lens_keys = tuple(sorted(item.lens_key for item in items))
        observations = tuple(sorted(set().union(*(set(item.observation_ids) for item in items))))
        evidence = tuple(sorted(set().union(*(set(item.evidence_ids) for item in items))))
        unresolved = kind is HyperedgeKind.CONTRADICTION
        edge_id = stable_id("semantic-hyperedge", {
            "findings": finding_ids, "lenses": lens_keys, "kind": kind.value, "observations": observations
        }, length=30)
        return LensHyperedge(
            edge_id=edge_id,
            finding_ids=finding_ids,
            lens_keys=lens_keys,
            families=tuple(families),
            observation_ids=observations,
            evidence_ids=evidence,
            kind=kind,
            confidence=confidence,
            ambiguity=ambiguity,
            family_diversity=family_diversity,
            calibration_support=calibration_support,
            overlap=overlap,
            unresolved=unresolved,
            metadata={
                "interpretive_only": True,
                "may_promote_to_evidence": False,
                "order": len(items),
                "raw_confidence": raw_confidence,
            },
        )

    def _restart_bundle(self, findings: Sequence[SemanticFinding], edges: Sequence[LensHyperedge]) -> PerpendicularRestartBundle:
        represented = tuple(sorted({item.family for item in findings}, key=lambda x: x.value))
        all_families = tuple(sorted(LensFamily, key=lambda x: x.value))
        missing = tuple(family for family in all_families if family not in represented)
        parent = stable_fingerprint(sorted(item.fingerprint for item in findings))
        seeds: list[TangentSeed] = []
        # Missing families are highest-value perpendicular directions. If all are represented,
        # revisit weakest represented families with an explicit falsification direction.
        target_families = missing or represented
        for family in target_families[: self.policy.tangent_limit]:
            rationale = (
                f"Perpendicular restart through {family.value}; preserve existing readings while testing an independent abstraction."
                if family in missing
                else f"Adversarial restart within {family.value}; search for evidence that would falsify the current cluster."
            )
            direction = _FAMILY_QUESTIONS.get(family, f"Investigate the {family.value} interpretation independently.")
            seed_id = stable_id("perpendicular-tangent", {
                "parent": parent, "family": family.value, "direction": direction
            }, length=28)
            seeds.append(TangentSeed(
                seed_id=seed_id,
                parent_fingerprint=parent,
                lens_key=f"perpendicular:{family.value}",
                direction=direction,
                rationale=rationale,
                novelty=1.0 if family in missing else 0.55,
                expected_value=0.62 if family in missing else 0.45,
                evidence_ids=tuple(sorted(set().union(*(set(item.evidence_ids) for item in findings)))),
                tags=("perpendicular", "restart", family.value),
            ))
        fingerprint = stable_fingerprint({
            "parent": parent,
            "represented": [x.value for x in represented],
            "missing": [x.value for x in missing],
            "seeds": [seed.seed_id for seed in seeds],
            "edges": [edge.edge_id for edge in edges],
        })
        return PerpendicularRestartBundle(
            parent_fingerprint=parent,
            represented_families=represented,
            missing_families=missing,
            tangent_seeds=tuple(seeds),
            edge_ids=tuple(edge.edge_id for edge in edges),
            fingerprint=fingerprint,
        )

    def build(
        self,
        findings: Sequence[SemanticFinding],
        *,
        calibration_weights: Mapping[str, float] | None = None,
    ) -> SemanticHypergraphSnapshot:
        if any(not isinstance(item, SemanticFinding) for item in findings):
            raise TypeError("findings must contain SemanticFinding values")
        calibration_weights = calibration_weights or {}
        ranked = sorted(
            findings,
            key=lambda item: (item.confidence * (1.0 - 0.5 * item.ambiguity), item.novelty, item.finding_id),
            reverse=True,
        )[: self.policy.max_findings]
        edges: list[LensHyperedge] = []
        for order in range(2, min(self.policy.max_order, len(ranked)) + 1):
            for combo in itertools.combinations(ranked, order):
                edge = self._edge(combo, calibration_weights)
                if edge is not None:
                    edges.append(edge)
                if len(edges) >= self.policy.max_edges:
                    break
            if len(edges) >= self.policy.max_edges:
                break
        edges.sort(
            key=lambda edge: (edge.unresolved, edge.confidence, edge.family_diversity, edge.overlap, edge.edge_id),
            reverse=True,
        )
        restart = self._restart_bundle(ranked, edges)
        unresolved = tuple(sorted(edge.edge_id for edge in edges if edge.unresolved))
        fp = stable_fingerprint({
            "findings": sorted(item.fingerprint for item in ranked),
            "edges": [edge.fingerprint for edge in edges],
            "restart": restart.fingerprint,
        })
        return SemanticHypergraphSnapshot(
            finding_ids=tuple(sorted(item.finding_id for item in ranked)),
            edges=tuple(edges),
            restart=restart,
            unresolved_edge_ids=unresolved,
            fingerprint=fp,
        )