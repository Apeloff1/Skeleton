"""Distributed fenced quorum approval registry for multi-worker AI shell use."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import secrets
import time
from typing import Callable, Mapping

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.quorum import (
    QuorumApproval,
    QuorumApprovalError,
    QuorumPolicy,
    QuorumState,
    QuorumVote,
    QuorumVoteDecision,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


class DistributedAIQuorumApprovalRegistry:
    """CAS-coordinate quorum votes and single-use consumption across workers."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-quorum",
        max_cas_retries: int = 16,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid distributed quorum namespace")
        if max_cas_retries <= 0:
            raise ValueError("max_cas_retries must be positive")
        self.backend = backend
        self.namespace = namespace
        self.max_cas_retries = max_cas_retries
        self._clock = clock

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
        if len(intent_fingerprint) != 64 or len(proposal_fingerprint) != 64:
            raise ValueError("quorum fingerprints must be SHA-256 hex")
        policy = policy or QuorumPolicy()
        now = self._clock()
        for _ in range(self.max_cas_retries):
            nonce = secrets.token_hex(16)
            seed = (
                f"{principal}:{intent_fingerprint}:{proposal_fingerprint}:"
                f"{nonce}:{now}"
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
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    quorum_id,
                    item,
                )
                return item
            except DistributedStateConflict:
                continue
        raise QuorumApprovalError("unable to allocate unique quorum approval")

    def _record(self, quorum_id: str):
        record = self.backend.get(self.namespace, quorum_id)
        if record is None or not isinstance(record.value, QuorumApproval):
            raise QuorumApprovalError("quorum approval is missing")
        return record

    def get(self, quorum_id: str) -> QuorumApproval:
        return self._record(quorum_id).value

    def vote(
        self,
        quorum: QuorumApproval,
        *,
        approver: str,
        decision: QuorumVoteDecision,
        reason: str = "",
    ) -> QuorumApproval:
        for _ in range(self.max_cas_retries):
            record = self._record(quorum.quorum_id)
            current = record.value
            if current.principal != quorum.principal:
                raise QuorumApprovalError("quorum principal binding mismatch")
            if current.intent_fingerprint != quorum.intent_fingerprint:
                raise QuorumApprovalError("quorum intent binding mismatch")
            if current.proposal_fingerprint != quorum.proposal_fingerprint:
                raise QuorumApprovalError("quorum proposal binding mismatch")
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
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    current.quorum_id,
                    expected_revision=record.revision,
                    value=updated,
                )
                return stored.value
            except DistributedStateConflict:
                continue
        raise QuorumApprovalError("quorum vote CAS retry budget exhausted")

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
        current = self.get(quorum.quorum_id)
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
        for _ in range(self.max_cas_retries):
            record = self._record(quorum.quorum_id)
            current = record.value
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
            consumed = replace(current, consumed=True)
            try:
                stored = self.backend.compare_and_swap(
                    self.namespace,
                    current.quorum_id,
                    expected_revision=record.revision,
                    value=consumed,
                )
                return stored.value
            except DistributedStateConflict:
                continue
        raise QuorumApprovalError("quorum consume CAS retry budget exhausted")
