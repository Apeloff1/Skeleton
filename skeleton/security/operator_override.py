"""Bounded human override and break-glass recovery controls.

Human recovery authority is intentionally explicit, narrow, time-bounded, and
append-only audited. Destructive actions require a preview receipt, repeated
approvals are rate-limited to resist fatigue, and reversible recovery actions
carry a one-time bounded undo path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Iterable


class OperatorOverrideError(ValueError):
    """Break-glass policy or operator action violates the safety contract."""


def _token(value: str, field: str, *, maximum: int = 192) -> str:
    if not isinstance(value, str):
        raise OperatorOverrideError(f"{field} must be text")
    if (
        not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise OperatorOverrideError(f"invalid {field}")
    return value


def _time(value: float, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise OperatorOverrideError(f"{field} must be finite and non-negative")
    return float(value)


def _digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class AuditEvent:
    sequence: int
    kind: str
    occurred_at: float
    payload_digest: str
    previous_digest: str
    digest: str


@dataclass(frozen=True, slots=True)
class BreakGlassGrant:
    grant_id: str
    operator_id: str
    scopes: tuple[str, ...]
    issued_at: float
    expires_at: float
    max_uses: int
    reason_digest: str


@dataclass(frozen=True, slots=True)
class OverrideAction:
    action: str
    resource: str
    destructive: bool = False
    inverse_action: str | None = None

    @property
    def scope(self) -> str:
        return f"{self.action}:{self.resource}"


@dataclass(frozen=True, slots=True)
class PreviewReceipt:
    grant_id: str
    action_scope: str
    created_at: float
    digest: str


@dataclass(frozen=True, slots=True)
class OverrideReceipt:
    receipt_id: str
    grant_id: str
    operator_id: str
    action_scope: str
    executed_at: float
    preview_digest: str | None
    undo_deadline: float | None
    inverse_action: str | None
    audit_digest: str


class OperatorOverrideController:
    """Least-authority break-glass controller with fatigue and undo protection."""

    def __init__(
        self,
        *,
        max_grant_seconds: float = 900.0,
        preview_ttl_seconds: float = 300.0,
        approval_window_seconds: float = 300.0,
        max_approvals_per_window: int = 3,
        undo_window_seconds: float = 600.0,
    ) -> None:
        for name, value in (
            ("max_grant_seconds", max_grant_seconds),
            ("preview_ttl_seconds", preview_ttl_seconds),
            ("approval_window_seconds", approval_window_seconds),
            ("undo_window_seconds", undo_window_seconds),
        ):
            if _time(value, name) <= 0:
                raise OperatorOverrideError(f"{name} must be positive")
        if (
            isinstance(max_approvals_per_window, bool)
            or not isinstance(max_approvals_per_window, int)
            or max_approvals_per_window < 1
        ):
            raise OperatorOverrideError(
                "max_approvals_per_window must be positive integer"
            )
        self._max_grant_seconds = float(max_grant_seconds)
        self._preview_ttl_seconds = float(preview_ttl_seconds)
        self._approval_window_seconds = float(approval_window_seconds)
        self._max_approvals_per_window = max_approvals_per_window
        self._undo_window_seconds = float(undo_window_seconds)
        self._grants: dict[str, BreakGlassGrant] = {}
        self._grant_uses: dict[str, int] = {}
        self._previews: dict[str, PreviewReceipt] = {}
        self._receipts: dict[str, OverrideReceipt] = {}
        self._undone: set[str] = set()
        self._executions: list[tuple[str, float]] = []
        self._audit: list[AuditEvent] = []

    @staticmethod
    def _scope(action: str, resource: str) -> str:
        action = _token(action, "action", maximum=96)
        resource = _token(resource, "resource")
        if "*" in action or "*" in resource:
            raise OperatorOverrideError("wildcard break-glass scope is forbidden")
        return f"{action}:{resource}"

    def _append_audit(
        self,
        kind: str,
        *,
        occurred_at: float,
        payload: object,
    ) -> AuditEvent:
        kind = _token(kind, "audit kind", maximum=64)
        occurred_at = _time(occurred_at, "occurred_at")
        previous = self._audit[-1].digest if self._audit else "0" * 64
        payload_digest = _digest(payload)
        sequence = len(self._audit) + 1
        digest = _digest(
            {
                "sequence": sequence,
                "kind": kind,
                "occurred_at": occurred_at,
                "payload_digest": payload_digest,
                "previous_digest": previous,
            }
        )
        event = AuditEvent(
            sequence=sequence,
            kind=kind,
            occurred_at=occurred_at,
            payload_digest=payload_digest,
            previous_digest=previous,
            digest=digest,
        )
        self._audit.append(event)
        return event

    def issue_grant(
        self,
        *,
        operator_id: str,
        scopes: Iterable[str],
        now: float,
        duration_seconds: float,
        max_uses: int,
        reason: str,
    ) -> BreakGlassGrant:
        operator_id = _token(operator_id, "operator_id")
        reason = _token(reason, "reason", maximum=512)
        now = _time(now, "now")
        duration_seconds = _time(duration_seconds, "duration_seconds")
        if duration_seconds <= 0 or duration_seconds > self._max_grant_seconds:
            raise OperatorOverrideError("grant duration exceeds break-glass bound")
        if isinstance(max_uses, bool) or not isinstance(max_uses, int) or max_uses < 1:
            raise OperatorOverrideError("max_uses must be positive integer")

        normalized = tuple(sorted(set(_token(item, "scope") for item in scopes)))
        if not normalized:
            raise OperatorOverrideError("break-glass grant requires explicit scopes")
        for scope in normalized:
            if ":" not in scope or "*" in scope:
                raise OperatorOverrideError(
                    "break-glass scopes must be exact action:resource pairs"
                )
            action, resource = scope.split(":", 1)
            self._scope(action, resource)

        reason_digest = _digest({"reason": reason})
        grant_id = _digest(
            {
                "operator_id": operator_id,
                "scopes": normalized,
                "issued_at": now,
                "expires_at": now + duration_seconds,
                "max_uses": max_uses,
                "reason_digest": reason_digest,
                "sequence": len(self._grants) + 1,
            }
        )
        grant = BreakGlassGrant(
            grant_id=grant_id,
            operator_id=operator_id,
            scopes=normalized,
            issued_at=now,
            expires_at=now + duration_seconds,
            max_uses=max_uses,
            reason_digest=reason_digest,
        )
        self._grants[grant_id] = grant
        self._grant_uses[grant_id] = 0
        self._append_audit(
            "grant_issued",
            occurred_at=now,
            payload={
                "grant_id": grant_id,
                "operator_id": operator_id,
                "scopes": normalized,
                "expires_at": grant.expires_at,
                "max_uses": max_uses,
                "reason_digest": reason_digest,
            },
        )
        return grant

    def _grant_for(
        self,
        grant_id: str,
        *,
        action: OverrideAction,
        now: float,
        consume: bool,
    ) -> BreakGlassGrant:
        try:
            grant = self._grants[grant_id]
        except KeyError as exc:
            raise OperatorOverrideError("unknown break-glass grant") from exc
        now = _time(now, "now")
        if now < grant.issued_at or now > grant.expires_at:
            raise OperatorOverrideError("break-glass grant is not currently valid")
        if action.scope not in grant.scopes:
            raise OperatorOverrideError("action exceeds break-glass scope")
        used = self._grant_uses[grant_id]
        if consume and used >= grant.max_uses:
            raise OperatorOverrideError("break-glass grant use budget exhausted")
        return grant

    def preview(
        self,
        grant_id: str,
        action: OverrideAction,
        *,
        now: float,
    ) -> PreviewReceipt:
        if not isinstance(action, OverrideAction):
            raise TypeError("action must be OverrideAction")
        self._grant_for(grant_id, action=action, now=now, consume=False)
        payload = {
            "grant_id": grant_id,
            "action_scope": action.scope,
            "destructive": action.destructive,
            "inverse_action": action.inverse_action,
            "created_at": float(now),
        }
        digest = _digest(payload)
        receipt = PreviewReceipt(
            grant_id=grant_id,
            action_scope=action.scope,
            created_at=float(now),
            digest=digest,
        )
        self._previews[digest] = receipt
        self._append_audit("preview", occurred_at=now, payload=payload)
        return receipt

    def _check_fatigue(self, operator_id: str, now: float) -> None:
        floor = float(now) - self._approval_window_seconds
        recent = sum(
            owner == operator_id and timestamp >= floor
            for owner, timestamp in self._executions
        )
        if recent >= self._max_approvals_per_window:
            raise OperatorOverrideError("approval fatigue bound exceeded")

    def execute(
        self,
        grant_id: str,
        action: OverrideAction,
        *,
        now: float,
        preview_digest: str | None = None,
    ) -> OverrideReceipt:
        if not isinstance(action, OverrideAction):
            raise TypeError("action must be OverrideAction")
        now = _time(now, "now")
        grant = self._grant_for(grant_id, action=action, now=now, consume=True)
        self._check_fatigue(grant.operator_id, now)

        if action.destructive:
            if not preview_digest:
                raise OperatorOverrideError(
                    "destructive override requires preview receipt"
                )
            preview = self._previews.get(preview_digest)
            if (
                preview is None
                or preview.grant_id != grant_id
                or preview.action_scope != action.scope
                or now < preview.created_at
                or now - preview.created_at > self._preview_ttl_seconds
            ):
                raise OperatorOverrideError(
                    "destructive override preview is missing, stale, or mismatched"
                )
        elif preview_digest is not None and preview_digest not in self._previews:
            raise OperatorOverrideError("unknown preview receipt")

        undo_deadline = (
            now + self._undo_window_seconds
            if action.destructive and action.inverse_action
            else None
        )
        event = self._append_audit(
            "override_executed",
            occurred_at=now,
            payload={
                "grant_id": grant_id,
                "operator_id": grant.operator_id,
                "action_scope": action.scope,
                "preview_digest": preview_digest,
                "undo_deadline": undo_deadline,
                "inverse_action": action.inverse_action,
            },
        )
        receipt_id = _digest(
            {
                "grant_id": grant_id,
                "action_scope": action.scope,
                "executed_at": now,
                "audit_digest": event.digest,
            }
        )
        receipt = OverrideReceipt(
            receipt_id=receipt_id,
            grant_id=grant_id,
            operator_id=grant.operator_id,
            action_scope=action.scope,
            executed_at=now,
            preview_digest=preview_digest,
            undo_deadline=undo_deadline,
            inverse_action=action.inverse_action,
            audit_digest=event.digest,
        )
        self._receipts[receipt_id] = receipt
        self._grant_uses[grant_id] += 1
        self._executions.append((grant.operator_id, now))
        return receipt

    def undo(self, receipt_id: str, *, now: float) -> AuditEvent:
        now = _time(now, "now")
        try:
            receipt = self._receipts[receipt_id]
        except KeyError as exc:
            raise OperatorOverrideError("unknown override receipt") from exc
        if receipt_id in self._undone:
            raise OperatorOverrideError("override receipt already undone")
        if receipt.inverse_action is None or receipt.undo_deadline is None:
            raise OperatorOverrideError("override action has no undo path")
        if now < receipt.executed_at or now > receipt.undo_deadline:
            raise OperatorOverrideError("override undo window expired")

        event = self._append_audit(
            "override_undone",
            occurred_at=now,
            payload={
                "receipt_id": receipt_id,
                "operator_id": receipt.operator_id,
                "inverse_action": receipt.inverse_action,
                "action_scope": receipt.action_scope,
            },
        )
        self._undone.add(receipt_id)
        return event

    def audit_events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._audit)

    def verify_audit_chain(self) -> bool:
        previous = "0" * 64
        for event in self._audit:
            expected = _digest(
                {
                    "sequence": event.sequence,
                    "kind": event.kind,
                    "occurred_at": event.occurred_at,
                    "payload_digest": event.payload_digest,
                    "previous_digest": previous,
                }
            )
            if event.previous_digest != previous or event.digest != expected:
                return False
            previous = event.digest
        return True


__all__ = [
    "AuditEvent",
    "BreakGlassGrant",
    "OperatorOverrideController",
    "OperatorOverrideError",
    "OverrideAction",
    "OverrideReceipt",
    "PreviewReceipt",
]
