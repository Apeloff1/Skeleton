"""Bounded break-glass execution and one-shot undo for P1 AC-19."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import hmac
import time
from typing import Callable

from skeleton.shells.ai.approval_quorum import QuorumApproval


class BreakGlassError(PermissionError):
    """Emergency execution failed a dual-control or replay boundary."""


@dataclass(frozen=True, slots=True)
class BreakGlassGrant:
    grant_id: str
    principal: str
    action_digest: str
    approval_digest: str
    issued_at: float
    expires_at: float
    undo_token: str

    def __post_init__(self) -> None:
        for field in ("grant_id", "action_digest", "approval_digest", "undo_token"):
            value = getattr(self, field)
            if len(value) != 64:
                raise ValueError(f"{field} must be SHA-256 hex")
        if self.expires_at <= self.issued_at:
            raise ValueError("grant expiry must follow issue time")


@dataclass(frozen=True, slots=True)
class UndoReceipt:
    grant_id: str
    action_digest: str
    undone_at: float
    receipt_digest: str


class BreakGlassController:
    """Emergency lane requiring approved quorum and bounded operator use."""

    def __init__(
        self,
        *,
        max_grants_per_window: int = 2,
        window_seconds: float = 900.0,
        max_ttl_seconds: float = 300.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if (
            isinstance(max_grants_per_window, bool)
            or not isinstance(max_grants_per_window, int)
            or max_grants_per_window < 1
        ):
            raise ValueError("max_grants_per_window must be positive integer")
        if window_seconds <= 0 or max_ttl_seconds <= 0:
            raise ValueError("break-glass time bounds must be positive")
        self._max_grants = max_grants_per_window
        self._window = float(window_seconds)
        self._max_ttl = float(max_ttl_seconds)
        self._clock = clock
        self._issued: deque[float] = deque()
        self._grants: dict[str, BreakGlassGrant] = {}
        self._undone: set[str] = set()

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        while self._issued and self._issued[0] <= cutoff:
            self._issued.popleft()

    def issue(
        self,
        *,
        approval: QuorumApproval,
        principal: str,
        action_digest: str,
        reason: str,
        ttl_seconds: float = 120.0,
    ) -> BreakGlassGrant:
        now = float(self._clock())
        if not isinstance(approval, QuorumApproval):
            raise TypeError("approval must be QuorumApproval")
        if not reason.strip() or len(reason) > 2048:
            raise BreakGlassError("break-glass reason is required")
        if len(action_digest) != 64:
            raise BreakGlassError("action_digest must be SHA-256 hex")
        try:
            bytes.fromhex(action_digest)
        except ValueError as exc:
            raise BreakGlassError("action_digest must be hexadecimal") from exc
        if ttl_seconds <= 0 or ttl_seconds > self._max_ttl:
            raise BreakGlassError("break-glass TTL out of range")
        if approval.consumed:
            raise BreakGlassError("approval already consumed")
        if approval.expires_at <= now:
            raise BreakGlassError("approval expired")
        if approval.policy_rejected or not approval.complete:
            raise BreakGlassError("approval quorum is not complete")
        if approval.principal != principal:
            raise BreakGlassError("approval principal mismatch")
        if not hmac.compare_digest(approval.proposal_fingerprint, action_digest):
            raise BreakGlassError("approval action mismatch")

        self._prune(now)
        if len(self._issued) >= self._max_grants:
            raise BreakGlassError("break-glass approval fatigue budget exhausted")

        material = (
            f"{approval.digest}|{principal}|{action_digest}|{reason}|{now}|"
            f"{len(self._grants)}"
        ).encode()
        grant_id = hashlib.sha256(b"grant|" + material).hexdigest()
        undo_token = hashlib.sha256(b"undo|" + material).hexdigest()
        grant = BreakGlassGrant(
            grant_id=grant_id,
            principal=principal,
            action_digest=action_digest,
            approval_digest=approval.digest,
            issued_at=now,
            expires_at=now + ttl_seconds,
            undo_token=undo_token,
        )
        self._grants[grant_id] = grant
        self._issued.append(now)
        return grant

    def authorize(
        self,
        grant: BreakGlassGrant,
        *,
        principal: str,
        action_digest: str,
    ) -> None:
        current = self._grants.get(grant.grant_id)
        if current is None or current != grant:
            raise BreakGlassError("unknown or stale break-glass grant")
        if grant.grant_id in self._undone:
            raise BreakGlassError("break-glass grant was undone")
        if grant.expires_at <= self._clock():
            raise BreakGlassError("break-glass grant expired")
        if grant.principal != principal:
            raise BreakGlassError("break-glass principal mismatch")
        if not hmac.compare_digest(grant.action_digest, action_digest):
            raise BreakGlassError("break-glass action mismatch")

    def undo(
        self,
        grant: BreakGlassGrant,
        *,
        undo_token: str,
    ) -> UndoReceipt:
        current = self._grants.get(grant.grant_id)
        if current is None or current != grant:
            raise BreakGlassError("unknown or stale break-glass grant")
        if grant.grant_id in self._undone:
            raise BreakGlassError("break-glass undo already consumed")
        if not hmac.compare_digest(grant.undo_token, undo_token):
            raise BreakGlassError("break-glass undo token mismatch")
        now = float(self._clock())
        self._undone.add(grant.grant_id)
        digest = hashlib.sha256(
            f"{grant.grant_id}|{grant.action_digest}|{now}".encode()
        ).hexdigest()
        return UndoReceipt(
            grant_id=grant.grant_id,
            action_digest=grant.action_digest,
            undone_at=now,
            receipt_digest=digest,
        )


__all__ = [
    "BreakGlassController",
    "BreakGlassError",
    "BreakGlassGrant",
    "UndoReceipt",
]
