"""Deterministic side-effect authority ledger for VOL-378..380.

The ledger records authority decisions and outcomes; it never executes effects.
Unknown outcomes quarantine an idempotency key until explicit reconciliation.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from skeleton.contracts.canonical import canonical_json_bytes


class EffectState(str, Enum):
    PREPARED = "prepared"
    IN_FLIGHT = "in_flight"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    RECONCILIATION_REQUIRED = "reconciliation_required"


_TERMINAL = frozenset({EffectState.SUCCEEDED, EffectState.COMPENSATED})
_RETRYABLE = frozenset({EffectState.FAILED})
_QUARANTINED = frozenset({EffectState.UNKNOWN, EffectState.RECONCILIATION_REQUIRED})
_ALLOWED = {
    EffectState.PREPARED: {EffectState.IN_FLIGHT},
    EffectState.IN_FLIGHT: {EffectState.SUCCEEDED, EffectState.FAILED, EffectState.UNKNOWN},
    EffectState.FAILED: {EffectState.PREPARED, EffectState.COMPENSATING},
    EffectState.UNKNOWN: {EffectState.RECONCILIATION_REQUIRED},
    EffectState.COMPENSATING: {EffectState.COMPENSATED, EffectState.RECONCILIATION_REQUIRED},
    EffectState.RECONCILIATION_REQUIRED: {EffectState.FAILED, EffectState.SUCCEEDED, EffectState.COMPENSATED},
    EffectState.SUCCEEDED: set(),
    EffectState.COMPENSATED: set(),
}


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class EffectIdentity:
    operation_id: str
    effect_id: str
    idempotency_key: str
    authority_scope: str

    def __post_init__(self) -> None:
        for name in ("operation_id", "effect_id", "idempotency_key", "authority_scope"):
            object.__setattr__(self, name, _text(getattr(self, name), name))

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes({
            "operation_id": self.operation_id,
            "effect_id": self.effect_id,
            "idempotency_key": self.idempotency_key,
            "authority_scope": self.authority_scope,
        })).hexdigest()


@dataclass(frozen=True, slots=True)
class EffectEvent:
    identity: EffectIdentity
    sequence: int
    state: EffectState
    prior_digest: str | None = None
    evidence_digest: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        for name in ("prior_digest", "evidence_digest"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
                raise ValueError(f"{name} must be lowercase sha256")

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes({
            "identity_digest": self.identity.digest,
            "sequence": self.sequence,
            "state": self.state.value,
            "prior_digest": self.prior_digest,
            "evidence_digest": self.evidence_digest,
        })).hexdigest()


class SideEffectLedger:
    def __init__(self, events: Iterable[EffectEvent] = ()) -> None:
        self._events: list[EffectEvent] = []
        self._heads: dict[str, EffectEvent] = {}
        for event in events:
            self.append(event)

    def append(self, event: EffectEvent) -> str:
        key = event.identity.idempotency_key
        prior = self._heads.get(key)
        if prior is None:
            if event.sequence != 1 or event.prior_digest is not None or event.state is not EffectState.PREPARED:
                raise ValueError("first effect event must prepare sequence one")
        else:
            if event.identity != prior.identity:
                raise PermissionError("idempotency key identity collision")
            if event.sequence != prior.sequence + 1 or event.prior_digest != prior.digest:
                raise ValueError("effect event chain mismatch")
            if event.state not in _ALLOWED[prior.state]:
                raise PermissionError(f"illegal effect transition {prior.state.value}->{event.state.value}")
        self._events.append(event)
        self._heads[key] = event
        return event.digest

    def transition(self, identity: EffectIdentity, state: EffectState, *, evidence_digest: str | None = None) -> EffectEvent:
        prior = self._heads.get(identity.idempotency_key)
        if prior is None:
            event = EffectEvent(identity, 1, state, evidence_digest=evidence_digest)
        else:
            event = EffectEvent(identity, prior.sequence + 1, state, prior.digest, evidence_digest)
        self.append(event)
        return event

    def admit(self, identity: EffectIdentity) -> EffectEvent:
        prior = self._heads.get(identity.idempotency_key)
        if prior is None:
            return self.transition(identity, EffectState.PREPARED)
        if prior.identity != identity:
            raise PermissionError("idempotency key already bound to another effect")
        if prior.state in _TERMINAL:
            raise PermissionError("effect already terminal")
        if prior.state in _QUARANTINED:
            raise PermissionError("effect outcome requires reconciliation")
        if prior.state not in _RETRYABLE:
            raise PermissionError("effect already active")
        return self.transition(identity, EffectState.PREPARED)

    def head(self, idempotency_key: str) -> EffectEvent:
        return self._heads[_text(idempotency_key, "idempotency_key")]

    def history(self, idempotency_key: str) -> tuple[EffectEvent, ...]:
        key = _text(idempotency_key, "idempotency_key")
        return tuple(event for event in self._events if event.identity.idempotency_key == key)

    @property
    def replay_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes([event.digest for event in self._events])).hexdigest()
