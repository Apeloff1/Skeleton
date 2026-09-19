"""Distributed dual-control approvals for high-assurance AI shell plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import secrets
import time
from types import MappingProxyType
from typing import Callable, Mapping

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.store_protocol import VersionedStateBackend


class QuorumVoteDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class QuorumApprovalState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSUMED = "consumed"
    EXPIRED = "expired"


@dataclass(frozen=True)
class QuorumApprovalPolicy:
    required_votes: int = 2
    max_votes: int = 16
    forbid_principal_self_approval: bool = True
    allowed_roles: frozenset[str] = frozenset()
    max_ttl_seconds: float = 900.0

    def __post_init__(self) -> None:
        if self.required_votes < 2:
            raise ValueError("dual-control quorum requires at least two votes")
        if self.max_votes < self.required_votes:
            raise ValueError("max_votes must cover required_votes")
        if self.max_votes > 128:
            raise ValueError("max_votes too large")
        if self.max_ttl_seconds <= 0:
            raise ValueError("quorum approval maximum TTL must be positive")
        roles = frozenset(self.allowed_roles)
        if any(not role or len(role) > 128 for role in roles):
            raise ValueError("invalid quorum approval role")
        object.__setattr__(self, "allowed_roles", roles)


@dataclass(frozen=True)
class QuorumVote:
    approver: str
    role: str
    voted_at: float
    decision: QuorumVoteDecision = QuorumVoteDecision.APPROVE
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.approver or len(self.approver) > 256:
            raise ValueError("invalid quorum approver")
        if len(self.role) > 128:
            raise ValueError("quorum role too long")
        if self.voted_at < 0:
            raise ValueError("quorum vote time may not be negative")
        object.__setattr__(self, "decision", QuorumVoteDecision(self.decision))
        if len(self.reason) > 2048:
            raise ValueError("quorum vote reason too long")

    def to_dict(self) -> dict[str, object]:
        return {
            "approver": self.approver,
            "role": self.role,
            "voted_at": self.voted_at,
            "decision": self.decision.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QuorumApproval:
    approval_id: str
    principal: str
    intent_fingerprint: str
    proposal_fingerprint: str
    required_votes: int
    votes: tuple[QuorumVote, ...]
    created_at: float
    expires_at: float
    consumed: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.approval_id or len(self.approval_id) > 128:
            raise ValueError("invalid quorum approval_id")
        if not self.principal or len(self.principal) > 256:
            raise ValueError("invalid quorum principal")
        if len(self.intent_fingerprint) != 64:
            raise ValueError("intent_fingerprint must be SHA-256 hex")
        if len(self.proposal_fingerprint) != 64:
            raise ValueError("proposal_fingerprint must be SHA-256 hex")
        if self.required_votes < 2:
            raise ValueError("quorum approval requires at least two votes")
        votes = tuple(self.votes)
        approvers = [item.approver for item in votes]
        if len(approvers) != len(set(approvers)):
            raise ValueError("quorum approval contains duplicate approvers")
        if self.expires_at <= self.created_at:
            raise ValueError("quorum approval expiry invalid")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many quorum approval metadata fields")
        object.__setattr__(self, "votes", votes)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def state_at(self, now: float) -> QuorumApprovalState:
        if self.consumed:
            return QuorumApprovalState.CONSUMED
        if self.expires_at <= now:
            return QuorumApprovalState.EXPIRED
        if self.policy_rejected:
            return QuorumApprovalState.REJECTED
        if self.complete:
            return QuorumApprovalState.APPROVED
        return QuorumApprovalState.PENDING

    @property
    def policy_rejected(self) -> bool:
        return any(item.decision is QuorumVoteDecision.REJECT for item in self.votes)

    @property
    def complete(self) -> bool:
        return (
            not self.policy_rejected
            and sum(item.decision is QuorumVoteDecision.APPROVE for item in self.votes)
            >= self.required_votes
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "principal": self.principal,
            "intent_fingerprint": self.intent_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "required_votes": self.required_votes,
            "votes": [item.to_dict() for item in self.votes],
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "consumed": self.consumed,
            "metadata": dict(self.metadata),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class StoredQuorumApproval:
    revision: int
    approval: QuorumApproval


class QuorumApprovalError(RuntimeError):
    pass


class AIApprovalQuorumStore:
    """Strongly-consistent, distinct-approver quorum over a versioned backend."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        policy: QuorumApprovalPolicy | None = None,
        namespace: str = "shell-ai-approval-quorum",
        max_retries: int = 8,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid quorum namespace")
        if max_retries <= 0:
            raise ValueError("quorum CAS retry budget must be positive")
        self.backend = backend
        self.policy = policy or QuorumApprovalPolicy()
        self.namespace = namespace
        self.max_retries = max_retries
        self._clock = clock

    def _load(self, approval_id: str):
        record = self.backend.get(self.namespace, approval_id)
        if record is None:
            return None
        if not isinstance(record.value, QuorumApproval):
            raise RuntimeError("quorum approval backend value type mismatch")
        return record

    def open(
        self,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
        ttl_seconds: float = 300.0,
        metadata: Mapping[str, str] | None = None,
    ) -> StoredQuorumApproval:
        if not principal or len(principal) > 256:
            raise ValueError("invalid quorum principal")
        if len(intent_fingerprint) != 64 or len(proposal_fingerprint) != 64:
            raise ValueError("quorum fingerprints must be SHA-256 hex")
        if ttl_seconds <= 0 or ttl_seconds > self.policy.max_ttl_seconds:
            raise ValueError("quorum approval TTL out of range")
        now = self._clock()
        nonce = secrets.token_hex(16)
        raw = (
            f"{principal}:{intent_fingerprint}:{proposal_fingerprint}:"
            f"{now}:{nonce}"
        ).encode()
        approval_id = hashlib.sha256(raw).hexdigest()[:32]
        approval = QuorumApproval(
            approval_id,
            principal,
            intent_fingerprint,
            proposal_fingerprint,
            self.policy.required_votes,
            (),
            now,
            now + ttl_seconds,
            False,
            metadata or {},
        )
        record = self.backend.put_if_absent(
            self.namespace,
            approval_id,
            approval,
        )
        return StoredQuorumApproval(record.revision, approval)

    def current(self, approval_id: str) -> StoredQuorumApproval | None:
        record = self._load(approval_id)
        if record is None:
            return None
        return StoredQuorumApproval(record.revision, record.value)

    def _require_live(self, approval: QuorumApproval) -> None:
        state = approval.state_at(self._clock())
        if state is QuorumApprovalState.CONSUMED:
            raise QuorumApprovalError("quorum approval already consumed")
        if state is QuorumApprovalState.EXPIRED:
            raise QuorumApprovalError("quorum approval expired")
        if state is QuorumApprovalState.REJECTED:
            raise QuorumApprovalError("quorum approval was rejected")

    def vote(
        self,
        approval_id: str,
        *,
        approver: str,
        role: str = "",
        decision: QuorumVoteDecision = QuorumVoteDecision.APPROVE,
        reason: str = "",
    ) -> StoredQuorumApproval:
        if not approver or len(approver) > 256:
            raise ValueError("invalid quorum approver")
        if len(role) > 128:
            raise ValueError("quorum role too long")
        decision = QuorumVoteDecision(decision)
        if len(reason) > 2048:
            raise ValueError("quorum vote reason too long")
        if self.policy.allowed_roles and role not in self.policy.allowed_roles:
            raise QuorumApprovalError("approver role is not allowed")
        for _ in range(self.max_retries):
            record = self._load(approval_id)
            if record is None:
                raise QuorumApprovalError("quorum approval does not exist")
            current = record.value
            self._require_live(current)
            if (
                self.policy.forbid_principal_self_approval
                and approver == current.principal
            ):
                raise QuorumApprovalError("principal may not approve own execution")
            prior = next(
                (item for item in current.votes if item.approver == approver),
                None,
            )
            if prior is not None:
                if prior.role != role:
                    raise QuorumApprovalError(
                        "approver already voted with a different role"
                    )
                if prior.decision is not decision:
                    raise QuorumApprovalError(
                        "approver may not change quorum vote decision"
                    )
                return StoredQuorumApproval(record.revision, current)
            if len(current.votes) >= self.policy.max_votes:
                raise QuorumApprovalError("quorum approval vote capacity exhausted")
            updated = QuorumApproval(
                current.approval_id,
                current.principal,
                current.intent_fingerprint,
                current.proposal_fingerprint,
                current.required_votes,
                current.votes + (
                    QuorumVote(approver, role, self._clock(), decision, reason),
                ),
                current.created_at,
                current.expires_at,
                False,
                current.metadata,
            )
            try:
                result = self.backend.compare_and_swap(
                    self.namespace,
                    approval_id,
                    expected_revision=record.revision,
                    value=updated,
                )
                return StoredQuorumApproval(result.revision, updated)
            except DistributedStateConflict:
                continue
        raise QuorumApprovalError("quorum vote CAS retry budget exhausted")

    def reject(
        self,
        approval_id: str,
        *,
        approver: str,
        role: str = "",
        reason: str = "",
    ) -> StoredQuorumApproval:
        return self.vote(
            approval_id,
            approver=approver,
            role=role,
            decision=QuorumVoteDecision.REJECT,
            reason=reason,
        )

    def require(
        self,
        approval: QuorumApproval,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
    ) -> QuorumApproval:
        record = self._load(approval.approval_id)
        if record is None:
            raise QuorumApprovalError("quorum approval does not exist")
        current = record.value
        self._require_live(current)
        if current.digest != approval.digest:
            raise QuorumApprovalError("quorum approval evidence is stale")
        if current.principal != principal:
            raise QuorumApprovalError("quorum approval principal mismatch")
        if current.intent_fingerprint != intent_fingerprint:
            raise QuorumApprovalError("quorum approval intent mismatch")
        if current.proposal_fingerprint != proposal_fingerprint:
            raise QuorumApprovalError("quorum approval proposal mismatch")
        if current.policy_rejected:
            raise QuorumApprovalError("quorum approval was rejected")
        if not current.complete:
            raise QuorumApprovalError("quorum approval does not have enough votes")
        return current

    def consume(
        self,
        approval: QuorumApproval,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
    ) -> QuorumApproval:
        current = self.require(
            approval,
            principal=principal,
            intent_fingerprint=intent_fingerprint,
            proposal_fingerprint=proposal_fingerprint,
        )
        record = self._load(current.approval_id)
        if record is None:
            raise QuorumApprovalError("quorum approval disappeared")
        if record.value.digest != current.digest:
            raise QuorumApprovalError(
                "quorum approval changed before consumption"
            )
        consumed = QuorumApproval(
            current.approval_id,
            current.principal,
            current.intent_fingerprint,
            current.proposal_fingerprint,
            current.required_votes,
            current.votes,
            current.created_at,
            current.expires_at,
            True,
            current.metadata,
        )
        try:
            self.backend.compare_and_swap(
                self.namespace,
                current.approval_id,
                expected_revision=record.revision,
                value=consumed,
            )
        except DistributedStateConflict as exc:
            raise QuorumApprovalError(
                "quorum approval changed before consumption"
            ) from exc
        return consumed
