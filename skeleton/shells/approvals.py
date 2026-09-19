"""Bounded execution approvals for explicitly gated shell actions."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class ExecutionApproval:
    approval_id: str
    principal: str
    command: str
    fingerprint: str
    approved_by: str
    created_at: float
    expires_at: float
    consumed: bool = False


class ApprovalError(RuntimeError):
    pass


class ApprovalRegistry:
    def __init__(
        self,
        *,
        max_approvals: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_approvals = max_approvals
        self._clock = clock
        self._items: dict[str, ExecutionApproval] = {}
        self._lock = threading.RLock()
        self._serial = 0

    def _prune(self) -> None:
        now = self._clock()
        for key in [
            key for key, value in self._items.items()
            if value.expires_at <= now or value.consumed
        ]:
            del self._items[key]

    def approve(
        self,
        *,
        principal: str,
        command: str,
        fingerprint: str,
        approved_by: str,
        ttl_seconds: float = 300.0,
    ) -> ExecutionApproval:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if not all((principal, command, fingerprint, approved_by)):
            raise ValueError("approval identity fields are required")
        with self._lock:
            self._prune()
            if len(self._items) >= self.max_approvals:
                raise ApprovalError("approval capacity exhausted")
            self._serial += 1
            now = self._clock()
            raw = f"{principal}:{command}:{fingerprint}:{approved_by}:{self._serial}:{now}"
            approval_id = hashlib.sha256(raw.encode()).hexdigest()[:32]
            approval = ExecutionApproval(
                approval_id,
                principal,
                command,
                fingerprint,
                approved_by,
                now,
                now + ttl_seconds,
            )
            self._items[approval_id] = approval
            return approval

    def require(
        self,
        approval: ExecutionApproval,
        *,
        principal: str,
        command: str,
        fingerprint: str,
    ) -> ExecutionApproval:
        with self._lock:
            self._prune()
            current = self._items.get(approval.approval_id)
            if current != approval:
                raise ApprovalError("approval is stale, consumed, or expired")
            if (
                current.principal != principal
                or current.command != command
                or current.fingerprint != fingerprint
            ):
                raise ApprovalError("approval does not match execution")
            return current

    def consume(
        self,
        approval: ExecutionApproval,
        *,
        principal: str,
        command: str,
        fingerprint: str,
    ) -> ExecutionApproval:
        current = self.require(
            approval,
            principal=principal,
            command=command,
            fingerprint=fingerprint,
        )
        with self._lock:
            consumed = ExecutionApproval(
                current.approval_id,
                current.principal,
                current.command,
                current.fingerprint,
                current.approved_by,
                current.created_at,
                current.expires_at,
                True,
            )
            self._items[current.approval_id] = consumed
            return consumed

    def snapshot(self) -> tuple[ExecutionApproval, ...]:
        with self._lock:
            self._prune()
            return tuple(self._items[key] for key in sorted(self._items))
