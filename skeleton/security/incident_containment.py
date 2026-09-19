"""Incident containment and authenticated recovery for the repository defense plane.

Hostile conditions should cause authority to contract, not expand. This module
turns bounded security signals into monotonic containment state and deliberately
separates automatic escalation from human-authorized recovery.

Properties:

* duplicate observations are idempotent;
* raw evidence is never retained -- only a digest and bounded summary;
* containment can escalate automatically but never auto-deescalates;
* recovery permits are short-lived, HMAC-authenticated, incident-bound,
  subject-bound, current-mode-bound, target-mode-bound, and one-shot;
* one incident cannot lower repository containment beneath the floor required
  by another active incident;
* critical incidents quarantine the affected principal locally in addition to
  raising the global containment mode;
* all transitions append to the defense plane's tamper-evident ledger.

This is a containment system, not an offensive response system. It never
contacts, probes, retaliates against, or modifies an external attacker.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
import threading
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Iterable, Mapping, Sequence

from skeleton.security.defense_plane import (
    ContainmentMode,
    DefenseConfigurationError,
    DefenseIntegrityError,
    DefensePlane,
    SignalKind,
)

_MAX_SUMMARY = 500
_MAX_SOURCE = 128
_MAX_KIND = 128
_MAX_SUBJECT = 256
_MAX_EVIDENCE_BYTES = 1_048_576
_MAX_INCIDENTS = 4096
_MAX_SIGNAL_DIGESTS = 256
_MAX_TOKEN_BYTES = 8192
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TOKEN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_INCIDENT_ID_RE = re.compile(r"^inc-[0-9a-f]{24}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class IncidentError(RuntimeError):
    """Base error for incident containment."""


class IncidentIntegrityError(IncidentError):
    """Raised when incident or recovery evidence is malformed."""


class IncidentStateError(IncidentError):
    """Raised when an incident transition is not permitted."""


class IncidentSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentPhase(str, Enum):
    DETECTED = "detected"
    TRIAGE = "triage"
    CONTAINED = "contained"
    RECOVERY = "recovery"
    MONITORING = "monitoring"
    CLOSED = "closed"


_SEVERITY_SCORE = {
    IncidentSeverity.INFO: 1,
    IncidentSeverity.LOW: 3,
    IncidentSeverity.MEDIUM: 7,
    IncidentSeverity.HIGH: 15,
    IncidentSeverity.CRITICAL: 30,
}

_MODE_RANK = {
    ContainmentMode.NORMAL: 0,
    ContainmentMode.RESTRICTED: 1,
    ContainmentMode.QUARANTINE: 2,
    ContainmentMode.LOCKDOWN: 3,
}


def _text(
    value: object,
    *,
    field_name: str,
    limit: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise IncidentIntegrityError(f"{field_name} must be a string")
    if value != value.strip():
        raise IncidentIntegrityError(f"{field_name} must be canonical")
    if not value and not allow_empty:
        raise IncidentIntegrityError(f"{field_name} must not be empty")
    if len(value) > limit:
        raise IncidentIntegrityError(f"{field_name} exceeds maximum length")
    if _CONTROL_RE.search(value):
        raise IncidentIntegrityError(f"{field_name} contains control characters")
    return value


def _timestamp(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IncidentIntegrityError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise IncidentIntegrityError(f"{field_name} must be finite and non-negative")
    return number


def _digest(value: object, *, field_name: str) -> str:
    text = _text(value, field_name=field_name, limit=64).casefold()
    if _DIGEST_RE.fullmatch(text) is None:
        raise IncidentIntegrityError(f"{field_name} must be sha256 hex")
    return text


def _incident_id(value: object) -> str:
    text = _text(value, field_name="incident_id", limit=28)
    if _INCIDENT_ID_RE.fullmatch(text) is None:
        raise IncidentIntegrityError("incident_id is invalid")
    return text


def _token_id(value: object) -> str:
    text = _text(value, field_name="token_id", limit=128)
    if _TOKEN_ID_RE.fullmatch(text) is None:
        raise IncidentIntegrityError("token_id is invalid")
    return text


def _key_id(value: object) -> str:
    text = _text(value, field_name="key_id", limit=64)
    if _KEY_ID_RE.fullmatch(text) is None:
        raise IncidentIntegrityError("key_id is invalid")
    return text


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    text = _text(value, field_name="recovery payload", limit=_MAX_TOKEN_BYTES)
    if re.fullmatch(r"[A-Za-z0-9_-]+", text) is None:
        raise IncidentIntegrityError("recovery payload is not canonical base64url")
    padding = "=" * ((4 - len(text) % 4) % 4)
    try:
        decoded = base64.b64decode(
            text + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise IncidentIntegrityError("recovery payload is invalid base64url") from exc
    if len(decoded) > _MAX_TOKEN_BYTES:
        raise IncidentIntegrityError("recovery payload exceeds maximum size")
    return decoded


def _object_pairs(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise IncidentIntegrityError(f"duplicate recovery field: {key}")
        payload[key] = value
    return payload


def digest_evidence(evidence: str | bytes) -> str:
    """Hash bounded evidence without retaining its potentially sensitive body."""

    if isinstance(evidence, str):
        raw = evidence.encode("utf-8")
    elif isinstance(evidence, bytes):
        raw = evidence
    else:
        raise IncidentIntegrityError("evidence must be text or bytes")
    if len(raw) > _MAX_EVIDENCE_BYTES:
        raise IncidentIntegrityError("evidence exceeds maximum size")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class IncidentSignal:
    source: str
    kind: str
    severity: IncidentSeverity
    subject: str
    observed_at: float
    evidence_digest: str
    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source",
            _text(self.source, field_name="signal source", limit=_MAX_SOURCE),
        )
        object.__setattr__(
            self,
            "kind",
            _text(self.kind, field_name="signal kind", limit=_MAX_KIND),
        )
        if not isinstance(self.severity, IncidentSeverity):
            try:
                object.__setattr__(
                    self,
                    "severity",
                    IncidentSeverity(self.severity),
                )
            except (TypeError, ValueError) as exc:
                raise IncidentIntegrityError("signal severity is invalid") from exc
        object.__setattr__(
            self,
            "subject",
            _text(self.subject, field_name="signal subject", limit=_MAX_SUBJECT),
        )
        object.__setattr__(
            self,
            "observed_at",
            _timestamp(self.observed_at, field_name="observed_at"),
        )
        object.__setattr__(
            self,
            "evidence_digest",
            _digest(self.evidence_digest, field_name="evidence_digest"),
        )
        object.__setattr__(
            self,
            "summary",
            _text(self.summary, field_name="signal summary", limit=_MAX_SUMMARY),
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            _json_bytes(
                {
                    "source": self.source,
                    "kind": self.kind,
                    "severity": self.severity.value,
                    "subject": self.subject,
                    "observed_at": self.observed_at,
                    "evidence_digest": self.evidence_digest,
                    "summary": self.summary,
                }
            )
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class IncidentPolicy:
    restricted_score: int = 7
    quarantine_score: int = 15
    lockdown_score: int = 30
    max_signal_age_seconds: float = 900.0
    max_future_skew_seconds: float = 30.0
    quarantine_seconds: float = 1800.0

    def __post_init__(self) -> None:
        for name in ("restricted_score", "quarantine_score", "lockdown_score"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise DefenseConfigurationError(f"{name} must be a positive integer")
        if not (
            self.restricted_score
            <= self.quarantine_score
            <= self.lockdown_score
        ):
            raise DefenseConfigurationError(
                "incident containment thresholds must be monotonic"
            )
        for name in (
            "max_signal_age_seconds",
            "max_future_skew_seconds",
            "quarantine_seconds",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0
            ):
                raise DefenseConfigurationError(f"{name} must be finite and positive")

    def mode_for_score(self, score: int) -> ContainmentMode:
        if score >= self.lockdown_score:
            return ContainmentMode.LOCKDOWN
        if score >= self.quarantine_score:
            return ContainmentMode.QUARANTINE
        if score >= self.restricted_score:
            return ContainmentMode.RESTRICTED
        return ContainmentMode.NORMAL


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    incident_id: str
    subject: str
    opened_at: float
    updated_at: float
    phase: IncidentPhase
    required_mode: ContainmentMode
    score: int
    signal_count: int
    signal_fingerprints: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    last_summary: str
    recovery_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "incident_id", _incident_id(self.incident_id))
        object.__setattr__(
            self,
            "subject",
            _text(self.subject, field_name="incident subject", limit=_MAX_SUBJECT),
        )
        opened = _timestamp(self.opened_at, field_name="opened_at")
        updated = _timestamp(self.updated_at, field_name="updated_at")
        if updated < opened:
            raise IncidentIntegrityError("updated_at precedes opened_at")
        if not isinstance(self.phase, IncidentPhase):
            object.__setattr__(self, "phase", IncidentPhase(self.phase))
        if not isinstance(self.required_mode, ContainmentMode):
            object.__setattr__(
                self,
                "required_mode",
                ContainmentMode(self.required_mode),
            )
        if isinstance(self.score, bool) or not isinstance(self.score, int) or self.score < 0:
            raise IncidentIntegrityError("incident score must be non-negative integer")
        if (
            isinstance(self.signal_count, bool)
            or not isinstance(self.signal_count, int)
            or self.signal_count < 1
        ):
            raise IncidentIntegrityError("signal_count must be positive")
        if len(self.signal_fingerprints) > _MAX_SIGNAL_DIGESTS:
            raise IncidentIntegrityError("too many signal fingerprints")
        if len(self.evidence_digests) > _MAX_SIGNAL_DIGESTS:
            raise IncidentIntegrityError("too many evidence digests")
        for value in self.signal_fingerprints:
            _digest(value, field_name="signal fingerprint")
        for value in self.evidence_digests:
            _digest(value, field_name="incident evidence digest")
        object.__setattr__(
            self,
            "last_summary",
            _text(
                self.last_summary,
                field_name="incident last_summary",
                limit=_MAX_SUMMARY,
            ),
        )
        if (
            isinstance(self.recovery_count, bool)
            or not isinstance(self.recovery_count, int)
            or self.recovery_count < 0
        ):
            raise IncidentIntegrityError("recovery_count must be non-negative")

    @property
    def active(self) -> bool:
        return self.phase is not IncidentPhase.CLOSED


@dataclass(frozen=True, slots=True)
class RecoveryClaims:
    token_id: str
    key_id: str
    incident_id: str
    subject: str
    operator: str
    from_mode: ContainmentMode
    to_mode: ContainmentMode
    issued_at: float
    expires_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "token_id", _token_id(self.token_id))
        object.__setattr__(self, "key_id", _key_id(self.key_id))
        object.__setattr__(self, "incident_id", _incident_id(self.incident_id))
        object.__setattr__(
            self,
            "subject",
            _text(self.subject, field_name="recovery subject", limit=_MAX_SUBJECT),
        )
        object.__setattr__(
            self,
            "operator",
            _text(self.operator, field_name="recovery operator", limit=128),
        )
        if not isinstance(self.from_mode, ContainmentMode):
            object.__setattr__(self, "from_mode", ContainmentMode(self.from_mode))
        if not isinstance(self.to_mode, ContainmentMode):
            object.__setattr__(self, "to_mode", ContainmentMode(self.to_mode))
        if _MODE_RANK[self.to_mode] >= _MODE_RANK[self.from_mode]:
            raise IncidentIntegrityError(
                "recovery target must strictly reduce containment"
            )
        issued = _timestamp(self.issued_at, field_name="recovery issued_at")
        expires = _timestamp(self.expires_at, field_name="recovery expires_at")
        if expires <= issued:
            raise IncidentIntegrityError("recovery token expiry must follow issue time")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def payload(self) -> dict[str, object]:
        return {
            "v": 1,
            "token_id": self.token_id,
            "key_id": self.key_id,
            "incident_id": self.incident_id,
            "subject": self.subject,
            "operator": self.operator,
            "from_mode": self.from_mode.value,
            "to_mode": self.to_mode.value,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True, slots=True)
class RecoveryKey:
    key_id: str
    secret: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", _key_id(self.key_id))
        if not isinstance(self.secret, bytes) or len(self.secret) < 32:
            raise IncidentIntegrityError(
                "recovery signing key must be at least 32 bytes"
            )


@dataclass(slots=True)
class RecoveryAuthority:
    keys: tuple[RecoveryKey, ...]
    active_key_id: str
    max_ttl_seconds: float = 600.0
    max_future_skew_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.keys:
            raise IncidentIntegrityError("recovery authority requires a key")
        ids = [item.key_id for item in self.keys]
        if len(ids) != len(set(ids)):
            raise IncidentIntegrityError("recovery key ids must be unique")
        self.active_key_id = _key_id(self.active_key_id)
        if self.active_key_id not in ids:
            raise IncidentIntegrityError("active recovery key is unavailable")
        for name in ("max_ttl_seconds", "max_future_skew_seconds"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0
            ):
                raise IncidentIntegrityError(
                    f"{name} must be finite and positive"
                )

    @property
    def _key_map(self) -> dict[str, bytes]:
        return {item.key_id: item.secret for item in self.keys}

    def issue(self, claims: RecoveryClaims) -> str:
        if claims.key_id != self.active_key_id:
            raise IncidentIntegrityError(
                "new recovery token must use the active key"
            )
        if claims.expires_at - claims.issued_at > self.max_ttl_seconds:
            raise IncidentIntegrityError("recovery token ttl exceeds policy")
        payload = _b64encode(_json_bytes(claims.payload()))
        signing_input = f"v1.{payload}".encode("ascii")
        signature = hmac.new(
            self._key_map[claims.key_id],
            signing_input,
            hashlib.sha256,
        ).hexdigest()
        return f"v1.{payload}.{signature}"

    def verify(self, token: str, *, now: float) -> RecoveryClaims:
        text = _text(token, field_name="recovery token", limit=_MAX_TOKEN_BYTES * 2)
        pieces = text.split(".")
        if len(pieces) != 3 or pieces[0] != "v1":
            raise IncidentIntegrityError("recovery token format is invalid")
        encoded, signature = pieces[1], pieces[2]
        if _DIGEST_RE.fullmatch(signature) is None:
            raise IncidentIntegrityError("recovery signature is invalid")

        try:
            payload = json.loads(
                _b64decode(encoded).decode("utf-8"),
                object_pairs_hook=_object_pairs,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IncidentIntegrityError("recovery payload is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise IncidentIntegrityError("recovery payload must be an object")
        expected = {
            "v",
            "token_id",
            "key_id",
            "incident_id",
            "subject",
            "operator",
            "from_mode",
            "to_mode",
            "issued_at",
            "expires_at",
        }
        if set(payload) != expected or payload.get("v") != 1:
            raise IncidentIntegrityError("recovery payload fields are invalid")

        claims = RecoveryClaims(
            token_id=payload["token_id"],
            key_id=payload["key_id"],
            incident_id=payload["incident_id"],
            subject=payload["subject"],
            operator=payload["operator"],
            from_mode=payload["from_mode"],
            to_mode=payload["to_mode"],
            issued_at=payload["issued_at"],
            expires_at=payload["expires_at"],
        )
        key = self._key_map.get(claims.key_id)
        if key is None:
            raise IncidentIntegrityError("recovery signing key is not trusted")
        expected_signature = hmac.new(
            key,
            f"v1.{encoded}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            raise IncidentIntegrityError("recovery signature verification failed")

        moment = _timestamp(now, field_name="now")
        if claims.issued_at > moment + self.max_future_skew_seconds:
            raise IncidentIntegrityError("recovery token is issued in the future")
        if moment >= claims.expires_at:
            raise IncidentIntegrityError("recovery token has expired")
        if claims.expires_at - claims.issued_at > self.max_ttl_seconds:
            raise IncidentIntegrityError("recovery token ttl exceeds policy")
        return claims


@dataclass(slots=True)
class IncidentCoordinator:
    defense: DefensePlane
    recovery_authority: RecoveryAuthority
    policy: IncidentPolicy = field(default_factory=IncidentPolicy)
    clock: Callable[[], float] = time.time
    max_incidents: int = _MAX_INCIDENTS
    _incidents: dict[str, IncidentRecord] = field(default_factory=dict, init=False)
    _active_by_subject: dict[str, str] = field(default_factory=dict, init=False)
    _used_recovery_tokens: set[str] = field(default_factory=set, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.defense, DefensePlane):
            raise IncidentIntegrityError("defense must be DefensePlane")
        if not isinstance(self.recovery_authority, RecoveryAuthority):
            raise IncidentIntegrityError(
                "recovery_authority must be RecoveryAuthority"
            )
        if not callable(self.clock):
            raise IncidentIntegrityError("clock must be callable")
        if (
            isinstance(self.max_incidents, bool)
            or not isinstance(self.max_incidents, int)
            or self.max_incidents < 1
        ):
            raise IncidentIntegrityError("max_incidents must be positive")

    def observe(self, signal: IncidentSignal) -> IncidentRecord:
        if not isinstance(signal, IncidentSignal):
            raise IncidentIntegrityError("signal must be IncidentSignal")
        now = _timestamp(self.clock(), field_name="clock")
        if signal.observed_at > now + self.policy.max_future_skew_seconds:
            raise IncidentIntegrityError("signal timestamp is too far in the future")
        if now - signal.observed_at > self.policy.max_signal_age_seconds:
            raise IncidentIntegrityError("signal is stale")

        with self._lock:
            current_id = self._active_by_subject.get(signal.subject)
            if current_id is None:
                record = self._new_record(signal, now)
            else:
                record = self._incidents[current_id]
                if signal.fingerprint in record.signal_fingerprints:
                    return record
                record = self._append_signal(record, signal, now)

            self._incidents[record.incident_id] = record
            self._active_by_subject[record.subject] = record.incident_id
            self._apply_containment(record, signal, now)
            return record

    def get(self, incident_id: str) -> IncidentRecord:
        key = _incident_id(incident_id)
        with self._lock:
            try:
                return self._incidents[key]
            except KeyError as exc:
                raise IncidentStateError("incident does not exist") from exc

    def active_incidents(self) -> tuple[IncidentRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (item for item in self._incidents.values() if item.active),
                    key=lambda item: (item.opened_at, item.incident_id),
                )
            )

    def mark_contained(self, incident_id: str) -> IncidentRecord:
        now = _timestamp(self.clock(), field_name="clock")
        with self._lock:
            record = self.get(incident_id)
            if record.phase is IncidentPhase.CLOSED:
                raise IncidentStateError("closed incident cannot be contained")
            if _MODE_RANK[record.required_mode] < _MODE_RANK[ContainmentMode.RESTRICTED]:
                raise IncidentStateError(
                    "incident has not reached an automatic containment threshold"
                )
            updated = replace(
                record,
                phase=IncidentPhase.CONTAINED,
                updated_at=now,
            )
            self._incidents[record.incident_id] = updated
            self._audit_transition(updated, "incident.contained", now)
            return updated

    def apply_recovery(self, token: str) -> IncidentRecord:
        now = _timestamp(self.clock(), field_name="clock")
        claims = self.recovery_authority.verify(token, now=now)

        with self._lock:
            if claims.token_id in self._used_recovery_tokens:
                raise IncidentStateError("recovery token has already been consumed")
            record = self.get(claims.incident_id)
            if record.phase is IncidentPhase.CLOSED:
                raise IncidentStateError("closed incident cannot enter recovery")
            if claims.subject != record.subject:
                raise IncidentStateError("recovery token subject does not match incident")
            if claims.from_mode is not record.required_mode:
                raise IncidentStateError(
                    "recovery token is stale for current incident containment"
                )
            if _MODE_RANK[claims.to_mode] >= _MODE_RANK[record.required_mode]:
                raise IncidentStateError("recovery must reduce incident containment")

            other_floor = self._other_incident_floor(record.incident_id)
            effective_target = (
                claims.to_mode
                if _MODE_RANK[claims.to_mode] >= _MODE_RANK[other_floor]
                else other_floor
            )
            if effective_target is not claims.to_mode:
                raise IncidentStateError(
                    "another active incident requires stronger containment"
                )

            self._used_recovery_tokens.add(claims.token_id)
            updated = replace(
                record,
                phase=(
                    IncidentPhase.MONITORING
                    if claims.to_mode is ContainmentMode.NORMAL
                    else IncidentPhase.RECOVERY
                ),
                required_mode=claims.to_mode,
                updated_at=now,
                recovery_count=record.recovery_count + 1,
            )
            self._incidents[record.incident_id] = updated
            self.defense.set_mode(self._global_floor())
            if claims.to_mode is ContainmentMode.NORMAL:
                self.defense.quarantines.release(record.subject)
            self._audit_transition(updated, "incident.recovery", now)
            return updated

    def close(self, incident_id: str) -> IncidentRecord:
        now = _timestamp(self.clock(), field_name="clock")
        with self._lock:
            record = self.get(incident_id)
            if record.phase not in {
                IncidentPhase.MONITORING,
                IncidentPhase.RECOVERY,
            }:
                raise IncidentStateError(
                    "incident must pass through authenticated recovery before closure"
                )
            if record.required_mode is not ContainmentMode.NORMAL:
                raise IncidentStateError(
                    "incident containment must be normal before closure"
                )
            updated = replace(
                record,
                phase=IncidentPhase.CLOSED,
                updated_at=now,
            )
            self._incidents[record.incident_id] = updated
            self._active_by_subject.pop(record.subject, None)
            self.defense.set_mode(self._global_floor())
            self._audit_transition(updated, "incident.closed", now)
            return updated

    def _new_record(
        self,
        signal: IncidentSignal,
        now: float,
    ) -> IncidentRecord:
        if len(self._incidents) >= self.max_incidents:
            self._evict_closed()
        if len(self._incidents) >= self.max_incidents:
            raise IncidentStateError(
                "incident store is full of active evidence; refusing to evict"
            )
        identity = hashlib.sha256(
            _json_bytes(
                {
                    "subject": signal.subject,
                    "first_signal": signal.fingerprint,
                    "opened_at": now,
                }
            )
        ).hexdigest()[:24]
        incident_id = f"inc-{identity}"
        score = _SEVERITY_SCORE[signal.severity]
        mode = self.policy.mode_for_score(score)
        return IncidentRecord(
            incident_id=incident_id,
            subject=signal.subject,
            opened_at=now,
            updated_at=now,
            phase=IncidentPhase.DETECTED,
            required_mode=mode,
            score=score,
            signal_count=1,
            signal_fingerprints=(signal.fingerprint,),
            evidence_digests=(signal.evidence_digest,),
            last_summary=signal.summary,
        )

    def _append_signal(
        self,
        record: IncidentRecord,
        signal: IncidentSignal,
        now: float,
    ) -> IncidentRecord:
        fingerprints = (
            *record.signal_fingerprints,
            signal.fingerprint,
        )[-_MAX_SIGNAL_DIGESTS:]
        evidence = tuple(
            dict.fromkeys(
                (
                    *record.evidence_digests,
                    signal.evidence_digest,
                )
            )
        )[-_MAX_SIGNAL_DIGESTS:]
        score = record.score + _SEVERITY_SCORE[signal.severity]
        desired = self.policy.mode_for_score(score)
        required = (
            desired
            if _MODE_RANK[desired] > _MODE_RANK[record.required_mode]
            else record.required_mode
        )
        phase = (
            IncidentPhase.TRIAGE
            if record.phase is IncidentPhase.DETECTED
            else record.phase
        )
        return replace(
            record,
            updated_at=now,
            phase=phase,
            required_mode=required,
            score=score,
            signal_count=record.signal_count + 1,
            signal_fingerprints=tuple(fingerprints),
            evidence_digests=evidence,
            last_summary=signal.summary,
        )

    def _apply_containment(
        self,
        record: IncidentRecord,
        signal: IncidentSignal,
        now: float,
    ) -> None:
        current = self.defense.mode
        if _MODE_RANK[record.required_mode] > _MODE_RANK[current]:
            self.defense.set_mode(record.required_mode)

        if _MODE_RANK[record.required_mode] >= _MODE_RANK[ContainmentMode.QUARANTINE]:
            self.defense.quarantines.quarantine(
                record.subject,
                reason=f"incident containment: {signal.kind}",
                now=now,
                ttl_seconds=self.policy.quarantine_seconds,
            )

        signal_kind = {
            "malware": SignalKind.MALWARE,
            "sandbox_escape": SignalKind.SANDBOX_ESCAPE,
            "policy_tamper": SignalKind.POLICY_TAMPER,
            "secret_probe": SignalKind.SECRET_PROBE,
            "replay": SignalKind.REPLAY,
        }.get(signal.kind, SignalKind.OTHER)
        self.defense.report_signal(record.subject, signal_kind, now=now)
        self._audit_transition(record, "incident.signal", now, signal.fingerprint)

    def _global_floor(self) -> ContainmentMode:
        floor = ContainmentMode.NORMAL
        for incident in self._incidents.values():
            if not incident.active:
                continue
            if _MODE_RANK[incident.required_mode] > _MODE_RANK[floor]:
                floor = incident.required_mode
        return floor

    def _other_incident_floor(self, excluded_id: str) -> ContainmentMode:
        floor = ContainmentMode.NORMAL
        for incident in self._incidents.values():
            if incident.incident_id == excluded_id or not incident.active:
                continue
            if _MODE_RANK[incident.required_mode] > _MODE_RANK[floor]:
                floor = incident.required_mode
        return floor

    def _evict_closed(self) -> None:
        closed = sorted(
            (
                item
                for item in self._incidents.values()
                if item.phase is IncidentPhase.CLOSED
            ),
            key=lambda item: (item.updated_at, item.incident_id),
        )
        while len(self._incidents) >= self.max_incidents and closed:
            item = closed.pop(0)
            self._incidents.pop(item.incident_id, None)

    def _audit_transition(
        self,
        record: IncidentRecord,
        event: str,
        now: float,
        fingerprint: str | None = None,
    ) -> None:
        self.defense.ledger.append(
            timestamp=now,
            event=event,
            subject=record.subject,
            decision=f"{record.phase.value}:{record.required_mode.value}",
            request_fingerprint=fingerprint or hashlib.sha256(
                _json_bytes(
                    {
                        "incident_id": record.incident_id,
                        "phase": record.phase.value,
                        "mode": record.required_mode.value,
                        "score": record.score,
                        "signal_count": record.signal_count,
                    }
                )
            ).hexdigest(),
        )


__all__ = [
    "IncidentCoordinator",
    "IncidentError",
    "IncidentIntegrityError",
    "IncidentPhase",
    "IncidentPolicy",
    "IncidentRecord",
    "IncidentSeverity",
    "IncidentSignal",
    "IncidentStateError",
    "RecoveryAuthority",
    "RecoveryClaims",
    "RecoveryKey",
    "digest_evidence",
]
