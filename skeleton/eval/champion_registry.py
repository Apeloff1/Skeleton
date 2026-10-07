"""P1 immutable candidate and champion/challenger registry.

The registry is evaluation-only. Candidate artifacts cannot replace an incumbent
by mutation. Every champion transition is append-only and must be created from
accepted LEARN-02 benchmark qualification plus a comparative improvement claim
whose baseline is the current champion and whose evaluated candidate is the
registered challenger.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import CanonicalContractError, EvidenceRef, canonical_json_bytes
from skeleton.contracts.reproducibility import ReproducibilityBundle
from skeleton.eval.benchmark_registry import (
    BenchmarkManifest,
    BenchmarkQualificationDecision,
    BenchmarkScoreObservation,
    ImprovementClaimDecision,
)
from skeleton.eval.experiment_registry import ExperimentManifest


CHAMPION_REGISTRY_SCHEMA_VERSION = 1
CHAMPION_REGISTRY_TASK_ID = "P1-LEARN-03"
CHAMPION_REGISTRY_ACCOUNTABILITY_ID = "ACC-P1-LEARN-03"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_CANDIDATES = 512
_MAX_TRANSITIONS = 2048


class ChampionRegistryError(ValueError):
    """Candidate or promotion state violates immutable registry policy."""


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise ChampionRegistryError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChampionRegistryError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise ChampionRegistryError(f"{field} must be normalized")
    return normalized


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ChampionRegistryError(f"{field} must be lowercase sha256")
    return value


def _sha40(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA40_RE.fullmatch(value):
        raise ChampionRegistryError(f"{field} must be lowercase git sha")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ChampionRegistryError(f"{field} must be a positive integer")
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = canonical_json_bytes(value)
    except CanonicalContractError as exc:
        raise ChampionRegistryError(
            "champion registry payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ChampionRegistryError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not result and not allow_empty:
        raise ChampionRegistryError(f"{field} must be non-empty")
    return result


@dataclass(frozen=True, slots=True)
class CandidateArtifact:
    candidate_id: str
    version: str
    candidate_ref: str
    artifact_digest: str
    source_commit: str
    experiment_manifest_digest: str
    benchmark_manifest_digest: str
    benchmark_qualification_digest: str
    reproducibility_bundle_digest: str
    parent_candidate_digest: str | None = None
    tags: tuple[str, ...] = ()
    schema_version: int = CHAMPION_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in ("candidate_id", "version", "candidate_ref"):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "artifact_digest",
            _sha256(self.artifact_digest, "artifact_digest"),
        )
        object.__setattr__(
            self,
            "source_commit",
            _sha40(self.source_commit, "source_commit"),
        )
        for field in (
            "experiment_manifest_digest",
            "benchmark_manifest_digest",
            "benchmark_qualification_digest",
            "reproducibility_bundle_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.parent_candidate_digest is not None:
            object.__setattr__(
                self,
                "parent_candidate_digest",
                _sha256(
                    self.parent_candidate_digest,
                    "parent_candidate_digest",
                ),
            )
        object.__setattr__(
            self,
            "tags",
            _tokens(self.tags, "tags"),
        )
        if self.schema_version != CHAMPION_REGISTRY_SCHEMA_VERSION:
            raise ChampionRegistryError(
                "unsupported candidate schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "version": self.version,
            "candidate_ref": self.candidate_ref,
            "artifact_digest": self.artifact_digest,
            "source_commit": self.source_commit,
            "experiment_manifest_digest": self.experiment_manifest_digest,
            "benchmark_manifest_digest": self.benchmark_manifest_digest,
            "benchmark_qualification_digest": self.benchmark_qualification_digest,
            "reproducibility_bundle_digest": self.reproducibility_bundle_digest,
            "parent_candidate_digest": self.parent_candidate_digest,
            "tags": list(self.tags),
            "production_authority": False,
        }

    @property
    def candidate_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class CandidateQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    candidate_digest: str
    experiment_manifest_digest: str
    benchmark_manifest_digest: str
    benchmark_qualification_digest: str
    reproducibility_bundle_digest: str
    task_id: str = CHAMPION_REGISTRY_TASK_ID
    accountability_id: str = CHAMPION_REGISTRY_ACCOUNTABILITY_ID
    schema_version: int = CHAMPION_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ChampionRegistryError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ChampionRegistryError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "candidate_digest",
            "experiment_manifest_digest",
            "benchmark_manifest_digest",
            "benchmark_qualification_digest",
            "reproducibility_bundle_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.task_id != CHAMPION_REGISTRY_TASK_ID:
            raise ChampionRegistryError("task_id drift")
        if self.accountability_id != CHAMPION_REGISTRY_ACCOUNTABILITY_ID:
            raise ChampionRegistryError("accountability_id drift")
        if self.schema_version != CHAMPION_REGISTRY_SCHEMA_VERSION:
            raise ChampionRegistryError(
                "unsupported qualification schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "candidate_digest": self.candidate_digest,
            "experiment_manifest_digest": self.experiment_manifest_digest,
            "benchmark_manifest_digest": self.benchmark_manifest_digest,
            "benchmark_qualification_digest": self.benchmark_qualification_digest,
            "reproducibility_bundle_digest": self.reproducibility_bundle_digest,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise ChampionRegistryError(
                "rejected candidate cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:learn-03:candidate:{self.candidate_digest}",
            digest=self.decision_digest,
            category="candidate_qualification",
        )


def qualify_candidate_artifact(
    *,
    candidate: CandidateArtifact,
    experiment: ExperimentManifest,
    benchmark: BenchmarkManifest,
    benchmark_qualification: BenchmarkQualificationDecision,
    reproducibility: ReproducibilityBundle,
) -> CandidateQualificationDecision:
    if not isinstance(candidate, CandidateArtifact):
        raise TypeError("candidate must be CandidateArtifact")
    if not isinstance(experiment, ExperimentManifest):
        raise TypeError("experiment must be ExperimentManifest")
    if not isinstance(benchmark, BenchmarkManifest):
        raise TypeError("benchmark must be BenchmarkManifest")
    if not isinstance(
        benchmark_qualification,
        BenchmarkQualificationDecision,
    ):
        raise TypeError(
            "benchmark_qualification must be BenchmarkQualificationDecision"
        )
    if not isinstance(reproducibility, ReproducibilityBundle):
        raise TypeError(
            "reproducibility must be ReproducibilityBundle"
        )

    reasons: list[str] = []
    if candidate.candidate_ref != experiment.candidate_ref:
        reasons.append("candidate-ref-mismatch")
    if candidate.source_commit != experiment.source_commit:
        reasons.append("candidate-source-commit-experiment-mismatch")
    if candidate.source_commit != reproducibility.commit_sha:
        reasons.append("candidate-source-commit-reproducibility-mismatch")
    if candidate.experiment_manifest_digest != experiment.manifest_digest:
        reasons.append("experiment-manifest-digest-mismatch")
    if candidate.benchmark_manifest_digest != benchmark.manifest_digest:
        reasons.append("benchmark-manifest-digest-mismatch")
    if (
        candidate.benchmark_qualification_digest
        != benchmark_qualification.decision_digest
    ):
        reasons.append("benchmark-qualification-digest-mismatch")
    if (
        candidate.reproducibility_bundle_digest
        != reproducibility.bundle_digest
    ):
        reasons.append("reproducibility-bundle-digest-mismatch")
    if not benchmark_qualification.accepted:
        reasons.append("benchmark-qualification-rejected")
    if (
        benchmark_qualification.benchmark_manifest_digest
        != benchmark.manifest_digest
    ):
        reasons.append("qualification-benchmark-mismatch")
    if (
        benchmark_qualification.experiment_manifest_digest
        != experiment.manifest_digest
    ):
        reasons.append("qualification-experiment-mismatch")
    if (
        benchmark_qualification.reproducibility_bundle_digest
        != reproducibility.bundle_digest
    ):
        reasons.append("qualification-reproducibility-mismatch")

    normalized = tuple(sorted(set(reasons)))
    return CandidateQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        candidate_digest=candidate.candidate_digest,
        experiment_manifest_digest=experiment.manifest_digest,
        benchmark_manifest_digest=benchmark.manifest_digest,
        benchmark_qualification_digest=benchmark_qualification.decision_digest,
        reproducibility_bundle_digest=reproducibility.bundle_digest,
    )


@dataclass(frozen=True, slots=True)
class PromotionTransition:
    sequence: int
    previous_champion_digest: str
    challenger_digest: str
    candidate_qualification_digest: str
    benchmark_qualification_digest: str
    improvement_claim_digest: str
    baseline_observation_digest: str
    candidate_observation_digest: str
    prior_transition_digest: str | None = None
    schema_version: int = CHAMPION_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence",
            _positive_int(self.sequence, "sequence"),
        )
        for field in (
            "previous_champion_digest",
            "challenger_digest",
            "candidate_qualification_digest",
            "benchmark_qualification_digest",
            "improvement_claim_digest",
            "baseline_observation_digest",
            "candidate_observation_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.previous_champion_digest == self.challenger_digest:
            raise ChampionRegistryError(
                "champion and challenger must differ"
            )
        if self.prior_transition_digest is not None:
            object.__setattr__(
                self,
                "prior_transition_digest",
                _sha256(
                    self.prior_transition_digest,
                    "prior_transition_digest",
                ),
            )
        if self.schema_version != CHAMPION_REGISTRY_SCHEMA_VERSION:
            raise ChampionRegistryError(
                "unsupported transition schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "previous_champion_digest": self.previous_champion_digest,
            "challenger_digest": self.challenger_digest,
            "candidate_qualification_digest": self.candidate_qualification_digest,
            "benchmark_qualification_digest": self.benchmark_qualification_digest,
            "improvement_claim_digest": self.improvement_claim_digest,
            "baseline_observation_digest": self.baseline_observation_digest,
            "candidate_observation_digest": self.candidate_observation_digest,
            "prior_transition_digest": self.prior_transition_digest,
        }

    @property
    def transition_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ChampionRegistry:
    registry_id: str
    candidates: tuple[CandidateArtifact, ...]
    initial_champion_digest: str
    transitions: tuple[PromotionTransition, ...] = ()
    schema_version: int = CHAMPION_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "registry_id",
            _token(self.registry_id, "registry_id"),
        )
        if not isinstance(self.candidates, tuple) or not self.candidates:
            raise ChampionRegistryError(
                "candidates must be a non-empty tuple"
            )
        if any(
            not isinstance(item, CandidateArtifact)
            for item in self.candidates
        ):
            raise ChampionRegistryError(
                "candidates must contain CandidateArtifact"
            )
        if len(self.candidates) > _MAX_CANDIDATES:
            raise ChampionRegistryError("candidate limit exceeded")
        digests = [item.candidate_digest for item in self.candidates]
        if len(digests) != len(set(digests)):
            raise ChampionRegistryError(
                "candidate digests must be unique"
            )
        candidate_keys = [
            (item.candidate_id, item.version)
            for item in self.candidates
        ]
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ChampionRegistryError(
                "candidate id/version keys must be unique"
            )
        refs = [item.candidate_ref for item in self.candidates]
        if len(refs) != len(set(refs)):
            raise ChampionRegistryError(
                "candidate refs must be unique"
            )
        object.__setattr__(
            self,
            "initial_champion_digest",
            _sha256(
                self.initial_champion_digest,
                "initial_champion_digest",
            ),
        )
        by_digest = {
            item.candidate_digest: item for item in self.candidates
        }
        for item in self.candidates:
            parent = item.parent_candidate_digest
            if parent is not None and parent not in by_digest:
                raise ChampionRegistryError(
                    f"{item.candidate_id}: unknown parent candidate digest"
                )
        for start in by_digest:
            seen: set[str] = set()
            current: str | None = start
            while current is not None:
                if current in seen:
                    raise ChampionRegistryError(
                        "candidate lineage contains a cycle"
                    )
                seen.add(current)
                current = by_digest[current].parent_candidate_digest
        if self.initial_champion_digest not in by_digest:
            raise ChampionRegistryError(
                "initial champion is not registered"
            )
        if not isinstance(self.transitions, tuple) or any(
            not isinstance(item, PromotionTransition)
            for item in self.transitions
        ):
            raise ChampionRegistryError(
                "transitions must contain PromotionTransition"
            )
        if len(self.transitions) > _MAX_TRANSITIONS:
            raise ChampionRegistryError("transition limit exceeded")

        champion = self.initial_champion_digest
        previous_transition: str | None = None
        for expected_sequence, transition in enumerate(
            self.transitions,
            start=1,
        ):
            if transition.sequence != expected_sequence:
                raise ChampionRegistryError(
                    "promotion transition sequence must be contiguous"
                )
            if transition.prior_transition_digest != previous_transition:
                raise ChampionRegistryError(
                    "promotion transition chain mismatch"
                )
            if transition.previous_champion_digest != champion:
                raise ChampionRegistryError(
                    "promotion does not start from current champion"
                )
            if transition.challenger_digest not in by_digest:
                raise ChampionRegistryError(
                    "promotion challenger is not registered"
                )
            champion = transition.challenger_digest
            previous_transition = transition.transition_digest

        if self.schema_version != CHAMPION_REGISTRY_SCHEMA_VERSION:
            raise ChampionRegistryError(
                "unsupported registry schema version"
            )

    @property
    def current_champion_digest(self) -> str:
        if self.transitions:
            return self.transitions[-1].challenger_digest
        return self.initial_champion_digest

    @property
    def current_champion(self) -> CandidateArtifact:
        for item in self.candidates:
            if item.candidate_digest == self.current_champion_digest:
                return item
        raise ChampionRegistryError(
            "current champion is not registered"
        )

    @property
    def registry_digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": self.schema_version,
                "task_id": CHAMPION_REGISTRY_TASK_ID,
                "accountability_id": CHAMPION_REGISTRY_ACCOUNTABILITY_ID,
                "registry_id": self.registry_id,
                "candidates": [
                    item.payload()
                    for item in sorted(
                        self.candidates,
                        key=lambda row: row.candidate_digest,
                    )
                ],
                "initial_champion_digest": self.initial_champion_digest,
                "transitions": [
                    item.payload() for item in self.transitions
                ],
                "current_champion_digest": self.current_champion_digest,
                "production_authority": False,
            }
        )

    def with_candidate(
        self,
        candidate: CandidateArtifact,
    ) -> "ChampionRegistry":
        if not isinstance(candidate, CandidateArtifact):
            raise TypeError("candidate must be CandidateArtifact")
        return replace(
            self,
            candidates=(*self.candidates, candidate),
        )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    accepted: bool
    reasons: tuple[str, ...]
    registry_digest: str
    current_champion_digest: str
    challenger_digest: str
    candidate_qualification_digest: str
    benchmark_qualification_digest: str
    improvement_claim_digest: str
    transition: PromotionTransition | None
    task_id: str = CHAMPION_REGISTRY_TASK_ID
    accountability_id: str = CHAMPION_REGISTRY_ACCOUNTABILITY_ID
    schema_version: int = CHAMPION_REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ChampionRegistryError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ChampionRegistryError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "registry_digest",
            "current_champion_digest",
            "challenger_digest",
            "candidate_qualification_digest",
            "benchmark_qualification_digest",
            "improvement_claim_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.transition is not None and not isinstance(
            self.transition,
            PromotionTransition,
        ):
            raise ChampionRegistryError(
                "transition must be PromotionTransition"
            )
        if self.accepted != (self.transition is not None and not self.reasons):
            raise ChampionRegistryError(
                "accepted promotion must be derived from reasons and transition"
            )
        if self.task_id != CHAMPION_REGISTRY_TASK_ID:
            raise ChampionRegistryError("task_id drift")
        if self.accountability_id != CHAMPION_REGISTRY_ACCOUNTABILITY_ID:
            raise ChampionRegistryError("accountability_id drift")
        if self.schema_version != CHAMPION_REGISTRY_SCHEMA_VERSION:
            raise ChampionRegistryError(
                "unsupported decision schema version"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "registry_digest": self.registry_digest,
            "current_champion_digest": self.current_champion_digest,
            "challenger_digest": self.challenger_digest,
            "candidate_qualification_digest": self.candidate_qualification_digest,
            "benchmark_qualification_digest": self.benchmark_qualification_digest,
            "improvement_claim_digest": self.improvement_claim_digest,
            "transition": (
                None if self.transition is None else self.transition.payload()
            ),
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise ChampionRegistryError(
                "rejected promotion cannot become promotion evidence"
            )
        return EvidenceRef(
            source=(
                f"p1:learn-03:promotion:"
                f"{self.current_champion_digest}:"
                f"{self.challenger_digest}"
            ),
            digest=self.decision_digest,
            category="champion_challenger_promotion",
        )


def evaluate_promotion(
    *,
    registry: ChampionRegistry,
    challenger: CandidateArtifact,
    candidate_qualification: CandidateQualificationDecision,
    benchmark_qualification: BenchmarkQualificationDecision,
    improvement_claim: ImprovementClaimDecision,
    baseline_observation: BenchmarkScoreObservation,
    candidate_observation: BenchmarkScoreObservation,
) -> PromotionDecision:
    if not isinstance(registry, ChampionRegistry):
        raise TypeError("registry must be ChampionRegistry")
    if not isinstance(challenger, CandidateArtifact):
        raise TypeError("challenger must be CandidateArtifact")
    if not isinstance(
        candidate_qualification,
        CandidateQualificationDecision,
    ):
        raise TypeError(
            "candidate_qualification must be CandidateQualificationDecision"
        )
    if not isinstance(
        benchmark_qualification,
        BenchmarkQualificationDecision,
    ):
        raise TypeError(
            "benchmark_qualification must be BenchmarkQualificationDecision"
        )
    if not isinstance(improvement_claim, ImprovementClaimDecision):
        raise TypeError(
            "improvement_claim must be ImprovementClaimDecision"
        )
    if not isinstance(baseline_observation, BenchmarkScoreObservation):
        raise TypeError(
            "baseline_observation must be BenchmarkScoreObservation"
        )
    if not isinstance(candidate_observation, BenchmarkScoreObservation):
        raise TypeError(
            "candidate_observation must be BenchmarkScoreObservation"
        )

    current = registry.current_champion
    reasons: list[str] = []
    registered = {
        item.candidate_digest: item for item in registry.candidates
    }
    if challenger.candidate_digest not in registered:
        reasons.append("challenger-not-registered")
    if challenger.candidate_digest == current.candidate_digest:
        reasons.append("challenger-is-current-champion")
    if not candidate_qualification.accepted:
        reasons.append("candidate-qualification-rejected")
    if (
        candidate_qualification.candidate_digest
        != challenger.candidate_digest
    ):
        reasons.append("candidate-qualification-digest-mismatch")
    if not benchmark_qualification.accepted:
        reasons.append("benchmark-qualification-rejected")
    if (
        candidate_qualification.benchmark_qualification_digest
        != benchmark_qualification.decision_digest
    ):
        reasons.append("candidate-benchmark-qualification-mismatch")
    if not improvement_claim.accepted:
        reasons.append("improvement-claim-rejected")
    if (
        improvement_claim.benchmark_qualification_digest
        != benchmark_qualification.decision_digest
    ):
        reasons.append("claim-benchmark-qualification-mismatch")
    if (
        improvement_claim.baseline_observation_digest
        != baseline_observation.digest
    ):
        reasons.append("baseline-observation-digest-mismatch")
    if (
        improvement_claim.candidate_observation_digest
        != candidate_observation.digest
    ):
        reasons.append("candidate-observation-digest-mismatch")
    if baseline_observation.candidate_ref != current.candidate_ref:
        reasons.append("baseline-is-not-current-champion")
    if candidate_observation.candidate_ref != challenger.candidate_ref:
        reasons.append("observation-is-not-challenger")
    if (
        baseline_observation.benchmark_manifest_digest
        != candidate_observation.benchmark_manifest_digest
    ):
        reasons.append("comparison-benchmark-mismatch")
    if (
        candidate_observation.benchmark_manifest_digest
        != challenger.benchmark_manifest_digest
    ):
        reasons.append("challenger-benchmark-mismatch")

    normalized = tuple(sorted(set(reasons)))
    transition: PromotionTransition | None = None
    if not normalized:
        transition = PromotionTransition(
            sequence=len(registry.transitions) + 1,
            previous_champion_digest=current.candidate_digest,
            challenger_digest=challenger.candidate_digest,
            candidate_qualification_digest=(
                candidate_qualification.decision_digest
            ),
            benchmark_qualification_digest=(
                benchmark_qualification.decision_digest
            ),
            improvement_claim_digest=improvement_claim.decision_digest,
            baseline_observation_digest=baseline_observation.digest,
            candidate_observation_digest=candidate_observation.digest,
            prior_transition_digest=(
                None
                if not registry.transitions
                else registry.transitions[-1].transition_digest
            ),
        )

    return PromotionDecision(
        accepted=not normalized,
        reasons=normalized,
        registry_digest=registry.registry_digest,
        current_champion_digest=current.candidate_digest,
        challenger_digest=challenger.candidate_digest,
        candidate_qualification_digest=(
            candidate_qualification.decision_digest
        ),
        benchmark_qualification_digest=(
            benchmark_qualification.decision_digest
        ),
        improvement_claim_digest=improvement_claim.decision_digest,
        transition=transition,
    )


def apply_promotion(
    registry: ChampionRegistry,
    decision: PromotionDecision,
) -> ChampionRegistry:
    if not isinstance(registry, ChampionRegistry):
        raise TypeError("registry must be ChampionRegistry")
    if not isinstance(decision, PromotionDecision):
        raise TypeError("decision must be PromotionDecision")
    if not decision.accepted or decision.transition is None:
        raise ChampionRegistryError(
            "only accepted promotion decisions can advance champion"
        )
    if decision.registry_digest != registry.registry_digest:
        raise ChampionRegistryError(
            "promotion decision was evaluated against another registry"
        )
    if decision.current_champion_digest != registry.current_champion_digest:
        raise ChampionRegistryError(
            "promotion decision champion is stale"
        )
    transition = decision.transition
    if transition.sequence != len(registry.transitions) + 1:
        raise ChampionRegistryError(
            "promotion transition sequence is stale"
        )
    return replace(
        registry,
        transitions=(*registry.transitions, transition),
    )


__all__ = [
    "CHAMPION_REGISTRY_ACCOUNTABILITY_ID",
    "CHAMPION_REGISTRY_SCHEMA_VERSION",
    "CHAMPION_REGISTRY_TASK_ID",
    "CandidateArtifact",
    "CandidateQualificationDecision",
    "ChampionRegistry",
    "ChampionRegistryError",
    "PromotionDecision",
    "PromotionTransition",
    "apply_promotion",
    "evaluate_promotion",
    "qualify_candidate_artifact",
]
