"""Explicit approval/change-control records for shell policy and plan changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping


class ChangeState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    SUPERSEDED = "superseded"


@dataclass(frozen=True)
class ChangeRequest:
    change_id: str
    kind: str
    target: str
    summary: str
    payload_digest: str
    state: ChangeState
    proposed_by: str
    proposed_at: float
    approvals: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.change_id or len(self.change_id) > 128:
            raise ValueError("invalid change_id")
        if not self.kind or len(self.kind) > 128:
            raise ValueError("invalid change kind")
        if not self.target or len(self.target) > 256:
            raise ValueError("invalid change target")
        if not self.proposed_by or len(self.proposed_by) > 256:
            raise ValueError("invalid proposer")
        metadata = dict(self.metadata)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))


class ChangeControl:
    def __init__(
        self,
        *,
        required_approvals: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if required_approvals <= 0:
            raise ValueError("required_approvals must be positive")
        self.required_approvals = required_approvals
        self._clock = clock
        self._items: dict[str, ChangeRequest] = {}
        self._serial = 0
        self._lock = threading.RLock()

    def propose(
        self,
        *,
        kind: str,
        target: str,
        summary: str,
        payload: Mapping[str, object],
        proposed_by: str,
        metadata: Mapping[str, str] | None = None,
    ) -> ChangeRequest:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        digest = hashlib.sha256(raw).hexdigest()
        with self._lock:
            self._serial += 1
            change_id = hashlib.sha256(
                f"{kind}:{target}:{digest}:{self._serial}:{self._clock()}".encode()
            ).hexdigest()[:32]
            item = ChangeRequest(
                change_id,
                kind,
                target,
                summary[:1024],
                digest,
                ChangeState.PROPOSED,
                proposed_by,
                self._clock(),
                metadata=metadata or {},
            )
            self._items[change_id] = item
            return item

    def approve(self, change_id: str, approver: str) -> ChangeRequest:
        if not approver or len(approver) > 256:
            raise ValueError("invalid approver")
        with self._lock:
            current = self._items[change_id]
            if current.state not in {ChangeState.PROPOSED, ChangeState.APPROVED}:
                raise RuntimeError("change cannot be approved from current state")
            approvals = tuple(sorted(set(current.approvals) | {approver}))
            state = (
                ChangeState.APPROVED
                if len(approvals) >= self.required_approvals
                else ChangeState.PROPOSED
            )
            updated = ChangeRequest(
                current.change_id,
                current.kind,
                current.target,
                current.summary,
                current.payload_digest,
                state,
                current.proposed_by,
                current.proposed_at,
                approvals,
                current.metadata,
            )
            self._items[change_id] = updated
            return updated

    def reject(self, change_id: str) -> ChangeRequest:
        with self._lock:
            current = self._items[change_id]
            if current.state not in {ChangeState.PROPOSED, ChangeState.APPROVED}:
                raise RuntimeError("change cannot be rejected from current state")
            updated = ChangeRequest(
                current.change_id,
                current.kind,
                current.target,
                current.summary,
                current.payload_digest,
                ChangeState.REJECTED,
                current.proposed_by,
                current.proposed_at,
                current.approvals,
                current.metadata,
            )
            self._items[change_id] = updated
            return updated

    def applied(self, change_id: str) -> ChangeRequest:
        with self._lock:
            current = self._items[change_id]
            if current.state is not ChangeState.APPROVED:
                raise RuntimeError("only approved changes may be marked applied")
            updated = ChangeRequest(
                current.change_id,
                current.kind,
                current.target,
                current.summary,
                current.payload_digest,
                ChangeState.APPLIED,
                current.proposed_by,
                current.proposed_at,
                current.approvals,
                current.metadata,
            )
            self._items[change_id] = updated
            return updated

    def get(self, change_id: str) -> ChangeRequest:
        with self._lock:
            return self._items[change_id]

    def snapshot(self) -> tuple[ChangeRequest, ...]:
        with self._lock:
            return tuple(self._items[key] for key in sorted(self._items))
