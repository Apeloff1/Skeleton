"""Vault quorum approvals — N-of-M operator sign-off for sensitive actions.

Rotating a master key or opening a sealed vault shouldn't be a solo
decision under dual-control policy. The gate collects approvals per
action-id and releases when the threshold is reached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set, Tuple

from skeleton.kernel.errors import VaultError


class QuorumError(VaultError):
    code = "VLT.QUORUM"


@dataclass
class QuorumRequest:
    action_id: str
    threshold: int
    approvals: Set[str] = field(default_factory=set)


class QuorumGate:
    """Collect operator approvals until threshold."""

    def __init__(self, *, threshold: int) -> None:
        if threshold <= 0:
            raise QuorumError("threshold must be positive")
        self._threshold = threshold
        self._requests: Dict[str, QuorumRequest] = {}

    def propose(self, action_id: str) -> QuorumRequest:
        req = QuorumRequest(action_id=action_id, threshold=self._threshold)
        self._requests[action_id] = req
        return req

    def approve(self, action_id: str, operator: str) -> None:
        req = self._requests.get(action_id)
        if req is None:
            raise QuorumError("unknown action", context={"action": action_id})
        req.approvals.add(operator)

    def check(self, action_id: str) -> bool:
        req = self._requests.get(action_id)
        if req is None:
            raise QuorumError("unknown action", context={"action": action_id})
        if len(req.approvals) < req.threshold:
            return False
        del self._requests[action_id]
        return True

    def required(self) -> int:
        return self._threshold

    def pending(self) -> Tuple[str, ...]:
        return tuple(sorted(self._requests))
