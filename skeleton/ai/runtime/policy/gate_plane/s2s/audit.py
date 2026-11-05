"""Audit events for the s2s plane, emitted through the existing telemetry adapter.

:class:`S2SAuditTrail` turns gate decisions, key-ring lifecycle changes and
registry changes into :class:`AuditEvent` records and fans them out to
sinks. :class:`TelemetryAuditSink` routes them through Pack F's
:class:`~skeleton.gate_plane.telemetry.gate_telemetry.GateTelemetry`
(``MetricsCollector`` underneath) - no new metrics backend.

Audit records never contain token material or key secrets: only service
names, policy names, kids, fingerprints and reasons. Telemetry labels are
bounded (kind / outcome / reason / service); raw paths stay in the audit
record only, with query strings stripped.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Protocol

from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.registry import RegistryEvent, ServiceRegistry

AUDIT_METRIC = "gate_s2s_audit_events_total"
KIND_DECISION = "decision"
KIND_KEY = "key_lifecycle"
KIND_REGISTRY = "registry"
_SECURITY_REASONS = frozenset({
    "replayed", "bad_signature", "revoked_kid", "revoked_token", "binding_mismatch",
    "binding_missing", "bad_issuer", "nonce_store_full", "unknown_kid",
})


@dataclass(frozen=True)
class AuditEvent:
    kind: str
    at: float
    action: str
    outcome: str = ""
    reason: str = ""
    service: Optional[str] = None
    policy: Optional[str] = None
    kid: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    http_status: Optional[int] = None
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def security_relevant(self) -> bool:
        return self.reason in _SECURITY_REASONS or self.action in ("revoke", "disable")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind, "at": self.at, "action": self.action, "outcome": self.outcome,
            "reason": self.reason, "service": self.service, "policy": self.policy, "kid": self.kid,
            "method": self.method, "path": self.path, "http_status": self.http_status,
            "security_relevant": self.security_relevant, "detail": dict(self.detail),
        }


class AuditSink(Protocol):
    def emit(self, event: AuditEvent) -> None: ...


class InMemoryAuditSink:
    """Bounded ring buffer sink (tests, local debugging)."""

    def __init__(self, capacity: int = 4096) -> None:
        self._events: Deque[AuditEvent] = deque(maxlen=int(capacity))
        self._lock = threading.Lock()

    def emit(self, event: AuditEvent) -> None:
        with self._lock:
            self._events.append(event)

    def events(self, *, kind: Optional[str] = None) -> List[AuditEvent]:
        with self._lock:
            return [e for e in self._events if kind is None or e.kind == kind]

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


class TelemetryAuditSink:
    """Counts audit events through an existing ``GateTelemetry`` adapter."""

    def __init__(self, telemetry: Any, *, metric: str = AUDIT_METRIC) -> None:
        if not hasattr(telemetry, "metrics"):
            raise TypeError("telemetry must expose .metrics (GateTelemetry)")
        self.telemetry = telemetry
        self.metric = metric

    def emit(self, event: AuditEvent) -> None:
        from skeleton.gate_plane.telemetry.gate_telemetry import safe_label

        labels = {
            "kind": event.kind,
            "action": event.action,
            "outcome": event.outcome or "-",
            "reason": event.reason or "-",
            "service": event.service or "-",
        }
        try:
            self.telemetry.metrics.increment(self.metric, 1.0, {k: safe_label(v) for k, v in labels.items()})
        except Exception:  # noqa: BLE001 - audit export never changes a verdict
            pass


def _strip_path(path: str) -> str:
    return (path or "/").split("?", 1)[0].split("#", 1)[0]


class S2SAuditTrail:
    def __init__(self, sinks: Iterable[AuditSink] = (), *, clock: Optional[Clock] = None) -> None:
        self._sinks: List[AuditSink] = list(sinks)
        self.clock = clock if clock is not None else system_clock()
        self._key_cursor: Dict[int, int] = {}
        self._lock = threading.Lock()
        self.dropped = 0

    def add_sink(self, sink: AuditSink) -> None:
        self._sinks.append(sink)

    def emit(self, event: AuditEvent) -> None:
        for sink in list(self._sinks):
            try:
                sink.emit(event)
            except Exception:  # noqa: BLE001
                with self._lock:
                    self.dropped += 1

    # -- gate decisions -----------------------------------------------------
    def gate_hook(self, method: str, path: str, decision: Any) -> None:
        """``S2SAuthGate.add_hook(trail.gate_hook)``."""
        principal = getattr(decision, "principal", None)
        token_error = getattr(decision, "token_error", None)
        outcome = getattr(getattr(decision, "outcome", None), "value", str(getattr(decision, "outcome", "")))
        if outcome == "open_bypass":
            return  # probes are not audited
        detail: Dict[str, Any] = {}
        if token_error is not None:
            detail["token_error"] = getattr(token_error, "value", str(token_error))
        authz = getattr(decision, "authz", None)
        if authz is not None and getattr(authz, "missing_scopes", ()):
            detail["missing_scopes"] = list(authz.missing_scopes)
        self.emit(AuditEvent(
            kind=KIND_DECISION,
            at=self.clock.now(),
            action="request",
            outcome=outcome,
            reason=str(getattr(decision, "reason", "")),
            service=None if principal is None else principal.service,
            policy=getattr(decision, "policy", None),
            kid=None if principal is None else principal.kid,
            method=(method or "GET").upper(),
            path=_strip_path(path),
            http_status=int(getattr(decision, "http_status", 0) or 0),
            detail=detail,
        ))

    # -- key lifecycle ---------------------------------------------------------
    def sync_keyring(self, ring: KeyRing, *, name: str = "default") -> int:
        """Emit audit events for key-ring events not yet seen. Returns count emitted."""
        events = ring.events()
        with self._lock:
            cursor = self._key_cursor.get(id(ring), 0)
            if cursor > len(events):  # ring trimmed its buffer
                cursor = 0
            fresh = events[cursor:]
            self._key_cursor[id(ring)] = len(events)
        for ev in fresh:
            self.emit(AuditEvent(
                kind=KIND_KEY, at=ev.at, action=ev.action, kid=ev.kid,
                reason=ev.detail if ev.action == "revoke" else "", detail={"ring": name, "detail": ev.detail},
            ))
        return len(fresh)

    # -- registry --------------------------------------------------------------
    def registry_listener(self, event: RegistryEvent) -> None:
        self.emit(AuditEvent(
            kind=KIND_REGISTRY, at=self.clock.now(), action=event.action,
            service=event.service, detail={"detail": event.detail},
        ))

    def watch_registry(self, registry: ServiceRegistry) -> None:
        registry.add_listener(self.registry_listener)


__all__ = [
    "AUDIT_METRIC",
    "AuditEvent",
    "AuditSink",
    "InMemoryAuditSink",
    "KIND_DECISION",
    "KIND_KEY",
    "KIND_REGISTRY",
    "S2SAuditTrail",
    "TelemetryAuditSink",
]
