"""Dual-control approval primitives for high-assurance AI shell execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping


class QuorumState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONSUMED = "consumed"
    EXPIRED = "expired"


class QuorumVoteDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True)
class QuorumPolicy:
    required_approvals: int = 2
    max_approvers: int = 8
    reject_is_terminal: bool = True
    require_distinct_approvers: bool = True

    def __post_init__(self) -> None:
        if self.required_approvals < 2:
            raise ValueError("quorum requires at least two approvals")
        if self.max_approvers < self.required_approvals:
            raise ValueError("max_approvers below required approvals")


@dataclass(frozen=True)
class QuorumVote:
    approver: str
    decision: QuorumVoteDecision
    observed_at: float
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.approver or len(self.approver) > 256:
            raise ValueError("invalid quorum approver")
        object.__setattr__(self, "decision", QuorumVoteDecision(self.decision))
        if self.observed_at < 0:
            raise ValueError("quorum vote time may not be negative")
        if len(self.reason) > 2048:
            raise ValueError("quorum vote reason too long")

    def to_dict(self) -> dict[str, object]:
        return {
            "approver": self.approver,
            "decision": self.decision.value,
            "observed_at": self.observed_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QuorumApproval:
    quorum_id: str
    principal: str
    intent_fingerprint: str
    proposal_fingerprint: str
    created_at: float
    expires_at: float
    policy: QuorumPolicy
    votes: tuple[QuorumVote, ...] = ()
    consumed: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.quorum_id or len(self.quorum_id) > 128:
            raise ValueError("invalid quorum_id")
        if not self.principal or len(self.principal) > 256:
            raise ValueError("invalid quorum principal")
        if len(self.intent_fingerprint) != 64:
            raise ValueError("quorum intent fingerprint must be SHA-256 hex")
        if len(self.proposal_fingerprint) != 64:
            raise ValueError("quorum proposal fingerprint must be SHA-256 hex")
        if self.expires_at <= self.created_at:
            raise ValueError("quorum expiry must follow creation")
        votes = tuple(self.votes)
        approvers = [item.approver for item in votes]
        if self.policy.require_distinct_approvers and len(approvers) != len(set(approvers)):
            raise ValueError("duplicate quorum approver")
        if len(votes) > self.policy.max_approvers:
            raise ValueError("quorum vote capacity exceeded")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many quorum metadata fields")
        object.__setattr__(self, "votes", votes)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def state_at(self, now: float) -> QuorumState:
        if self.consumed:
            return QuorumState.CONSUMED
        if self.expires_at <= now:
            return QuorumState.EXPIRED
        if self.policy.reject_is_terminal and any(
            item.decision is QuorumVoteDecision.REJECT
            for item in self.votes
        ):
            return QuorumState.REJECTED
        approvals = sum(
            item.decision is QuorumVoteDecision.APPROVE
            for item in self.votes
        )
        if approvals >= self.policy.required_approvals:
            return QuorumState.APPROVED
        return QuorumState.PENDING

    @property
    def approvers(self) -> tuple[str, ...]:
        return tuple(
            item.approver
            for item in self.votes
            if item.decision is QuorumVoteDecision.APPROVE
        )

    def to_dict(self, *, now: float | None = None) -> dict[str, object]:
        data = {
            "quorum_id": self.quorum_id,
            "principal": self.principal,
            "intent_fingerprint": self.intent_fingerprint,
            "proposal_fingerprint": self.proposal_fingerprint,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "policy": {
                "required_approvals": self.policy.required_approvals,
                "max_approvers": self.policy.max_approvers,
                "reject_is_terminal": self.policy.reject_is_terminal,
                "require_distinct_approvers": self.policy.require_distinct_approvers,
            },
            "votes": [item.to_dict() for item in self.votes],
            "consumed": self.consumed,
            "metadata": dict(self.metadata),
        }
        if now is not None:
            data["state"] = self.state_at(now).value
        return data


class QuorumApprovalError(RuntimeError):
    pass


class AIQuorumApprovalRegistry:
    """Bounded in-process quorum registry with single-use consumption."""

    def __init__(
        self,
        *,
        max_items: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_items <= 0:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self._clock = clock
        self._serial = 0
        self._items: dict[str, QuorumApproval] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = self._clock()
        for key in [
            key
            for key, item in self._items.items()
            if item.state_at(now) in {
                QuorumState.EXPIRED,
                QuorumState.CONSUMED,
            }
        ]:
            del self._items[key]

    def create(
        self,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
        policy: QuorumPolicy | None = None,
        ttl_seconds: float = 300.0,
        metadata: Mapping[str, str] | None = None,
    ) -> QuorumApproval:
        if ttl_seconds <= 0:
            raise ValueError("quorum ttl_seconds must be positive")
        if not principal:
            raise ValueError("quorum principal is required")
        if len(intent_fingerprint) != 64 or len(proposal_fingerprint) != 64:
            raise ValueError("quorum fingerprints must be SHA-256 hex")
        policy = policy or QuorumPolicy()
        with self._lock:
            self._prune()
            if len(self._items) >= self.max_items:
                raise QuorumApprovalError("quorum registry capacity exhausted")
            self._serial += 1
            now = self._clock()
            seed = (
                f"{principal}:{intent_fingerprint}:{proposal_fingerprint}:"
                f"{self._serial}:{now}"
            ).encode()
            quorum_id = hashlib.sha256(seed).hexdigest()[:32]
            item = QuorumApproval(
                quorum_id,
                principal,
                intent_fingerprint,
                proposal_fingerprint,
                now,
                now + ttl_seconds,
                policy,
                (),
                False,
                metadata or {},
            )
            self._items[quorum_id] = item
            return item

    def get(self, quorum_id: str) -> QuorumApproval:
        with self._lock:
            self._prune()
            try:
                return self._items[quorum_id]
            except KeyError as exc:
                raise QuorumApprovalError(
                    "quorum approval is missing or expired"
                ) from exc

    def vote(
        self,
        quorum: QuorumApproval,
        *,
        approver: str,
        decision: QuorumVoteDecision,
        reason: str = "",
    ) -> QuorumApproval:
        with self._lock:
            current = self.get(quorum.quorum_id)
            if current != quorum:
                raise QuorumApprovalError("quorum approval is stale")
            state = current.state_at(self._clock())
            if state is not QuorumState.PENDING:
                raise QuorumApprovalError(
                    f"quorum approval cannot accept votes in {state.value} state"
                )
            if any(item.approver == approver for item in current.votes):
                raise QuorumApprovalError("approver already voted")
            if len(current.votes) >= current.policy.max_approvers:
                raise QuorumApprovalError("quorum approver capacity exhausted")
            updated = replace(
                current,
                votes=current.votes + (
                    QuorumVote(
                        approver,
                        QuorumVoteDecision(decision),
                        self._clock(),
                        reason,
                    ),
                ),
            )
            self._items[current.quorum_id] = updated
            return updated

    def approve(
        self,
        quorum: QuorumApproval,
        *,
        approver: str,
        reason: str = "",
    ) -> QuorumApproval:
        return self.vote(
            quorum,
            approver=approver,
            decision=QuorumVoteDecision.APPROVE,
            reason=reason,
        )

    def reject(
        self,
        quorum: QuorumApproval,
        *,
        approver: str,
        reason: str = "",
    ) -> QuorumApproval:
        return self.vote(
            quorum,
            approver=approver,
            decision=QuorumVoteDecision.REJECT,
            reason=reason,
        )

    def require(
        self,
        quorum: QuorumApproval,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
    ) -> QuorumApproval:
        with self._lock:
            current = self.get(quorum.quorum_id)
            if current != quorum:
                raise QuorumApprovalError("quorum approval is stale")
            if current.principal != principal:
                raise QuorumApprovalError("quorum principal mismatch")
            if current.intent_fingerprint != intent_fingerprint:
                raise QuorumApprovalError("quorum intent mismatch")
            if current.proposal_fingerprint != proposal_fingerprint:
                raise QuorumApprovalError("quorum proposal mismatch")
            state = current.state_at(self._clock())
            if state is not QuorumState.APPROVED:
                raise QuorumApprovalError(
                    f"quorum approval is not approved: {state.value}"
                )
            return current

    def consume(
        self,
        quorum: QuorumApproval,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
    ) -> QuorumApproval:
        with self._lock:
            current = self.require(
                quorum,
                principal=principal,
                intent_fingerprint=intent_fingerprint,
                proposal_fingerprint=proposal_fingerprint,
            )
            consumed = replace(current, consumed=True)
            self._items[current.quorum_id] = consumed
            return consumed
