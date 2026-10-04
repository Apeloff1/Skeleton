"""Evidence-bound multi-agent orchestration for VOL-017.

This module closes two explicit masterplan gaps without introducing another
scheduler:

* conflict-domain ownership is an exclusive, generation-fenced mutation lease;
* disagreement resolution is based on independent verifier evidence, never raw
  agent-majority text.

Existing handoff envelopes remain the task transport. Existing worker runtimes
remain execution owners. This boundary only decides whether a handoff may own a
mutation domain and whether conflicting candidate outputs have sufficient,
independent evidence to resolve deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import threading
from typing import Any, Mapping, Sequence

from skeleton.automation.swarm.handoff import TaskEnvelope, TaskState
from skeleton.kernel.errors import AgentError


SCHEMA = "skeleton.multi_agent_orchestration.v1"


class MultiAgentOrchestrationError(AgentError):
    """The orchestration contract was invalid or could not resolve safely."""

    code = "AGT.MULTI_AGENT_ORCHESTRATION"


class ConflictDomainBusy(MultiAgentOrchestrationError):
    """A live mutation lease already owns the requested conflict domain."""

    code = "AGT.CONFLICT_DOMAIN_BUSY"


class ArbitrationStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise MultiAgentOrchestrationError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized or normalized != value:
        raise MultiAgentOrchestrationError(
            f"{field} must be a non-empty canonical token"
        )
    if len(normalized) > 256:
        raise MultiAgentOrchestrationError(f"{field} exceeds 256 characters")
    return normalized


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MultiAgentOrchestrationError(
            f"{field} must be a positive integer"
        )
    return value


def _finite_number(
    value: object,
    field: str,
    *,
    positive: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MultiAgentOrchestrationError(f"{field} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise MultiAgentOrchestrationError(f"{field} must be finite")
    if positive and normalized <= 0:
        raise MultiAgentOrchestrationError(f"{field} must be greater than zero")
    return normalized


def _sha256(value: object, field: str) -> str:
    token = _token(value, field)
    if len(token) != 64 or any(ch not in "0123456789abcdef" for ch in token):
        raise MultiAgentOrchestrationError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return token


def _canonical_json(value: object, field: str) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MultiAgentOrchestrationError(
            f"{field} must be canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value, "digest payload")).hexdigest()


def _sorted_unique_tokens(
    values: Sequence[str],
    field: str,
    *,
    maximum: int | None = None,
) -> tuple[str, ...]:
    normalized = tuple(sorted({_token(value, field) for value in values}))
    if not normalized:
        raise MultiAgentOrchestrationError(f"{field} must not be empty")
    if maximum is not None and len(normalized) > maximum:
        raise MultiAgentOrchestrationError(
            f"{field} exceeds bounded maximum {maximum}"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class ConflictDomain:
    """One exclusive mutation namespace.

    Domains are deliberately exclusive. Parallel read/analysis work does not
    need a domain lease; any operation that can mutate the same logical
    resource must serialize through one generation-fenced domain.
    """

    domain_id: str
    resource_key: str
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain_id", _token(self.domain_id, "domain_id"))
        object.__setattr__(
            self,
            "resource_key",
            _token(self.resource_key, "resource_key"),
        )
        if not isinstance(self.description, str):
            raise MultiAgentOrchestrationError("description must be a string")
        if len(self.description) > 1024:
            raise MultiAgentOrchestrationError(
                "description exceeds 1024 characters"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCHEMA,
                "kind": "conflict-domain",
                "domain_id": self.domain_id,
                "resource_key": self.resource_key,
                "description": self.description,
            }
        )


@dataclass(frozen=True, slots=True)
class FencingToken:
    """Monotonic generation proving the current conflict-domain owner."""

    domain_id: str
    generation: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain_id", _token(self.domain_id, "domain_id"))
        object.__setattr__(
            self,
            "generation",
            _positive_int(self.generation, "generation"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCHEMA,
                "kind": "fencing-token",
                "domain_id": self.domain_id,
                "generation": self.generation,
            }
        )


@dataclass(frozen=True, slots=True)
class WorkLease:
    """Exclusive, expiring mutation authority for one task and worker."""

    lease_id: str
    task_id: str
    worker_id: str
    domain_id: str
    fence: FencingToken
    issued_at: float
    expires_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "lease_id", _sha256(self.lease_id, "lease_id"))
        object.__setattr__(self, "task_id", _token(self.task_id, "task_id"))
        object.__setattr__(self, "worker_id", _token(self.worker_id, "worker_id"))
        object.__setattr__(self, "domain_id", _token(self.domain_id, "domain_id"))
        if not isinstance(self.fence, FencingToken):
            raise MultiAgentOrchestrationError(
                "fence must be a FencingToken"
            )
        if self.fence.domain_id != self.domain_id:
            raise MultiAgentOrchestrationError(
                "fence domain does not match work lease"
            )
        issued = _finite_number(self.issued_at, "issued_at")
        expires = _finite_number(self.expires_at, "expires_at")
        if expires <= issued:
            raise MultiAgentOrchestrationError(
                "expires_at must be greater than issued_at"
            )
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def active(self, now: float) -> bool:
        return _finite_number(now, "now") < self.expires_at

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCHEMA,
                "kind": "work-lease",
                "lease_id": self.lease_id,
                "task_id": self.task_id,
                "worker_id": self.worker_id,
                "domain_id": self.domain_id,
                "fence": self.fence.digest,
                "issued_at": self.issued_at,
                "expires_at": self.expires_at,
            }
        )


@dataclass(frozen=True, slots=True)
class AgentHandoff:
    """Digest-bound projection of a live A2A handoff into conflict domains."""

    task_id: str
    requester_id: str
    assignee_id: str
    capability: str
    payload_digest: str
    conflict_domains: tuple[str, ...]
    created_at: float
    updated_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _token(self.task_id, "task_id"))
        object.__setattr__(
            self,
            "requester_id",
            _token(self.requester_id, "requester_id"),
        )
        object.__setattr__(
            self,
            "assignee_id",
            _token(self.assignee_id, "assignee_id"),
        )
        object.__setattr__(
            self,
            "capability",
            _token(self.capability, "capability"),
        )
        object.__setattr__(
            self,
            "payload_digest",
            _sha256(self.payload_digest, "payload_digest"),
        )
        domains = _sorted_unique_tokens(
            self.conflict_domains,
            "conflict_domains",
        )
        object.__setattr__(self, "conflict_domains", domains)
        created = _finite_number(self.created_at, "created_at")
        updated = _finite_number(self.updated_at, "updated_at")
        if updated < created:
            raise MultiAgentOrchestrationError(
                "handoff updated_at precedes created_at"
            )
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)

    @classmethod
    def from_envelope(
        cls,
        envelope: TaskEnvelope,
        *,
        conflict_domains: Sequence[str],
        max_conflict_domains: int,
    ) -> "AgentHandoff":
        if not isinstance(envelope, TaskEnvelope):
            raise MultiAgentOrchestrationError(
                "envelope must be a TaskEnvelope"
            )
        if envelope.state is not TaskState.WORKING:
            raise MultiAgentOrchestrationError(
                "handoff envelope must be in working state"
            )
        if envelope.assignee is None:
            raise MultiAgentOrchestrationError(
                "handoff envelope requires an assignee"
            )
        domains = _sorted_unique_tokens(
            conflict_domains,
            "conflict_domains",
            maximum=_positive_int(
                max_conflict_domains,
                "max_conflict_domains",
            ),
        )
        return cls(
            task_id=envelope.task_id,
            requester_id=envelope.requester,
            assignee_id=envelope.assignee,
            capability=envelope.capability,
            payload_digest=hashlib.sha256(
                _canonical_json(envelope.input, "handoff input")
            ).hexdigest(),
            conflict_domains=domains,
            created_at=envelope.created_at,
            updated_at=envelope.updated_at,
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCHEMA,
                "kind": "agent-handoff",
                "task_id": self.task_id,
                "requester_id": self.requester_id,
                "assignee_id": self.assignee_id,
                "capability": self.capability,
                "payload_digest": self.payload_digest,
                "conflict_domains": list(self.conflict_domains),
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }
        )


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    """Independent verifier evidence bound to one candidate output digest."""

    verifier_id: str
    subject_digest: str
    evidence_refs: tuple[str, ...]
    verified: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "verifier_id",
            _token(self.verifier_id, "verifier_id"),
        )
        object.__setattr__(
            self,
            "subject_digest",
            _sha256(self.subject_digest, "subject_digest"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _sorted_unique_tokens(self.evidence_refs, "evidence_refs"),
        )
        if not isinstance(self.verified, bool):
            raise MultiAgentOrchestrationError("verified must be a boolean")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCHEMA,
                "kind": "evidence-claim",
                "verifier_id": self.verifier_id,
                "subject_digest": self.subject_digest,
                "evidence_refs": list(self.evidence_refs),
                "verified": self.verified,
            }
        )


@dataclass(frozen=True, slots=True)
class ArbitrationCandidate:
    """One conflicting output plus verifier evidence for that exact output."""

    candidate_id: str
    output_digest: str
    claims: tuple[EvidenceClaim, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _token(self.candidate_id, "candidate_id"),
        )
        object.__setattr__(
            self,
            "output_digest",
            _sha256(self.output_digest, "output_digest"),
        )
        if not isinstance(self.claims, tuple) or not self.claims:
            raise MultiAgentOrchestrationError(
                "candidate requires verifier claims"
            )
        seen: set[str] = set()
        for claim in self.claims:
            if not isinstance(claim, EvidenceClaim):
                raise MultiAgentOrchestrationError(
                    "claims must contain EvidenceClaim values"
                )
            if claim.subject_digest != self.output_digest:
                raise MultiAgentOrchestrationError(
                    "claim subject does not match candidate output"
                )
            if claim.verifier_id in seen:
                raise MultiAgentOrchestrationError(
                    "candidate contains duplicate verifier"
                )
            seen.add(claim.verifier_id)

    @property
    def verified_verifiers(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                claim.verifier_id
                for claim in self.claims
                if claim.verified
            )
        )

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        refs = {
            ref
            for claim in self.claims
            if claim.verified
            for ref in claim.evidence_refs
        }
        return tuple(sorted(refs))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCHEMA,
                "kind": "arbitration-candidate",
                "candidate_id": self.candidate_id,
                "output_digest": self.output_digest,
                "claims": sorted(claim.digest for claim in self.claims),
            }
        )


@dataclass(frozen=True, slots=True)
class ArbitrationDecision:
    """Deterministic resolution; ties and verifier ambiguity fail closed."""

    status: ArbitrationStatus
    candidate_ids: tuple[str, ...]
    selected_candidate_id: str | None
    verified_counts: tuple[tuple[str, int], ...]
    evidence_refs: tuple[str, ...]
    reason: str
    decision_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.status, ArbitrationStatus):
            raise MultiAgentOrchestrationError(
                "status must be ArbitrationStatus"
            )
        object.__setattr__(
            self,
            "candidate_ids",
            _sorted_unique_tokens(self.candidate_ids, "candidate_ids"),
        )
        if self.selected_candidate_id is not None:
            selected = _token(
                self.selected_candidate_id,
                "selected_candidate_id",
            )
            if selected not in self.candidate_ids:
                raise MultiAgentOrchestrationError(
                    "selected candidate is not part of arbitration"
                )
            object.__setattr__(self, "selected_candidate_id", selected)
        object.__setattr__(
            self,
            "evidence_refs",
            tuple(sorted(set(self.evidence_refs))),
        )
        object.__setattr__(self, "reason", _token(self.reason, "reason"))
        object.__setattr__(
            self,
            "decision_digest",
            _sha256(self.decision_digest, "decision_digest"),
        )


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    """Audit record binding a conflict domain to its evidence decision."""

    domain_id: str
    task_id: str
    candidate_ids: tuple[str, ...]
    selected_candidate_id: str | None
    arbitration_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain_id", _token(self.domain_id, "domain_id"))
        object.__setattr__(self, "task_id", _token(self.task_id, "task_id"))
        object.__setattr__(
            self,
            "candidate_ids",
            _sorted_unique_tokens(self.candidate_ids, "candidate_ids"),
        )
        if self.selected_candidate_id is not None:
            selected = _token(
                self.selected_candidate_id,
                "selected_candidate_id",
            )
            if selected not in self.candidate_ids:
                raise MultiAgentOrchestrationError(
                    "selected candidate is absent from conflict"
                )
            object.__setattr__(self, "selected_candidate_id", selected)
        object.__setattr__(
            self,
            "arbitration_digest",
            _sha256(self.arbitration_digest, "arbitration_digest"),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": SCHEMA,
                "kind": "conflict-record",
                "domain_id": self.domain_id,
                "task_id": self.task_id,
                "candidate_ids": list(self.candidate_ids),
                "selected_candidate_id": self.selected_candidate_id,
                "arbitration_digest": self.arbitration_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class BoundedOrchestrationPolicy:
    """Resource bounds for one orchestration boundary."""

    max_fanout: int = 8
    max_conflict_domains_per_task: int = 8
    max_arbitration_candidates: int = 8
    min_independent_verifiers: int = 1

    def __post_init__(self) -> None:
        for field in (
            "max_fanout",
            "max_conflict_domains_per_task",
            "max_arbitration_candidates",
            "min_independent_verifiers",
        ):
            object.__setattr__(
                self,
                field,
                _positive_int(getattr(self, field), field),
            )


class ConflictDomainRegistry:
    """Thread-safe exclusive mutation ownership with generation fencing."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._domains: dict[str, ConflictDomain] = {}
        self._resource_owners: dict[str, str] = {}
        self._leases: dict[str, WorkLease] = {}
        self._generations: dict[str, int] = {}

    def register(self, domain: ConflictDomain) -> ConflictDomain:
        if not isinstance(domain, ConflictDomain):
            raise MultiAgentOrchestrationError(
                "domain must be ConflictDomain"
            )
        with self._lock:
            current = self._domains.get(domain.domain_id)
            if current is not None:
                if current != domain:
                    raise MultiAgentOrchestrationError(
                        "conflict domain id is already bound differently"
                    )
                return current
            owner = self._resource_owners.get(domain.resource_key)
            if owner is not None and owner != domain.domain_id:
                raise MultiAgentOrchestrationError(
                    "resource key is already owned by another conflict domain"
                )
            self._domains[domain.domain_id] = domain
            self._resource_owners[domain.resource_key] = domain.domain_id
            self._generations.setdefault(domain.domain_id, 0)
            return domain

    def require(self, domain_id: str) -> ConflictDomain:
        domain = self._domains.get(_token(domain_id, "domain_id"))
        if domain is None:
            raise MultiAgentOrchestrationError("unknown conflict domain")
        return domain

    def _live_lease(self, domain_id: str, now: float) -> WorkLease | None:
        current = self._leases.get(domain_id)
        if current is None:
            return None
        if current.active(now):
            return current
        self._leases.pop(domain_id, None)
        return None

    def acquire(
        self,
        domain_id: str,
        *,
        task_id: str,
        worker_id: str,
        ttl_s: float,
        now: float,
    ) -> WorkLease:
        domain = _token(domain_id, "domain_id")
        task = _token(task_id, "task_id")
        worker = _token(worker_id, "worker_id")
        ttl = _finite_number(ttl_s, "ttl_s", positive=True)
        observed = _finite_number(now, "now")
        with self._lock:
            self.require(domain)
            current = self._live_lease(domain, observed)
            if current is not None:
                if current.task_id == task and current.worker_id == worker:
                    return current
                raise ConflictDomainBusy(
                    "conflict domain already has a live mutation lease"
                )
            generation = self._generations.get(domain, 0) + 1
            fence = FencingToken(domain, generation)
            lease_payload = {
                "schema": SCHEMA,
                "kind": "work-lease-id",
                "domain_id": domain,
                "task_id": task,
                "worker_id": worker,
                "generation": generation,
                "issued_at": observed,
                "expires_at": observed + ttl,
            }
            lease = WorkLease(
                lease_id=_digest(lease_payload),
                task_id=task,
                worker_id=worker,
                domain_id=domain,
                fence=fence,
                issued_at=observed,
                expires_at=observed + ttl,
            )
            self._generations[domain] = generation
            self._leases[domain] = lease
            return lease

    def assert_fence(self, lease: WorkLease, *, now: float) -> WorkLease:
        if not isinstance(lease, WorkLease):
            raise MultiAgentOrchestrationError("lease must be WorkLease")
        observed = _finite_number(now, "now")
        with self._lock:
            self.require(lease.domain_id)
            current = self._live_lease(lease.domain_id, observed)
            if current is None:
                raise MultiAgentOrchestrationError(
                    "mutation lease is absent or expired"
                )
            generation = self._generations.get(lease.domain_id, 0)
            if lease.fence.generation != generation:
                raise MultiAgentOrchestrationError(
                    "stale fencing token generation"
                )
            if current != lease:
                raise MultiAgentOrchestrationError(
                    "mutation lease no longer owns conflict domain"
                )
            return current

    def release(self, lease: WorkLease, *, now: float) -> None:
        with self._lock:
            self.assert_fence(lease, now=now)
            self._leases.pop(lease.domain_id, None)

    def snapshot(self, *, now: float) -> tuple[WorkLease, ...]:
        observed = _finite_number(now, "now")
        with self._lock:
            for domain_id in tuple(self._leases):
                self._live_lease(domain_id, observed)
            return tuple(
                sorted(
                    self._leases.values(),
                    key=lambda item: item.domain_id,
                )
            )


