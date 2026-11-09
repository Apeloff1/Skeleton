"""Chronological, provenance-preserving scientific evidence ledger.

The ledger is designed for architecture selection, not bibliography vanity.  It
keeps primary artifacts, claims, assumptions, populations, replications,
contradictions, and supersession explicit.  A recent paper never overwrites an
older result merely because it is recent; historical snapshots remain
reconstructable and architecture promotion can ask what was actually supported
at a given date.

No scalar "truth score" is exposed.  Scientific evidence is partially ordered:
formal guarantees, interventional evidence, replicated empirical evidence,
observations, simulations, and expert claims answer different questions and
must not be collapsed into a fake universal number.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Sequence, Set, Tuple


class ArtifactKind(str, Enum):
    PAPER = "paper"
    BOOK = "book"
    STANDARD = "standard"
    FORMALIZATION = "formalization"
    DATASET = "dataset"
    BENCHMARK = "benchmark"
    SOURCE_CODE = "source_code"
    SPECIFICATION = "specification"
    TECHNICAL_REPORT = "technical_report"
    OTHER = "other"


class EvidenceKind(str, Enum):
    MACHINE_CHECKED_PROOF = "machine_checked_proof"
    MATHEMATICAL_PROOF = "mathematical_proof"
    RANDOMIZED_INTERVENTION = "randomized_intervention"
    QUASI_EXPERIMENT = "quasi_experiment"
    CONTROLLED_BENCHMARK = "controlled_benchmark"
    REPLICATION = "replication"
    OBSERVATIONAL = "observational"
    ABLATION = "ablation"
    SIMULATION = "simulation"
    CASE_STUDY = "case_study"
    EXPERT_ARGUMENT = "expert_argument"
    HYPOTHESIS = "hypothesis"


class ClaimRelation(str, Enum):
    SUPPORTS = "supports"
    REPLICATES = "replicates"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    SUPERSEDES = "supersedes"
    GENERALIZES = "generalizes"
    LIMITS = "limits"


class ClaimStatus(str, Enum):
    ACTIVE = "active"
    CONTESTED = "contested"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


@dataclass(frozen=True)
class ResearchArtifact:
    artifact_id: str
    title: str
    published: date
    kind: ArtifactKind
    citation: str
    content_digest: str
    authors: Tuple[str, ...] = ()
    version: str = ""
    primary_source: bool = True
    peer_reviewed: Optional[bool] = None
    persistent_id: str = ""
    source_uri: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_id or not self.title or not self.citation:
            raise ValueError("artifact id, title, and citation are required")
        if not self.content_digest:
            raise ValueError("content_digest is required")
        for key, value in self.metadata.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("artifact metadata must be string-to-string")

    @property
    def year(self) -> int:
        return self.published.year

    def as_json(self) -> Mapping[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "title": self.title,
            "published": self.published.isoformat(),
            "kind": self.kind.value,
            "citation": self.citation,
            "content_digest": self.content_digest,
            "authors": list(self.authors),
            "version": self.version,
            "primary_source": self.primary_source,
            "peer_reviewed": self.peer_reviewed,
            "persistent_id": self.persistent_id,
            "source_uri": self.source_uri,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class ScientificClaim:
    claim_id: str
    proposition: str
    domain: str
    artifact_id: str
    evidence_kind: EvidenceKind
    observed_on: date
    assumptions: Tuple[str, ...] = ()
    population: str = ""
    environment: str = ""
    metrics: Mapping[str, float] = field(default_factory=dict)
    uncertainty: Mapping[str, float] = field(default_factory=dict)
    sample_size: Optional[int] = None
    preregistered: Optional[bool] = None
    code_available: Optional[bool] = None
    data_available: Optional[bool] = None
    direct_evidence: bool = True
    notes: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.claim_id or not self.proposition or not self.domain or not self.artifact_id:
            raise ValueError("claim identity, proposition, domain, and artifact are required")
        if self.sample_size is not None and self.sample_size < 0:
            raise ValueError("sample_size cannot be negative")
        self._validate_finite(self.metrics, "metric")
        self._validate_finite(self.uncertainty, "uncertainty")

    @staticmethod
    def _validate_finite(values: Mapping[str, float], label: str) -> None:
        for key, value in values.items():
            numeric = float(value)
            if numeric != numeric or numeric in (float("inf"), float("-inf")):
                raise ValueError("%s %s must be finite" % (label, key))

    @property
    def is_simulation(self) -> bool:
        return self.evidence_kind == EvidenceKind.SIMULATION

    def as_json(self) -> Mapping[str, object]:
        return {
            "claim_id": self.claim_id,
            "proposition": self.proposition,
            "domain": self.domain,
            "artifact_id": self.artifact_id,
            "evidence_kind": self.evidence_kind.value,
            "observed_on": self.observed_on.isoformat(),
            "assumptions": list(self.assumptions),
            "population": self.population,
            "environment": self.environment,
            "metrics": dict(sorted((key, float(value)) for key, value in self.metrics.items())),
            "uncertainty": dict(sorted((key, float(value)) for key, value in self.uncertainty.items())),
            "sample_size": self.sample_size,
            "preregistered": self.preregistered,
            "code_available": self.code_available,
            "data_available": self.data_available,
            "direct_evidence": self.direct_evidence,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ClaimEdge:
    source_claim_id: str
    target_claim_id: str
    relation: ClaimRelation
    artifact_id: str
    rationale: str
    created_on: date

    def __post_init__(self) -> None:
        if not all((self.source_claim_id, self.target_claim_id, self.artifact_id, self.rationale)):
            raise ValueError("claim relation fields must be non-empty")
        if self.source_claim_id == self.target_claim_id:
            raise ValueError("claim relation cannot self-reference")


@dataclass(frozen=True)
class EvidenceProfile:
    claim_id: str
    status: ClaimStatus
    direct_sources: int
    primary_sources: int
    independent_support: int
    replications: int
    contradictions: int
    formal_support: int
    interventional_support: int
    benchmark_support: int
    observational_support: int
    simulation_support: int
    latest_evidence_date: date
    assumptions: Tuple[str, ...]
    environments: Tuple[str, ...]
    populations: Tuple[str, ...]

    @property
    def empirical_support(self) -> int:
        return self.interventional_support + self.benchmark_support + self.observational_support


@dataclass(frozen=True)
class FrontierEntry:
    claim: ScientificClaim
    profile: EvidenceProfile
    dominated_by: Tuple[str, ...] = ()

    @property
    def undominated(self) -> bool:
        return not self.dominated_by


class ScientificEvidenceLedger:
    """Append-only, date-sliceable scientific evidence graph."""

    _FORMAL = frozenset({EvidenceKind.MACHINE_CHECKED_PROOF, EvidenceKind.MATHEMATICAL_PROOF})
    _INTERVENTIONAL = frozenset({EvidenceKind.RANDOMIZED_INTERVENTION, EvidenceKind.QUASI_EXPERIMENT})
    _BENCHMARK = frozenset({EvidenceKind.CONTROLLED_BENCHMARK, EvidenceKind.ABLATION, EvidenceKind.REPLICATION})
    _OBSERVATIONAL = frozenset({EvidenceKind.OBSERVATIONAL, EvidenceKind.CASE_STUDY})

    def __init__(self) -> None:
        self._artifacts: Dict[str, ResearchArtifact] = {}
        self._digest_owner: Dict[str, str] = {}
        self._claims: Dict[str, ScientificClaim] = {}
        self._edges: list[ClaimEdge] = []
        self._retracted_artifacts: Set[str] = set()

    def add_artifact(self, artifact: ResearchArtifact) -> None:
        previous = self._artifacts.get(artifact.artifact_id)
        if previous is not None:
            if previous != artifact:
                raise ValueError("artifact id already registered with different content")
            return
        duplicate = self._digest_owner.get(artifact.content_digest)
        if duplicate is not None and duplicate != artifact.artifact_id:
            raise ValueError("duplicate artifact content already registered as %s" % duplicate)
        self._artifacts[artifact.artifact_id] = artifact
        self._digest_owner[artifact.content_digest] = artifact.artifact_id

    def add_claim(self, claim: ScientificClaim) -> None:
        if claim.artifact_id not in self._artifacts:
            raise ValueError("claim references unknown artifact")
        artifact = self._artifacts[claim.artifact_id]
        if claim.observed_on < artifact.published:
            raise ValueError("claim observation cannot predate its source artifact publication")
        previous = self._claims.get(claim.claim_id)
        if previous is not None and previous != claim:
            raise ValueError("claim id already registered with different content")
        self._claims[claim.claim_id] = claim

    def relate(self, edge: ClaimEdge) -> None:
        if edge.source_claim_id not in self._claims or edge.target_claim_id not in self._claims:
            raise ValueError("claim relation references unknown claim")
        if edge.artifact_id not in self._artifacts:
            raise ValueError("claim relation references unknown artifact")
        if edge.created_on < self._artifacts[edge.artifact_id].published:
            raise ValueError("relation cannot predate its source artifact")
        if edge not in self._edges:
            self._edges.append(edge)

    def retract_artifact(self, artifact_id: str) -> None:
        if artifact_id not in self._artifacts:
            raise KeyError(artifact_id)
        self._retracted_artifacts.add(artifact_id)

    def artifact(self, artifact_id: str) -> ResearchArtifact:
        return self._artifacts[artifact_id]

    def claim(self, claim_id: str) -> ScientificClaim:
        return self._claims[claim_id]

    def snapshot(self, *, through: date) -> "EvidenceSnapshot":
        artifacts = {
            artifact_id: artifact
            for artifact_id, artifact in self._artifacts.items()
            if artifact.published <= through
        }
        claims = {
            claim_id: claim
            for claim_id, claim in self._claims.items()
            if claim.observed_on <= through and claim.artifact_id in artifacts
        }
        edges = tuple(
            edge
            for edge in self._edges
            if edge.created_on <= through
            and edge.source_claim_id in claims
            and edge.target_claim_id in claims
            and edge.artifact_id in artifacts
        )
        retracted = frozenset(item for item in self._retracted_artifacts if item in artifacts)
        return EvidenceSnapshot(through, artifacts, claims, edges, retracted)

    @property
    def fingerprint(self) -> str:
        payload = {
            "artifacts": [self._artifacts[key].as_json() for key in sorted(self._artifacts)],
            "claims": [self._claims[key].as_json() for key in sorted(self._claims)],
            "edges": [
                {
                    "source": edge.source_claim_id,
                    "target": edge.target_claim_id,
                    "relation": edge.relation.value,
                    "artifact": edge.artifact_id,
                    "rationale": edge.rationale,
                    "created_on": edge.created_on.isoformat(),
                }
                for edge in sorted(
                    self._edges,
                    key=lambda item: (
                        item.created_on,
                        item.source_claim_id,
                        item.target_claim_id,
                        item.relation.value,
                    ),
                )
            ],
            "retracted": sorted(self._retracted_artifacts),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class EvidenceSnapshot:
    """Immutable historical view over evidence available by one date."""

    def __init__(
        self,
        through: date,
        artifacts: Mapping[str, ResearchArtifact],
        claims: Mapping[str, ScientificClaim],
        edges: Sequence[ClaimEdge],
        retracted_artifacts: frozenset[str],
    ) -> None:
        self.through = through
        self.artifacts = dict(artifacts)
        self.claims = dict(claims)
        self.edges = tuple(edges)
        self.retracted_artifacts = retracted_artifacts

    def status(self, claim_id: str) -> ClaimStatus:
        claim = self.claims[claim_id]
        if claim.artifact_id in self.retracted_artifacts:
            return ClaimStatus.RETRACTED
        superseded = any(
            edge.target_claim_id == claim_id
            and edge.relation == ClaimRelation.SUPERSEDES
            and self.claims[edge.source_claim_id].artifact_id not in self.retracted_artifacts
            for edge in self.edges
        )
        if superseded:
            return ClaimStatus.SUPERSEDED
        contradicted = any(
            edge.target_claim_id == claim_id
            and edge.relation == ClaimRelation.CONTRADICTS
            and self.claims[edge.source_claim_id].artifact_id not in self.retracted_artifacts
            for edge in self.edges
        )
        if contradicted:
            return ClaimStatus.CONTESTED
        return ClaimStatus.ACTIVE

    def profile(self, claim_id: str) -> EvidenceProfile:
        root = self.claims[claim_id]
        related_ids = {claim_id}
        for edge in self.edges:
            if edge.target_claim_id == claim_id and edge.relation in {
                ClaimRelation.SUPPORTS,
                ClaimRelation.REPLICATES,
                ClaimRelation.REFINES,
                ClaimRelation.GENERALIZES,
                ClaimRelation.LIMITS,
                ClaimRelation.CONTRADICTS,
            }:
                related_ids.add(edge.source_claim_id)
        related = [
            self.claims[item]
            for item in sorted(related_ids)
            if self.claims[item].artifact_id not in self.retracted_artifacts
        ]
        direct = [item for item in related if item.direct_evidence]
        artifact_ids = {item.artifact_id for item in direct}
        support_edges = [
            edge
            for edge in self.edges
            if edge.target_claim_id == claim_id
            and edge.relation in {ClaimRelation.SUPPORTS, ClaimRelation.REPLICATES}
            and self.claims[edge.source_claim_id].artifact_id not in self.retracted_artifacts
        ]
        contradiction_edges = [
            edge
            for edge in self.edges
            if edge.target_claim_id == claim_id
            and edge.relation == ClaimRelation.CONTRADICTS
            and self.claims[edge.source_claim_id].artifact_id not in self.retracted_artifacts
        ]
        assumptions = sorted({assumption for item in related for assumption in item.assumptions})
        environments = sorted({item.environment for item in related if item.environment})
        populations = sorted({item.population for item in related if item.population})
        latest = max((item.observed_on for item in related), default=root.observed_on)
        return EvidenceProfile(
            claim_id=claim_id,
            status=self.status(claim_id),
            direct_sources=len(artifact_ids),
            primary_sources=sum(1 for item in artifact_ids if self.artifacts[item].primary_source),
            independent_support=len({self.claims[edge.source_claim_id].artifact_id for edge in support_edges}),
            replications=sum(1 for edge in support_edges if edge.relation == ClaimRelation.REPLICATES),
            contradictions=len({self.claims[edge.source_claim_id].artifact_id for edge in contradiction_edges}),
            formal_support=sum(1 for item in direct if item.evidence_kind in ScientificEvidenceLedger._FORMAL),
            interventional_support=sum(1 for item in direct if item.evidence_kind in ScientificEvidenceLedger._INTERVENTIONAL),
            benchmark_support=sum(1 for item in direct if item.evidence_kind in ScientificEvidenceLedger._BENCHMARK),
            observational_support=sum(1 for item in direct if item.evidence_kind in ScientificEvidenceLedger._OBSERVATIONAL),
            simulation_support=sum(1 for item in direct if item.evidence_kind == EvidenceKind.SIMULATION),
            latest_evidence_date=latest,
            assumptions=tuple(assumptions),
            environments=tuple(environments),
            populations=tuple(populations),
        )

    def frontier(
        self,
        *,
        domain: str,
        required_environment: Optional[str] = None,
        include_contested: bool = True,
    ) -> Tuple[FrontierEntry, ...]:
        candidates = []
        for claim in self.claims.values():
            if claim.domain != domain:
                continue
            profile = self.profile(claim.claim_id)
            if profile.status in {ClaimStatus.RETRACTED, ClaimStatus.SUPERSEDED}:
                continue
            if not include_contested and profile.status == ClaimStatus.CONTESTED:
                continue
            if required_environment and claim.environment and claim.environment != required_environment:
                continue
            candidates.append((claim, profile))

        entries = []
        for claim, profile in sorted(candidates, key=lambda pair: (pair[0].observed_on, pair[0].claim_id)):
            dominators = []
            for other_claim, other_profile in candidates:
                if other_claim.claim_id == claim.claim_id:
                    continue
                if self._dominates(other_profile, profile):
                    dominators.append(other_claim.claim_id)
            entries.append(FrontierEntry(claim, profile, tuple(sorted(dominators))))
        return tuple(entries)

    def undominated_frontier(self, *, domain: str) -> Tuple[FrontierEntry, ...]:
        return tuple(item for item in self.frontier(domain=domain) if item.undominated)

    @staticmethod
    def _dominates(left: EvidenceProfile, right: EvidenceProfile) -> bool:
        """Pareto dominance over evidence dimensions, never publication date."""

        left_vector = (
            left.formal_support,
            left.interventional_support,
            left.benchmark_support,
            left.observational_support,
            left.independent_support,
            left.replications,
            -left.contradictions,
        )
        right_vector = (
            right.formal_support,
            right.interventional_support,
            right.benchmark_support,
            right.observational_support,
            right.independent_support,
            right.replications,
            -right.contradictions,
        )
        at_least = all(a >= b for a, b in zip(left_vector, right_vector))
        strictly = any(a > b for a, b in zip(left_vector, right_vector))
        return at_least and strictly

    def simulation_only(self, claim_id: str) -> bool:
        profile = self.profile(claim_id)
        substantive = (
            profile.formal_support
            + profile.interventional_support
            + profile.benchmark_support
            + profile.observational_support
        )
        return profile.simulation_support > 0 and substantive == 0
