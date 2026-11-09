"""Vault quorum approvals — N-of-M operator sign-off for sensitive actions.

Rotating a master key or opening a sealed vault shouldn't be a solo
decision under dual-control policy. The gate collects approvals per
action-id and releases when the threshold is reached.

Hardening (all opt-in, defaults stay backward compatible):

- ``operators``: an allow-list of custodians; approvals from anyone else
  are rejected, and the threshold may not exceed the roster size.
- ``proposer``: the operator who proposed an action may not approve it
  (four-eyes principle).
- ``ttl_s``: proposals expire; stale approvals never release an action.
- Re-proposing a pending action is idempotent — it never wipes approvals
  already collected.
- ``check`` consumes a released approval exactly once.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Optional, Set, Tuple

from skeleton.kernel.errors import VaultError


class QuorumError(VaultError):
    code = "VLT.QUORUM"


@dataclass
class QuorumRequest:
    action_id: str
    threshold: int
    approvals: Set[str] = field(default_factory=set)
    proposer: Optional[str] = None
    created_at: float = 0.0
    expires_at: Optional[float] = None

    @property
    def remaining(self) -> int:
        return max(0, self.threshold - len(self.approvals))


class QuorumGate:
    """Collect operator approvals until threshold."""

    def __init__(
        self,
        *,
        threshold: int,
        operators: Optional[Iterable[str]] = None,
        ttl_s: Optional[float] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if threshold <= 0:
            raise QuorumError("threshold must be positive")
        roster = None if operators is None else frozenset(operators)
        if roster is not None and threshold > len(roster):
            raise QuorumError("threshold exceeds operator roster",
                              context={"threshold": threshold, "operators": len(roster)})
        if ttl_s is not None and ttl_s <= 0:
            raise QuorumError("ttl_s must be positive")
        self._threshold = threshold
        self._operators = roster
        self._ttl = ttl_s
        self._now = clock or time.time
        self._requests: Dict[str, QuorumRequest] = {}

    def propose(self, action_id: str, *, proposer: Optional[str] = None) -> QuorumRequest:
        existing = self._live(action_id)
        if existing is not None:
            return existing
        if proposer is not None and self._operators is not None and proposer not in self._operators:
            raise QuorumError("proposer is not a registered operator", context={"operator": proposer})
        now = self._now()
        req = QuorumRequest(
            action_id=action_id,
            threshold=self._threshold,
            proposer=proposer,
            created_at=now,
            expires_at=None if self._ttl is None else now + self._ttl,
        )
        self._requests[action_id] = req
        return req

    def approve(self, action_id: str, operator: str) -> QuorumRequest:
        req = self._live(action_id)
        if req is None:
            raise QuorumError("unknown or expired action", context={"action": action_id})
        if self._operators is not None and operator not in self._operators:
            raise QuorumError("operator is not on the roster", context={"operator": operator})
        if req.proposer is not None and operator == req.proposer:
            raise QuorumError("proposer may not approve their own action",
                              context={"action": action_id, "operator": operator})
        req.approvals.add(operator)
        return req

    def revoke(self, action_id: str, operator: str) -> None:
        req = self._live(action_id)
        if req is not None:
            req.approvals.discard(operator)

    def check(self, action_id: str) -> bool:
        if action_id not in self._requests:
            raise QuorumError("unknown action", context={"action": action_id})
        req = self._live(action_id)
        if req is None or len(req.approvals) < req.threshold:
            return False
        del self._requests[action_id]
        return True

    def status(self, action_id: str) -> Dict[str, object]:
        req = self._live(action_id)
        if req is None:
            raise QuorumError("unknown or expired action", context={"action": action_id})
        return {
            "action_id": req.action_id,
            "threshold": req.threshold,
            "approvals": sorted(req.approvals),
            "remaining": req.remaining,
            "expires_at": req.expires_at,
        }

    def required(self) -> int:
        return self._threshold

    def pending(self) -> Tuple[str, ...]:
        for action_id in list(self._requests):
            self._live(action_id)
        return tuple(sorted(self._requests))

    def _live(self, action_id: str) -> Optional[QuorumRequest]:
        req = self._requests.get(action_id)
        if req is None:
            return None
        if req.expires_at is not None and self._now() > req.expires_at:
            del self._requests[action_id]
            return None
        return req


__all__ = ["QuorumError", "QuorumGate", "QuorumRequest"]