class EvidenceArbitrator:
    """Evidence-first deterministic conflict resolution.

    Agent ballots are intentionally absent. A candidate is eligible only when
    enough independent verifier identities positively bind evidence to its exact
    output digest. A verifier may not verify competing outputs in one decision.
    The strongest unique-verifier set wins only when it is strictly stronger;
    ties fail closed.
    """

    def __init__(
        self,
        *,
        max_candidates: int,
        min_independent_verifiers: int,
    ) -> None:
        self.max_candidates = _positive_int(max_candidates, "max_candidates")
        self.min_independent_verifiers = _positive_int(
            min_independent_verifiers,
            "min_independent_verifiers",
        )

    def resolve(
        self,
        candidates: Sequence[ArbitrationCandidate],
    ) -> ArbitrationDecision:
        if not isinstance(candidates, Sequence):
            raise MultiAgentOrchestrationError(
                "candidates must be a sequence"
            )
        if len(candidates) < 2:
            raise MultiAgentOrchestrationError(
                "arbitration requires at least two candidates"
            )
        if len(candidates) > self.max_candidates:
            raise MultiAgentOrchestrationError(
                "arbitration candidate fanout exceeds policy"
            )

        by_id: dict[str, ArbitrationCandidate] = {}
        verifier_subjects: dict[str, set[str]] = {}
        for candidate in candidates:
            if not isinstance(candidate, ArbitrationCandidate):
                raise MultiAgentOrchestrationError(
                    "candidates must contain ArbitrationCandidate values"
                )
            if candidate.candidate_id in by_id:
                raise MultiAgentOrchestrationError(
                    "duplicate arbitration candidate id"
                )
            by_id[candidate.candidate_id] = candidate
            for claim in candidate.claims:
                if claim.verified:
                    verifier_subjects.setdefault(
                        claim.verifier_id,
                        set(),
                    ).add(candidate.output_digest)

        ambiguous = sorted(
            verifier
            for verifier, subjects in verifier_subjects.items()
            if len(subjects) > 1
        )
        counts = tuple(
            sorted(
                (
                    candidate.candidate_id,
                    len(candidate.verified_verifiers),
                )
                for candidate in by_id.values()
            )
        )
        candidate_ids = tuple(sorted(by_id))
        if ambiguous:
            return self._decision(
                status=ArbitrationStatus.UNRESOLVED,
                candidates=by_id,
                candidate_ids=candidate_ids,
                selected=None,
                counts=counts,
                evidence_refs=(),
                reason="verifier-bound-conflicting-outputs",
            )

        eligible = [
            candidate
            for candidate in by_id.values()
            if len(candidate.verified_verifiers)
            >= self.min_independent_verifiers
        ]
        if not eligible:
            return self._decision(
                status=ArbitrationStatus.UNRESOLVED,
                candidates=by_id,
                candidate_ids=candidate_ids,
                selected=None,
                counts=counts,
                evidence_refs=(),
                reason="insufficient-independent-verification",
            )

        ranked = sorted(
            eligible,
            key=lambda candidate: (
                -len(candidate.verified_verifiers),
                candidate.candidate_id,
            ),
        )
        winner = ranked[0]
        if (
            len(ranked) > 1
            and len(ranked[1].verified_verifiers)
            == len(winner.verified_verifiers)
        ):
            refs = tuple(
                sorted(
                    {
                        ref
                        for candidate in ranked
                        if len(candidate.verified_verifiers)
                        == len(winner.verified_verifiers)
                        for ref in candidate.evidence_refs
                    }
                )
            )
            return self._decision(
                status=ArbitrationStatus.UNRESOLVED,
                candidates=by_id,
                candidate_ids=candidate_ids,
                selected=None,
                counts=counts,
                evidence_refs=refs,
                reason="verified-evidence-tie",
            )

        return self._decision(
            status=ArbitrationStatus.RESOLVED,
            candidates=by_id,
            candidate_ids=candidate_ids,
            selected=winner.candidate_id,
            counts=counts,
            evidence_refs=winner.evidence_refs,
            reason="independent-verifier-evidence-dominates",
        )

    @staticmethod
    def _decision(
        *,
        status: ArbitrationStatus,
        candidates: Mapping[str, ArbitrationCandidate],
        candidate_ids: tuple[str, ...],
        selected: str | None,
        counts: tuple[tuple[str, int], ...],
        evidence_refs: tuple[str, ...],
        reason: str,
    ) -> ArbitrationDecision:
        candidate_digests = {
            candidate_id: candidates[candidate_id].digest
            for candidate_id in candidate_ids
        }
        decision_digest = _digest(
            {
                "schema": SCHEMA,
                "kind": "arbitration-decision",
                "status": status.value,
                "candidate_digests": candidate_digests,
                "selected_candidate_id": selected,
                "verified_counts": [list(item) for item in counts],
                "evidence_refs": list(evidence_refs),
                "reason": reason,
            }
        )
        return ArbitrationDecision(
            status=status,
            candidate_ids=candidate_ids,
            selected_candidate_id=selected,
            verified_counts=counts,
            evidence_refs=evidence_refs,
            reason=reason,
            decision_digest=decision_digest,
        )


