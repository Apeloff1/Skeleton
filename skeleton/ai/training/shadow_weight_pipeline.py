"""Evidence-first shadow-weight intake owned by the canonical training plane.

A source claim is NOT a weight shard and a shadow admission is NOT a trained
model. This boundary deliberately separates acquisition, independent source
corroboration, lawful dataset preparation, model training and runtime promotion.

Only the independently verified handoff becomes eligible for candidate-only
training; actual production model admission remains with the existing
PromotionEvidence + RuntimeAdmission/rollback lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
from threading import RLock
from typing import Iterable

from .flgb_training_runtime import digest_json, require_digest, require_id


class ShadowWeightError(ValueError):
    """Invalid evidence, lifecycle transition, or candidate identity."""


class ShadowState(str, Enum):
    INBOX = "inbox"
    CORROBORATED = "corroborated"
    QUARANTINED = "quarantined"
    TRAINING_ELIGIBLE = "training_eligible"
    REJECTED = "rejected"
    CONSUMED = "consumed"


RIGHTS = frozenset({"allowed", "restricted", "quarantined", "denied"})
MAX_SOURCES = 64
MAX_ENTRIES = 20_000
MAX_LEDGER_EVENTS = 200_000


def _id(value: str, name: str) -> str:
    return require_id(value, name)


def _digest(value: str, name: str) -> str:
    return require_digest(value, name)


def _ppm(value: int, name: str) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise ShadowWeightError(f"{name} must be an integer in 0..1000000")
    return value


@dataclass(frozen=True, slots=True)
class SourceAttestation:
    source_id: str
    content_digest: str
    claim_digest: str
    independence_group: str
    rights_status: str
    rights_evidence_digest: str
    observed_at_ns: int

    def __post_init__(self) -> None:
        for field in ("source_id", "independence_group"):
            _id(getattr(self, field), field)
        for field in ("content_digest", "claim_digest", "rights_evidence_digest"):
            _digest(getattr(self, field), field)
        if self.rights_status not in RIGHTS:
            raise ShadowWeightError("unsupported source rights_status")
        if type(self.observed_at_ns) is not int or self.observed_at_ns < 0:
            raise ShadowWeightError("source observation timestamp must be non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "content_digest": self.content_digest,
            "claim_digest": self.claim_digest,
            "independence_group": self.independence_group,
            "rights_status": self.rights_status,
            "rights_evidence_digest": self.rights_evidence_digest,
            "observed_at_ns": self.observed_at_ns,
        }


@dataclass(frozen=True, slots=True)
class ShadowWeightIntake:
    intake_id: str
    subject_id: str
    claim_digest: str
    target_scope: str
    sources: tuple[SourceAttestation, ...]
    proposed_dataset_digest: str
    parent_model_digest: str
    proposed_by: str
    relevance_ppm: int
    confidence_ppm: int
    novelty_ppm: int
    observed_at_ns: int

    def __post_init__(self) -> None:
        for field in ("intake_id", "subject_id", "target_scope", "proposed_by"):
            _id(getattr(self, field), field)
        for field in ("claim_digest", "proposed_dataset_digest", "parent_model_digest"):
            _digest(getattr(self, field), field)
        for field in ("relevance_ppm", "confidence_ppm", "novelty_ppm"):
            _ppm(getattr(self, field), field)
        if type(self.observed_at_ns) is not int or self.observed_at_ns < 0:
            raise ShadowWeightError("intake timestamp must be non-negative")
        if not isinstance(self.sources, tuple) or not 1 <= len(self.sources) <= MAX_SOURCES:
            raise ShadowWeightError("shadow intake requires bounded source attestations")
        if any(not isinstance(x, SourceAttestation) for x in self.sources):
            raise ShadowWeightError("source evidence must be SourceAttestation")
        if len({x.source_id for x in self.sources}) != len(self.sources):
            raise ShadowWeightError("duplicate source identity")
        if any(x.claim_digest != self.claim_digest for x in self.sources):
            raise ShadowWeightError("sources must corroborate the same exact claim")
        if any(x.observed_at_ns > self.observed_at_ns for x in self.sources):
            raise ShadowWeightError("intake cannot precede a claimed observation")
        object.__setattr__(self, "sources", tuple(sorted(self.sources, key=lambda x: x.source_id)))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "skeleton.shadow_weight_intake.v1",
            "intake_id": self.intake_id,
            "subject_id": self.subject_id,
            "claim_digest": self.claim_digest,
            "target_scope": self.target_scope,
            "sources": [source.to_dict() for source in self.sources],
            "proposed_dataset_digest": self.proposed_dataset_digest,
            "parent_model_digest": self.parent_model_digest,
            "proposed_by": self.proposed_by,
            "relevance_ppm": self.relevance_ppm,
            "confidence_ppm": self.confidence_ppm,
            "novelty_ppm": self.novelty_ppm,
            "observed_at_ns": self.observed_at_ns,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ShadowPolicy:
    minimum_independent_groups: int = 2
    minimum_relevance_ppm: int = 550_000
    minimum_confidence_ppm: int = 700_000
    minimum_novelty_ppm: int = 100_000
    maximum_evidence_age_ns: int = 90 * 24 * 3600 * 1_000_000_000

    def __post_init__(self) -> None:
        if type(self.minimum_independent_groups) is not int or not 2 <= self.minimum_independent_groups <= MAX_SOURCES:
            raise ShadowWeightError("independent group floor must be 2..64")
        for field in ("minimum_relevance_ppm", "minimum_confidence_ppm", "minimum_novelty_ppm"):
            _ppm(getattr(self, field), field)
        if type(self.maximum_evidence_age_ns) is not int or self.maximum_evidence_age_ns < 1:
            raise ShadowWeightError("evidence age budget must be positive")


@dataclass(frozen=True, slots=True)
class ShadowReview:
    intake_digest: str
    verifier_id: str
    reviewed_at_ns: int
    rights_clear: bool
    contamination_clear: bool
    dataset_scope_approved: bool
    evaluator_evidence_digest: str
    contamination_evidence_digest: str
    decision: ShadowState
    explanation_digest: str

    def __post_init__(self) -> None:
        for field in ("intake_digest", "evaluator_evidence_digest",
                      "contamination_evidence_digest", "explanation_digest"):
            _digest(getattr(self, field), field)
        _id(self.verifier_id, "verifier_id")
        if type(self.reviewed_at_ns) is not int or self.reviewed_at_ns < 0:
            raise ShadowWeightError("reviewed_at_ns must be non-negative")
        if any(type(getattr(self, name)) is not bool for name in
               ("rights_clear", "contamination_clear", "dataset_scope_approved")):
            raise ShadowWeightError("review gates must be booleans")
        if self.decision not in (ShadowState.CORROBORATED, ShadowState.QUARANTINED,
                                 ShadowState.REJECTED):
            raise ShadowWeightError("review must corroborate, quarantine, or reject")

    @property
    def digest(self) -> str:
        return digest_json({
            "intake_digest": self.intake_digest,
            "verifier_id": self.verifier_id,
            "reviewed_at_ns": self.reviewed_at_ns,
            "rights_clear": self.rights_clear,
            "contamination_clear": self.contamination_clear,
            "dataset_scope_approved": self.dataset_scope_approved,
            "evaluator_evidence_digest": self.evaluator_evidence_digest,
            "contamination_evidence_digest": self.contamination_evidence_digest,
            "decision": self.decision.value,
            "explanation_digest": self.explanation_digest,
        })


@dataclass(frozen=True, slots=True)
class ShadowRecord:
    intake: ShadowWeightIntake
    state: ShadowState = ShadowState.INBOX
    version: int = 0
    review_digest: str | None = None
    training_manifest_digest: str | None = None
    consumed_candidate_digest: str | None = None
    last_event_digest: str | None = None

    @property
    def identity(self) -> str:
        return self.intake.intake_id

    def to_dict(self) -> dict[str, object]:
        return {
            "intake": self.intake.to_dict(), "state": self.state.value,
            "version": self.version, "review_digest": self.review_digest,
            "training_manifest_digest": self.training_manifest_digest,
            "consumed_candidate_digest": self.consumed_candidate_digest,
            "last_event_digest": self.last_event_digest,
        }


@dataclass(frozen=True, slots=True)
class ShadowEvent:
    intake_id: str
    version: int
    prior_digest: str
    record_digest: str
    operation: str
    authority: str
    evidence_digest: str
    at_ns: int

    @property
    def digest(self) -> str:
        return digest_json({
            "intake_id": self.intake_id, "version": self.version,
            "prior_digest": self.prior_digest, "record_digest": self.record_digest,
            "operation": self.operation, "authority": self.authority,
            "evidence_digest": self.evidence_digest, "at_ns": self.at_ns,
        })


class ShadowWeightPipeline:
    """In-memory authority-bound intake. Model weights are never mutated here.

    Persist events/records with the host's canonical authoritative store.
    The pipeline itself is intentionally provider-neutral and side-effect free
    beyond its own guarded state updates.
    """

    GENESIS = "0" * 64

    def __init__(self, *, policy: ShadowPolicy | None = None) -> None:
        self.policy = policy or ShadowPolicy()
        self._lock = RLock()
        self._records: dict[str, ShadowRecord] = {}
        self._events: list[ShadowEvent] = []
        self._head = self.GENESIS

    def get(self, intake_id: str) -> ShadowRecord | None:
        with self._lock:
            return self._records.get(_id(intake_id, "intake_id"))

    def entries(
        self, *, state: ShadowState | None = None,
        states: tuple[ShadowState, ...] | None = None,
        offset: int = 0, limit: int = 100,
    ) -> tuple[ShadowRecord, ...]:
        """Page eligible candidates by relevance without excluding later records.

        Keep the original single-state filter for existing consumers. A host
        scheduler may instead request a bounded union of states and paginate
        the entire priority frontier.
        """
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ShadowWeightError("entry page budget exceeded")
        if type(offset) is not int or not 0 <= offset <= MAX_ENTRIES:
            raise ShadowWeightError("entry offset exceeds storage capacity")
        if state is not None and states is not None:
            raise ShadowWeightError("select state or states, not both")
        if state is not None and not isinstance(state, ShadowState):
            raise ShadowWeightError("invalid shadow state filter")
        if states is not None and (
            not isinstance(states, tuple) or not 1 <= len(states) <= len(ShadowState)
            or any(not isinstance(item, ShadowState) for item in states)
            or len(set(states)) != len(states)
        ):
            raise ShadowWeightError("invalid shadow state selection")
        allowed = frozenset(states) if states is not None else (
            frozenset((state,)) if state is not None else None
        )
        with self._lock:
            records = sorted(self._records.values(),
                             key=lambda r: (-r.intake.relevance_ppm, r.identity))
            selected = (r for r in records if allowed is None or r.state in allowed)
            from itertools import islice
            return tuple(islice(selected, offset, offset + limit))

    def _record(self, record: ShadowRecord, *, operation: str, authority: str,
                evidence_digest: str, at_ns: int) -> ShadowRecord:
        if len(self._events) >= MAX_LEDGER_EVENTS:
            raise ShadowWeightError("shadow ledger is full")
        if type(at_ns) is not int or at_ns < 0:
            raise ShadowWeightError("event timestamp must be non-negative")
        _id(authority, "authority")
        _digest(evidence_digest, "evidence_digest")
        raw = record.to_dict()
        event = ShadowEvent(
            intake_id=record.identity, version=record.version,
            prior_digest=self._head, record_digest=digest_json(raw),
            operation=operation, authority=authority,
            evidence_digest=evidence_digest, at_ns=at_ns,
        )
        record = replace(record, last_event_digest=event.digest)
        self._records[record.identity] = record
        self._events.append(event)
        self._head = event.digest
        return record

    def submit(self, intake: ShadowWeightIntake) -> ShadowRecord:
        if not isinstance(intake, ShadowWeightIntake):
            raise ShadowWeightError("intake must be ShadowWeightIntake")
        with self._lock:
            prior = self._records.get(intake.intake_id)
            if prior is not None:
                if prior.intake.digest == intake.digest:
                    return prior
                raise ShadowWeightError("intake ID already bound to different content")
            if len(self._records) >= MAX_ENTRIES:
                raise ShadowWeightError("shadow intake capacity exceeded")
            return self._record(
                ShadowRecord(intake), operation="submit", authority=intake.proposed_by,
                evidence_digest=intake.digest, at_ns=intake.observed_at_ns,
            )

    def _candidate_quality(self, intake: ShadowWeightIntake, at_ns: int) -> tuple[str, ...]:
        reasons: list[str] = []
        if any(source.rights_status != "allowed" for source in intake.sources):
            reasons.append("rights_not_allowed")
        groups = {source.independence_group for source in intake.sources}
        if len(groups) < self.policy.minimum_independent_groups:
            reasons.append("insufficient_independent_sources")
        if intake.relevance_ppm < self.policy.minimum_relevance_ppm:
            reasons.append("low_task_relevance")
        if intake.confidence_ppm < self.policy.minimum_confidence_ppm:
            reasons.append("low_confidence")
        if intake.novelty_ppm < self.policy.minimum_novelty_ppm:
            reasons.append("insufficient_novelty")
        if any(at_ns < source.observed_at_ns
               or at_ns - source.observed_at_ns > self.policy.maximum_evidence_age_ns
               for source in intake.sources):
            reasons.append("stale_or_future_source_evidence")
        return tuple(reasons)

    def review(self, intake_id: str, review: ShadowReview, *, expected_version: int) -> ShadowRecord:
        if not isinstance(review, ShadowReview):
            raise ShadowWeightError("review must be ShadowReview")
        with self._lock:
            prior = self._records.get(_id(intake_id, "intake_id"))
            if prior is None or prior.version != expected_version:
                raise ShadowWeightError("unknown or stale shadow intake")
            if prior.state not in (ShadowState.INBOX, ShadowState.QUARANTINED):
                raise ShadowWeightError("shadow intake is not reviewable")
            if review.intake_digest != prior.intake.digest or review.verifier_id == prior.intake.proposed_by:
                raise ShadowWeightError("review identity mismatch or self-verification")
            if review.reviewed_at_ns < prior.intake.observed_at_ns:
                raise ShadowWeightError("review precedes intake")
            failures = self._candidate_quality(prior.intake, review.reviewed_at_ns)
            passed = (not failures and review.rights_clear and review.contamination_clear
                      and review.dataset_scope_approved)
            if review.decision is ShadowState.CORROBORATED and not passed:
                raise ShadowWeightError("corroboration requires every independent gate")
            if review.decision is ShadowState.REJECTED and passed:
                raise ShadowWeightError("passing review cannot be represented as rejection")
            updated = replace(prior, state=review.decision,
                              version=prior.version + 1, review_digest=review.digest)
            return self._record(
                updated, operation="review", authority=review.verifier_id,
                evidence_digest=review.digest, at_ns=review.reviewed_at_ns,
            )

    def admit_training(self, intake_id: str, *, expected_version: int,
                       training_manifest_digest: str, training_authority: str,
                       evidence_digest: str, at_ns: int) -> ShadowRecord:
        """Publish an intake eligibility binding, NEVER deploy model parameters."""
        _digest(training_manifest_digest, "training_manifest_digest")
        with self._lock:
            prior = self._records.get(_id(intake_id, "intake_id"))
            if prior is None or prior.version != expected_version:
                raise ShadowWeightError("unknown or stale shadow intake")
            if prior.state is not ShadowState.CORROBORATED or prior.review_digest is None:
                raise ShadowWeightError("independent corroboration required before training")
            if training_authority in (prior.intake.proposed_by,):
                raise ShadowWeightError("training admission must be independently authorized")
            if type(at_ns) is not int or at_ns < prior.intake.observed_at_ns:
                raise ShadowWeightError("invalid training admission time")
            if self._candidate_quality(prior.intake, at_ns):
                raise ShadowWeightError("shadow evidence is stale or below policy")
            updated = replace(prior, state=ShadowState.TRAINING_ELIGIBLE,
                              version=prior.version + 1,
                              training_manifest_digest=training_manifest_digest)
            return self._record(updated, operation="admit_training",
                                authority=training_authority,
                                evidence_digest=evidence_digest, at_ns=at_ns)

    def consume(self, intake_id: str, *, expected_version: int,
                verified_candidate_digest: str, authority: str, at_ns: int) -> ShadowRecord:
        """Attach an external candidate artifact. It remains candidate-only."""
        _digest(verified_candidate_digest, "verified_candidate_digest")
        with self._lock:
            prior = self._records.get(_id(intake_id, "intake_id"))
            if prior is None or prior.version != expected_version:
                raise ShadowWeightError("unknown or stale shadow intake")
            if prior.state is not ShadowState.TRAINING_ELIGIBLE:
                raise ShadowWeightError("training was not independently admitted")
            updated = replace(prior, state=ShadowState.CONSUMED,
                              version=prior.version + 1,
                              consumed_candidate_digest=verified_candidate_digest)
            return self._record(updated, operation="consume", authority=authority,
                                evidence_digest=verified_candidate_digest, at_ns=at_ns)

    def quarantine(self, intake_id: str, *, expected_version: int,
                   reason_digest: str, authority: str, at_ns: int) -> ShadowRecord:
        with self._lock:
            prior = self._records.get(_id(intake_id, "intake_id"))
            if prior is None or prior.version != expected_version:
                raise ShadowWeightError("unknown or stale shadow intake")
            if prior.state in (ShadowState.REJECTED, ShadowState.CONSUMED):
                raise ShadowWeightError("terminal shadow intake cannot be reopened")
            updated = replace(prior, state=ShadowState.QUARANTINED,
                              version=prior.version + 1)
            return self._record(updated, operation="quarantine", authority=authority,
                                evidence_digest=reason_digest, at_ns=at_ns)

    def events(self, *, start: int = 0, limit: int = 100) -> tuple[ShadowEvent, ...]:
        if type(start) is not int or start < 0 or type(limit) is not int or not 1 <= limit <= 1000:
            raise ShadowWeightError("event pagination exceeds bound")
        with self._lock:
            return tuple(self._events[start:start + limit])

    @property
    def head_digest(self) -> str:
        with self._lock:
            return self._head

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            rows = [x.to_dict() for x in sorted(self._records.values(), key=lambda r: r.identity)]
            return {
                "schema": "skeleton.shadow_weight_queue.v1",
                "head_digest": self._head,
                "event_count": len(self._events),
                "record_count": len(rows),
                "records": rows,
                "training_status": "proposal_only; no model weights deployed",
            }


__all__ = [
    "ShadowWeightError", "ShadowState", "SourceAttestation",
    "ShadowWeightIntake", "ShadowPolicy", "ShadowReview",
    "ShadowRecord", "ShadowEvent", "ShadowWeightPipeline",
]
