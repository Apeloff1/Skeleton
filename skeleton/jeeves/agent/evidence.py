"""Evidence ledger and grounding gate for the Jeeves agent runtime.

Tool/retrieval outputs enter an append-only content-addressed ledger before the
model may rely on them.  Claims point at immutable evidence references, and the
grounding gate rejects unsupported, stale, contradictory, or low-confidence
claims.  A narrow bridge can project verified evidence into PR #1038's
``LearningEvidenceStore`` without giving live model output write authority.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from .types import (
    AgentContractError,
    Claim,
    EvidenceKind,
    EvidenceRef,
    ToolObservation,
    bounded_text,
    finite_number,
    json_safe,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


class EvidenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    evidence_id: str
    kind: EvidenceKind
    source: str
    payload: Any
    observed_at: float
    confidence: float = 1.0
    uri: str | None = None
    parent_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", require_id("evidence_id", self.evidence_id))
        if not isinstance(self.kind, EvidenceKind):
            object.__setattr__(self, "kind", EvidenceKind(str(self.kind)))
        object.__setattr__(self, "source", bounded_text("source", self.source, maximum=1024))
        object.__setattr__(self, "payload", json_safe(self.payload))
        observed = finite_number("observed_at", self.observed_at)
        if observed < 0:
            raise AgentContractError("observed_at must be non-negative")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "confidence", probability("confidence", self.confidence))
        if self.uri is not None:
            object.__setattr__(self, "uri", bounded_text("uri", self.uri, maximum=4096))
        parents = tuple(require_id("parent_id", parent) for parent in self.parent_ids)
        if self.evidence_id in parents or len(set(parents)) != len(parents):
            raise AgentContractError("invalid evidence parents")
        object.__setattr__(self, "parent_ids", parents)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.payload)

    @property
    def ref(self) -> EvidenceRef:
        return EvidenceRef(
            evidence_id=self.evidence_id,
            kind=self.kind,
            source=self.source,
            fingerprint=self.fingerprint,
            confidence=self.confidence,
            observed_at=self.observed_at,
            uri=self.uri,
        )


@dataclass(frozen=True, slots=True)
class Contradiction:
    contradiction_id: str
    left_id: str
    right_id: str
    reason: str
    detected_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "contradiction_id", require_id("contradiction_id", self.contradiction_id))
        object.__setattr__(self, "left_id", require_id("left_id", self.left_id))
        object.__setattr__(self, "right_id", require_id("right_id", self.right_id))
        if self.left_id == self.right_id:
            raise AgentContractError("contradiction requires two different evidence ids")
        object.__setattr__(self, "reason", bounded_text("contradiction reason", self.reason, maximum=4096))
        detected = finite_number("detected_at", self.detected_at)
        if detected < 0:
            raise AgentContractError("detected_at must be non-negative")
        object.__setattr__(self, "detected_at", detected)


class EvidenceLedger:
    """Append-only content-addressed evidence store with lineage."""

    def __init__(self, *, max_artifacts: int = 100_000, clock: Callable[[], float] = time.time) -> None:
        if isinstance(max_artifacts, bool) or not isinstance(max_artifacts, int) or max_artifacts < 1:
            raise ValueError("max_artifacts must be positive")
        self.max_artifacts = max_artifacts
        self._clock = clock
        self._artifacts: dict[str, EvidenceArtifact] = {}
        self._fingerprints: dict[str, str] = {}
        self._contradictions: dict[str, Contradiction] = {}
        self._lock = threading.RLock()

    def append(self, artifact: EvidenceArtifact) -> EvidenceArtifact:
        if not isinstance(artifact, EvidenceArtifact):
            raise TypeError("artifact must be EvidenceArtifact")
        with self._lock:
            prior = self._artifacts.get(artifact.evidence_id)
            if prior is not None:
                if prior.fingerprint != artifact.fingerprint:
                    raise EvidenceError("evidence id collision with different content")
                return prior
            if len(self._artifacts) >= self.max_artifacts:
                raise EvidenceError("evidence ledger capacity exhausted")
            missing = [parent for parent in artifact.parent_ids if parent not in self._artifacts]
            if missing:
                raise EvidenceError(f"evidence parents are missing: {missing}")
            duplicate_id = self._fingerprints.get(artifact.fingerprint)
            if duplicate_id is not None:
                return self._artifacts[duplicate_id]
            self._artifacts[artifact.evidence_id] = artifact
            self._fingerprints[artifact.fingerprint] = artifact.evidence_id
            return artifact

    def ingest_observation(self, observation: ToolObservation, *, source_prefix: str = "tool") -> tuple[EvidenceArtifact, ...]:
        if not observation.ok:
            return ()
        artifacts: list[EvidenceArtifact] = []
        for ref in observation.evidence:
            artifact = EvidenceArtifact(
                evidence_id=ref.evidence_id,
                kind=ref.kind,
                source=ref.source,
                payload={
                    "tool": observation.tool_name,
                    "call_id": observation.call_id,
                    "payload": observation.payload,
                    "declared_fingerprint": ref.fingerprint,
                },
                observed_at=ref.observed_at,
                confidence=ref.confidence,
                uri=ref.uri,
                metadata={"cached": observation.cached, "latency_ms": observation.latency_ms},
            )
            # Tool executors fingerprint their payload directly.  Preserve the
            # actual payload hash as the authoritative evidence fingerprint.
            if stable_fingerprint(observation.payload) != ref.fingerprint:
                raise EvidenceError("tool evidence fingerprint does not match observation payload")
            artifact = EvidenceArtifact(
                evidence_id=ref.evidence_id,
                kind=ref.kind,
                source=ref.source,
                payload=observation.payload,
                observed_at=ref.observed_at,
                confidence=ref.confidence,
                uri=ref.uri,
                metadata={"tool": observation.tool_name, "call_id": observation.call_id, "cached": observation.cached},
            )
            artifacts.append(self.append(artifact))
        if not artifacts and observation.payload is not None:
            artifacts.append(
                self.append(
                    evidence_from_payload(
                        observation.payload,
                        kind=EvidenceKind.TOOL,
                        source=f"{source_prefix}:{observation.tool_name}",
                        observed_at=self._clock(),
                        confidence=1.0,
                        metadata={"call_id": observation.call_id},
                    )
                )
            )
        return tuple(artifacts)

    def get(self, evidence_id: str) -> EvidenceArtifact | None:
        with self._lock:
            return self._artifacts.get(require_id("evidence_id", evidence_id))

    def require(self, evidence_id: str) -> EvidenceArtifact:
        artifact = self.get(evidence_id)
        if artifact is None:
            raise EvidenceError(f"unknown evidence: {evidence_id}")
        return artifact

    def refs(self, evidence_ids: Iterable[str]) -> tuple[EvidenceRef, ...]:
        return tuple(self.require(evidence_id).ref for evidence_id in evidence_ids)

    def lineage(self, evidence_id: str) -> tuple[EvidenceArtifact, ...]:
        ordered: list[EvidenceArtifact] = []
        visiting: set[str] = set()

        def walk(current: str) -> None:
            if current in visiting:
                raise EvidenceError("evidence lineage contains a cycle")
            if any(item.evidence_id == current for item in ordered):
                return
            visiting.add(current)
            artifact = self.require(current)
            for parent in artifact.parent_ids:
                walk(parent)
            visiting.remove(current)
            ordered.append(artifact)

        walk(require_id("evidence_id", evidence_id))
        return tuple(ordered)

    def mark_contradiction(self, left_id: str, right_id: str, reason: str) -> Contradiction:
        left_id = require_id("left_id", left_id)
        right_id = require_id("right_id", right_id)
        self.require(left_id)
        self.require(right_id)
        ordered = sorted((left_id, right_id))
        contradiction = Contradiction(
            contradiction_id=stable_id("contradiction", {"left": ordered[0], "right": ordered[1], "reason": reason}),
            left_id=ordered[0],
            right_id=ordered[1],
            reason=reason,
            detected_at=self._clock(),
        )
        with self._lock:
            self._contradictions[contradiction.contradiction_id] = contradiction
        return contradiction

    def contradictions_for(self, evidence_ids: Iterable[str]) -> tuple[Contradiction, ...]:
        ids = set(evidence_ids)
        with self._lock:
            values = [item for item in self._contradictions.values() if item.left_id in ids and item.right_id in ids]
        return tuple(sorted(values, key=lambda item: item.contradiction_id))

    def artifacts(self) -> tuple[EvidenceArtifact, ...]:
        with self._lock:
            return tuple(sorted(self._artifacts.values(), key=lambda item: item.evidence_id))

    @property
    def fingerprint(self) -> str:
        with self._lock:
            return stable_fingerprint(
                {
                    "artifacts": [(item.evidence_id, item.fingerprint) for item in sorted(self._artifacts.values(), key=lambda item: item.evidence_id)],
                    "contradictions": [
                        (item.contradiction_id, item.left_id, item.right_id)
                        for item in sorted(self._contradictions.values(), key=lambda item: item.contradiction_id)
                    ],
                }
            )


@dataclass(frozen=True, slots=True)
class GroundingPolicy:
    minimum_claim_confidence: float = 0.55
    minimum_evidence_confidence: float = 0.5
    maximum_evidence_age_seconds: float | None = None
    require_evidence_for_derived: bool = True
    reject_contradictions: bool = True
    maximum_claims: int = 128

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum_claim_confidence", probability("minimum_claim_confidence", self.minimum_claim_confidence))
        object.__setattr__(self, "minimum_evidence_confidence", probability("minimum_evidence_confidence", self.minimum_evidence_confidence))
        if self.maximum_evidence_age_seconds is not None:
            age = finite_number("maximum_evidence_age_seconds", self.maximum_evidence_age_seconds)
            if age <= 0:
                raise AgentContractError("maximum evidence age must be positive")
            object.__setattr__(self, "maximum_evidence_age_seconds", age)
        if isinstance(self.maximum_claims, bool) or not isinstance(self.maximum_claims, int) or self.maximum_claims < 1:
            raise AgentContractError("maximum_claims must be positive")


@dataclass(frozen=True, slots=True)
class GroundingReport:
    accepted: tuple[Claim, ...]
    rejected: tuple[Claim, ...]
    reasons: Mapping[str, tuple[str, ...]]
    contradictions: tuple[Contradiction, ...]

    @property
    def grounded_fraction(self) -> float:
        total = len(self.accepted) + len(self.rejected)
        return len(self.accepted) / total if total else 1.0

    @property
    def ok(self) -> bool:
        return not self.rejected and not self.contradictions


class GroundingGate:
    def __init__(
        self,
        ledger: EvidenceLedger,
        *,
        policy: GroundingPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ledger = ledger
        self.policy = policy or GroundingPolicy()
        self._clock = clock

    def check(self, claims: Sequence[Claim]) -> GroundingReport:
        if len(claims) > self.policy.maximum_claims:
            raise EvidenceError("claim count exceeds grounding policy")
        accepted: list[Claim] = []
        rejected: list[Claim] = []
        reasons: dict[str, tuple[str, ...]] = {}
        referenced_ids: set[str] = set()
        now = self._clock()
        for claim in claims:
            if not isinstance(claim, Claim):
                raise TypeError("claims must contain Claim values")
            problems: list[str] = []
            if claim.confidence < self.policy.minimum_claim_confidence:
                problems.append("claim confidence below threshold")
            if claim.derived and self.policy.require_evidence_for_derived and not claim.evidence:
                problems.append("derived claim has no evidence")
            for ref in claim.evidence:
                artifact = self.ledger.get(ref.evidence_id)
                if artifact is None:
                    problems.append(f"unknown evidence {ref.evidence_id}")
                    continue
                referenced_ids.add(ref.evidence_id)
                if artifact.fingerprint != ref.fingerprint:
                    problems.append(f"evidence fingerprint mismatch {ref.evidence_id}")
                if min(artifact.confidence, ref.confidence) < self.policy.minimum_evidence_confidence:
                    problems.append(f"evidence confidence below threshold {ref.evidence_id}")
                if self.policy.maximum_evidence_age_seconds is not None:
                    age = now - artifact.observed_at
                    if age < 0 or age > self.policy.maximum_evidence_age_seconds:
                        problems.append(f"evidence stale {ref.evidence_id}")
            if problems:
                rejected.append(claim)
                reasons[claim.claim_id] = tuple(problems)
            else:
                accepted.append(claim)
        contradictions = self.ledger.contradictions_for(referenced_ids)
        if contradictions and self.policy.reject_contradictions:
            contradicted = {item.left_id for item in contradictions} | {item.right_id for item in contradictions}
            still_accepted: list[Claim] = []
            for claim in accepted:
                if any(ref.evidence_id in contradicted for ref in claim.evidence):
                    rejected.append(claim)
                    reasons[claim.claim_id] = reasons.get(claim.claim_id, ()) + ("claim relies on contradictory evidence",)
                else:
                    still_accepted.append(claim)
            accepted = still_accepted
        return GroundingReport(tuple(accepted), tuple(rejected), reasons, contradictions)


class LearningEvidenceBridge:
    """Project verified artifacts into ``skeleton.learning.evidence`` safely.

    The bridge accepts *host-verified artifacts*, never raw live-model output.
    It intentionally writes root observations only.  Features, hypotheses,
    predictions, and outcomes should be constructed by their dedicated
    deterministic workflows so the fact/analysis/result planes from PR #1038
    remain separated.
    """

    def __init__(self, store: Any) -> None:
        required = ("record_observation", "version", "clock_version")
        if any(not hasattr(store, name) for name in required):
            raise TypeError("store does not implement LearningEvidenceStore contract")
        self.store = store

    def record_artifact(self, artifact: EvidenceArtifact, *, subject_id: str) -> Any:
        if artifact.kind is EvidenceKind.DERIVED:
            raise EvidenceError("derived model analysis cannot be written as a root fact")
        from skeleton.learning.evidence import Observation, make_provenance

        subject_id = require_id("subject_id", subject_id)
        payload = {
            "evidence_id": artifact.evidence_id,
            "kind": artifact.kind.value,
            "source": artifact.source,
            "payload": artifact.payload,
            "confidence": artifact.confidence,
        }
        # PR #1038 intentionally restricts observation payload values to JSON
        # scalars.  Preserve complex payload integrity by storing its canonical
        # fingerprint while exposing safe scalar metadata.
        observation_payload = {
            "evidence_id": artifact.evidence_id,
            "kind": artifact.kind.value,
            "source": artifact.source,
            "payload_fingerprint": stable_fingerprint(artifact.payload),
            "confidence": artifact.confidence,
        }
        provenance = make_provenance(
            observation_payload,
            source_id=artifact.evidence_id,
            source_kind="verified-evidence",
            observed_at=artifact.observed_at,
            clock_version=self.store.clock_version,
            uri=artifact.uri,
        )
        observation = Observation(
            observation_id=stable_id("obs", {"subject": subject_id, "evidence": artifact.evidence_id}),
            subject_id=subject_id,
            payload=observation_payload,
            provenance=provenance,
        )
        return self.store.record_observation(observation)


def evidence_from_payload(
    payload: Any,
    *,
    kind: EvidenceKind,
    source: str,
    observed_at: float,
    confidence: float = 1.0,
    uri: str | None = None,
    parent_ids: Sequence[str] = (),
    metadata: Mapping[str, Any] | None = None,
) -> EvidenceArtifact:
    safe_payload = json_safe(payload)
    evidence_id = stable_id(
        "evidence",
        {
            "kind": kind.value if isinstance(kind, EvidenceKind) else str(kind),
            "source": source,
            "payload": safe_payload,
            "parents": list(parent_ids),
        },
    )
    return EvidenceArtifact(
        evidence_id=evidence_id,
        kind=kind,
        source=source,
        payload=safe_payload,
        observed_at=observed_at,
        confidence=confidence,
        uri=uri,
        parent_ids=tuple(parent_ids),
        metadata=metadata or {},
    )