class MultiAgentOrchestrator:
    """Composition boundary for bounded handoff, mutation fencing and evidence."""

    def __init__(
        self,
        *,
        policy: BoundedOrchestrationPolicy | None = None,
        conflicts: ConflictDomainRegistry | None = None,
    ) -> None:
        self.policy = policy or BoundedOrchestrationPolicy()
        self.conflicts = conflicts or ConflictDomainRegistry()
        self.arbitrator = EvidenceArbitrator(
            max_candidates=self.policy.max_arbitration_candidates,
            min_independent_verifiers=(
                self.policy.min_independent_verifiers
            ),
        )

    def bind_handoffs(
        self,
        envelopes: Sequence[TaskEnvelope],
        *,
        conflict_domains_by_task: Mapping[str, Sequence[str]],
    ) -> tuple[AgentHandoff, ...]:
        if len(envelopes) > self.policy.max_fanout:
            raise MultiAgentOrchestrationError(
                "handoff fanout exceeds bounded policy"
            )
        seen: set[str] = set()
        bound: list[AgentHandoff] = []
        for envelope in envelopes:
            if envelope.task_id in seen:
                raise MultiAgentOrchestrationError(
                    "duplicate task in handoff fanout"
                )
            seen.add(envelope.task_id)
            domains = conflict_domains_by_task.get(envelope.task_id)
            if domains is None:
                raise MultiAgentOrchestrationError(
                    "handoff is missing conflict-domain assignment"
                )
            handoff = AgentHandoff.from_envelope(
                envelope,
                conflict_domains=domains,
                max_conflict_domains=(
                    self.policy.max_conflict_domains_per_task
                ),
            )
            for domain_id in handoff.conflict_domains:
                self.conflicts.require(domain_id)
            bound.append(handoff)
        return tuple(sorted(bound, key=lambda item: item.task_id))

    def acquire_mutation(
        self,
        handoff: AgentHandoff,
        domain_id: str,
        *,
        ttl_s: float,
        now: float,
    ) -> WorkLease:
        if not isinstance(handoff, AgentHandoff):
            raise MultiAgentOrchestrationError(
                "handoff must be AgentHandoff"
            )
        domain = _token(domain_id, "domain_id")
        if domain not in handoff.conflict_domains:
            raise MultiAgentOrchestrationError(
                "handoff does not authorize requested conflict domain"
            )
        return self.conflicts.acquire(
            domain,
            task_id=handoff.task_id,
            worker_id=handoff.assignee_id,
            ttl_s=ttl_s,
            now=now,
        )

    def require_mutation_authority(
        self,
        lease: WorkLease,
        *,
        now: float,
    ) -> WorkLease:
        return self.conflicts.assert_fence(lease, now=now)

    def record_conflict(
        self,
        *,
        domain_id: str,
        task_id: str,
        candidates: Sequence[ArbitrationCandidate],
    ) -> ConflictRecord:
        self.conflicts.require(domain_id)
        decision = self.arbitrator.resolve(candidates)
        return ConflictRecord(
            domain_id=domain_id,
            task_id=task_id,
            candidate_ids=decision.candidate_ids,
            selected_candidate_id=decision.selected_candidate_id,
            arbitration_digest=decision.decision_digest,
        )


__all__ = [
    "SCHEMA",
    "AgentHandoff",
    "ArbitrationCandidate",
    "ArbitrationDecision",
    "ArbitrationStatus",
    "BoundedOrchestrationPolicy",
    "ConflictDomain",
    "ConflictDomainBusy",
    "ConflictDomainRegistry",
    "ConflictRecord",
    "EvidenceArbitrator",
    "EvidenceClaim",
    "FencingToken",
    "MultiAgentOrchestrationError",
    "MultiAgentOrchestrator",
    "WorkLease",
]
