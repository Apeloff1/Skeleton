"""Plan-level approvals bound to exact AI intent and proposal fingerprints."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class AIPlanApproval:
    approval_id: str
    principal: str
    intent_fingerprint: str
    proposal_fingerprint: str
    approved_by: str
    created_at: float
    expires_at: float
    consumed: bool = False


class AIApprovalError(RuntimeError):
    pass


class AIApprovalRegistry:
    def __init__(
        self,
        *,
        max_approvals: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_approvals <= 0:
            raise ValueError("max_approvals must be positive")
        self.max_approvals = max_approvals
        self._clock = clock
        self._serial = 0
        self._items: dict[str, AIPlanApproval] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = self._clock()
        for key in [
            key
            for key, item in self._items.items()
            if item.expires_at <= now or item.consumed
        ]:
            del self._items[key]

    def approve(
        self,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
        approved_by: str,
        ttl_seconds: float = 300.0,
    ) -> AIPlanApproval:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if not principal or not approved_by:
            raise ValueError("principal and approver are required")
        if len(intent_fingerprint) != 64 or len(proposal_fingerprint) != 64:
            raise ValueError("approval fingerprints must be SHA-256 hex")
        with self._lock:
            self._prune()
            if len(self._items) >= self.max_approvals:
                raise AIApprovalError("AI approval capacity exhausted")
            self._serial += 1
            now = self._clock()
            raw = (
                f"{principal}:{intent_fingerprint}:{proposal_fingerprint}:"
                f"{approved_by}:{self._serial}:{now}"
            )
            approval_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
            item = AIPlanApproval(
                approval_id,
                principal,
                intent_fingerprint,
                proposal_fingerprint,
                approved_by,
                now,
                now + ttl_seconds,
            )
            self._items[approval_id] = item
            return item

    def require(
        self,
        approval: AIPlanApproval,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
    ) -> AIPlanApproval:
        with self._lock:
            self._prune()
            current = self._items.get(approval.approval_id)
            if current != approval:
                raise AIApprovalError("AI approval is stale, expired, or consumed")
            if current.principal != principal:
                raise AIApprovalError("AI approval principal mismatch")
            if current.intent_fingerprint != intent_fingerprint:
                raise AIApprovalError("AI approval intent mismatch")
            if current.proposal_fingerprint != proposal_fingerprint:
                raise AIApprovalError("AI approval proposal mismatch")
            return current

    def consume(
        self,
        approval: AIPlanApproval,
        *,
        principal: str,
        intent_fingerprint: str,
        proposal_fingerprint: str,
    ) -> AIPlanApproval:
        current = self.require(
            approval,
            principal=principal,
            intent_fingerprint=intent_fingerprint,
            proposal_fingerprint=proposal_fingerprint,
        )
        with self._lock:
            consumed = AIPlanApproval(
                current.approval_id,
                current.principal,
                current.intent_fingerprint,
                current.proposal_fingerprint,
                current.approved_by,
                current.created_at,
                current.expires_at,
                True,
            )
            self._items[current.approval_id] = consumed
            return consumed
