"""Repository defense plane: containment-first authorization for hostile conditions.

This module is deliberately defensive. It does not "hack back", retaliate, or
initiate actions against an attacker. Its self-defense model is containment:

* authenticate and bind an actor to immutable execution provenance;
* reject stale, replayed, malformed, over-budget, or capability-widening work;
* restrict sensitive actions as the system enters containment modes;
* quarantine actors/resources locally when reliable threat signals accumulate;
* preserve a bounded, tamper-evident decision ledger;
* fail closed whenever the control plane cannot establish authority.

The implementation is standard-library-only so the defense boundary does not
depend on optional packages or network services.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import threading
import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Iterable, Mapping, MutableMapping, Sequence

_MAX_TEXT = 512
_MAX_RESOURCE = 2048
_MAX_METADATA_ITEMS = 64
_MAX_METADATA_VALUE = 512
_MAX_CAPABILITIES = 64
_MAX_LEDGER_ENTRIES = 10_000
_MAX_REPLAY_ENTRIES = 50_000
_MAX_QUARANTINES = 10_000
_MAX_SIGNALS_PER_SUBJECT = 1024
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class DefenseError(RuntimeError):
    """Base class for defense-plane failures."""


class DefenseConfigurationError(DefenseError):
    """Raised when a security policy is malformed."""


class DefenseIntegrityError(DefenseError):
    """Raised when audit or request integrity cannot be established."""


class TrustLevel(str, Enum):
    UNTRUSTED = "untrusted"
    AUTHENTICATED = "authenticated"
    TRUSTED = "trusted"


class ActionClass(str, Enum):
    OBSERVE = "observe"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    CREDENTIAL = "credential"
    POLICY = "policy"
    RELEASE = "release"


class ContainmentMode(str, Enum):
    NORMAL = "normal"
    RESTRICTED = "restricted"
    QUARANTINE = "quarantine"
    LOCKDOWN = "lockdown"


class DecisionCode(str, Enum):
    ALLOW = "allow"
    DENY_INVALID = "deny.invalid"
    DENY_STALE = "deny.stale"
    DENY_FUTURE = "deny.future"
    DENY_REPLAY = "deny.replay"
    DENY_QUARANTINE = "deny.quarantine"
    DENY_CONTAINMENT = "deny.containment"
    DENY_TRUST = "deny.trust"
    DENY_CAPABILITY = "deny.capability"
    DENY_BUDGET = "deny.budget"
    DENY_ESCALATION = "deny.escalation"
    DENY_RESOURCE = "deny.resource"
    DENY_INTEGRITY = "deny.integrity"


class SignalKind(str, Enum):
    MALFORMED_AUTHORITY = "malformed_authority"
    REPLAY = "replay"
    CAPABILITY_ESCALATION = "capability_escalation"
    SECRET_PROBE = "secret_probe"
    SANDBOX_ESCAPE = "sandbox_escape"
    POLICY_TAMPER = "policy_tamper"
    RATE_ABUSE = "rate_abuse"
    INTEGRITY_FAILURE = "integrity_failure"
    MALWARE = "malware"
    OTHER = "other"


_SIGNAL_WEIGHT = {
    SignalKind.MALFORMED_AUTHORITY: 2,
    SignalKind.REPLAY: 3,
    SignalKind.CAPABILITY_ESCALATION: 5,
    SignalKind.SECRET_PROBE: 5,
    SignalKind.SANDBOX_ESCAPE: 8,
    SignalKind.POLICY_TAMPER: 8,
    SignalKind.RATE_ABUSE: 2,
    SignalKind.INTEGRITY_FAILURE: 8,
    SignalKind.MALWARE: 10,
    SignalKind.OTHER: 1,
}

_REQUIRED_CAPABILITIES = {
    ActionClass.OBSERVE: frozenset(),
    ActionClass.READ: frozenset({"resource.read"}),
    ActionClass.WRITE: frozenset({"resource.write"}),
    ActionClass.EXECUTE: frozenset({"execution.run"}),
    ActionClass.NETWORK: frozenset({"network.egress"}),
    ActionClass.CREDENTIAL: frozenset({"secret.read"}),
    ActionClass.POLICY: frozenset({"policy.write"}),
    ActionClass.RELEASE: frozenset({"release.write"}),
}

_MUTATING_ACTIONS = frozenset(
    {
        ActionClass.WRITE,
        ActionClass.EXECUTE,
        ActionClass.NETWORK,
        ActionClass.CREDENTIAL,
        ActionClass.POLICY,
        ActionClass.RELEASE,
    }
)

_PRIVILEGED_ACTIONS = frozenset(
    {
        ActionClass.EXECUTE,
        ActionClass.CREDENTIAL,
        ActionClass.POLICY,
        ActionClass.RELEASE,
    }
)

_ESCALATION_METADATA_KEYS = frozenset(
    {
        "grant",
        "grants",
        "capability",
        "capabilities",
        "permissions",
        "permission",
        "override",
        "bypass",
        "sudo",
        "admin",
        "token",
        "secret",
    }
)


def _required_text(
    value: object,
    *,
    field_name: str,
    limit: int = _MAX_TEXT,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise DefenseIntegrityError(f"{field_name} must be a string")
    if value != value.strip():
        raise DefenseIntegrityError(f"{field_name} must be canonical")
    text = value
    if not text and not allow_empty:
        raise DefenseIntegrityError(f"{field_name} must not be empty")
    if len(text) > limit:
        raise DefenseIntegrityError(f"{field_name} exceeds maximum length")
    if _CONTROL_RE.search(text):
        raise DefenseIntegrityError(f"{field_name} contains control characters")
    return text


def _identifier(value: object, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name, limit=256)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise DefenseIntegrityError(f"{field_name} is not a canonical identifier")
    return text


def _request_id(value: object) -> str:
    text = _required_text(value, field_name="request_id", limit=128)
    if _REQUEST_ID_RE.fullmatch(text) is None:
        raise DefenseIntegrityError("request_id is not canonical")
    return text


def _repository(value: object) -> str:
    text = _required_text(value, field_name="repository", limit=201)
    if _REPOSITORY_RE.fullmatch(text) is None:
        raise DefenseIntegrityError("repository must be owner/name")
    return text


def _commit_sha(value: object) -> str:
    text = _required_text(value, field_name="commit_sha", limit=40)
    if _SHA_RE.fullmatch(text) is None:
        raise DefenseIntegrityError(
            "commit_sha must be a full lowercase 40-character hex OID"
        )
    return text


def _capability(value: object) -> str:
    text = _required_text(value, field_name="capability", limit=128).casefold()
    if _CAPABILITY_RE.fullmatch(text) is None:
        raise DefenseIntegrityError("capability name is invalid")
    return text


def _resource(value: object) -> str:
    text = _required_text(value, field_name="resource", limit=_MAX_RESOURCE)
    if "\x00" in text:
        raise DefenseIntegrityError("resource contains NUL")
    return text


def _finite_timestamp(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DefenseIntegrityError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise DefenseIntegrityError(f"{field_name} must be finite and non-negative")
    return number


def _canonical_metadata(
    metadata: Mapping[str, object] | Sequence[tuple[str, str]] | None,
) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if isinstance(metadata, Mapping):
        items = list(metadata.items())
    else:
        try:
            items = list(metadata)
        except TypeError as exc:
            raise DefenseIntegrityError("metadata must be a mapping or pair sequence") from exc
    if len(items) > _MAX_METADATA_ITEMS:
        raise DefenseIntegrityError("metadata contains too many entries")
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_key, raw_value in items:
        key = _required_text(raw_key, field_name="metadata key", limit=96).casefold()
        if key in seen:
            raise DefenseIntegrityError(f"duplicate metadata key: {key}")
        seen.add(key)
        value = _required_text(
            str(raw_value),
            field_name=f"metadata[{key}]",
            limit=_MAX_METADATA_VALUE,
            allow_empty=True,
        )
        normalized.append((key, value))
    return tuple(sorted(normalized))


def _canonical_capabilities(values: Iterable[str]) -> frozenset[str]:
    try:
        materialized = list(values)
    except TypeError as exc:
        raise DefenseIntegrityError("capabilities must be iterable") from exc
    if len(materialized) > _MAX_CAPABILITIES:
        raise DefenseIntegrityError("too many capabilities")
    return frozenset(_capability(item) for item in materialized)


def _json_bytes(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ActorIdentity:
    subject: str
    source: str
    repository: str
    workflow: str
    run_id: int
    run_attempt: int
    ref: str
    commit_sha: str
    event: str
    trust: TrustLevel = TrustLevel.UNTRUSTED

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject", _identifier(self.subject, field_name="subject"))
        object.__setattr__(self, "source", _identifier(self.source, field_name="source"))
        object.__setattr__(self, "repository", _repository(self.repository))
        object.__setattr__(
            self,
            "workflow",
            _required_text(self.workflow, field_name="workflow", limit=256),
        )
        for field_name in ("run_id", "run_attempt"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise DefenseIntegrityError(f"{field_name} must be a positive integer")
        object.__setattr__(
            self,
            "ref",
            _required_text(self.ref, field_name="ref", limit=512),
        )
        object.__setattr__(self, "commit_sha", _commit_sha(self.commit_sha))
        object.__setattr__(
            self,
            "event",
            _identifier(self.event, field_name="event"),
        )
        if not isinstance(self.trust, TrustLevel):
            try:
                object.__setattr__(self, "trust", TrustLevel(self.trust))
            except (TypeError, ValueError) as exc:
                raise DefenseIntegrityError("trust level is invalid") from exc

    @property
    def fingerprint(self) -> str:
        payload = {
            "subject": self.subject,
            "source": self.source,
            "repository": self.repository,
            "workflow": self.workflow,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "ref": self.ref,
            "commit_sha": self.commit_sha,
            "event": self.event,
            "trust": self.trust.value,
        }
        return hashlib.sha256(_json_bytes(payload)).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "source": self.source,
            "repository": self.repository,
            "workflow": self.workflow,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "ref": self.ref,
            "commit_sha": self.commit_sha,
            "event": self.event,
            "trust": self.trust.value,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class SecurityRequest:
    request_id: str
    nonce: str
    issued_at: float
    action: ActionClass
    resource: str
    actor: ActorIdentity
    capabilities: frozenset[str] = frozenset()
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _request_id(self.request_id))
        object.__setattr__(
            self,
            "nonce",
            _required_text(self.nonce, field_name="nonce", limit=128),
        )
        object.__setattr__(
            self,
            "issued_at",
            _finite_timestamp(self.issued_at, field_name="issued_at"),
        )
        if not isinstance(self.action, ActionClass):
            try:
                object.__setattr__(self, "action", ActionClass(self.action))
            except (TypeError, ValueError) as exc:
                raise DefenseIntegrityError("action class is invalid") from exc
        object.__setattr__(self, "resource", _resource(self.resource))
        if not isinstance(self.actor, ActorIdentity):
            raise DefenseIntegrityError("actor must be ActorIdentity")
        object.__setattr__(
            self,
            "capabilities",
            _canonical_capabilities(self.capabilities),
        )
        object.__setattr__(
            self,
            "metadata",
            _canonical_metadata(self.metadata),
        )

    @property
    def metadata_map(self) -> dict[str, str]:
        return dict(self.metadata)

    @property
    def fingerprint(self) -> str:
        payload = {
            "request_id": self.request_id,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "action": self.action.value,
            "resource": self.resource,
            "actor": self.actor.to_dict(),
            "capabilities": sorted(self.capabilities),
            "metadata": dict(self.metadata),
        }
        return hashlib.sha256(_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class DefenseDecision:
    allowed: bool
    code: DecisionCode
    reason: str
    request_fingerprint: str
    mode: ContainmentMode
    required_capabilities: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, DecisionCode):
            raise DefenseIntegrityError("decision code is invalid")
        if not isinstance(self.mode, ContainmentMode):
            raise DefenseIntegrityError("containment mode is invalid")
        object.__setattr__(
            self,
            "reason",
            _required_text(self.reason, field_name="decision reason", limit=256),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "code": self.code.value,
            "reason": self.reason,
            "request_fingerprint": self.request_fingerprint,
            "mode": self.mode.value,
            "required_capabilities": list(self.required_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
        }


@dataclass(frozen=True, slots=True)
class DefensePolicy:
    max_request_age_seconds: float = 300.0
    max_future_skew_seconds: float = 30.0
    replay_ttl_seconds: float = 900.0
    mutation_window_seconds: float = 60.0
    max_writes_per_window: int = 30
    max_executes_per_window: int = 6
    max_network_per_window: int = 60
    max_credentials_per_window: int = 3
    max_policy_changes_per_window: int = 2
    max_releases_per_window: int = 2
    quarantine_threshold: int = 10
    quarantine_seconds: float = 900.0
    allow_untrusted_reads: bool = False

    def __post_init__(self) -> None:
        for name in (
            "max_request_age_seconds",
            "max_future_skew_seconds",
            "replay_ttl_seconds",
            "mutation_window_seconds",
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
        for name in (
            "max_writes_per_window",
            "max_executes_per_window",
            "max_network_per_window",
            "max_credentials_per_window",
            "max_policy_changes_per_window",
            "max_releases_per_window",
            "quarantine_threshold",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise DefenseConfigurationError(f"{name} must be a positive integer")

    def limit_for(self, action: ActionClass) -> int | None:
        return {
            ActionClass.WRITE: self.max_writes_per_window,
            ActionClass.EXECUTE: self.max_executes_per_window,
            ActionClass.NETWORK: self.max_network_per_window,
            ActionClass.CREDENTIAL: self.max_credentials_per_window,
            ActionClass.POLICY: self.max_policy_changes_per_window,
            ActionClass.RELEASE: self.max_releases_per_window,
        }.get(action)


@dataclass(slots=True)
class ReplayWindow:
    ttl_seconds: float
    max_entries: int = _MAX_REPLAY_ENTRIES
    _entries: OrderedDict[str, float] = field(default_factory=OrderedDict, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.ttl_seconds, bool)
            or not isinstance(self.ttl_seconds, (int, float))
            or not math.isfinite(float(self.ttl_seconds))
            or float(self.ttl_seconds) <= 0
        ):
            raise DefenseConfigurationError("replay ttl must be finite and positive")
        if isinstance(self.max_entries, bool) or not isinstance(self.max_entries, int) or self.max_entries < 1:
            raise DefenseConfigurationError("replay max_entries must be positive")

    def seen_or_record(self, key: str, now: float) -> bool:
        canonical = _required_text(key, field_name="replay key", limit=256)
        moment = _finite_timestamp(now, field_name="now")
        with self._lock:
            self._prune(moment)
            if canonical in self._entries:
                return True
            self._entries[canonical] = moment + float(self.ttl_seconds)
            self._entries.move_to_end(canonical)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
            return False

    def _prune(self, now: float) -> None:
        while self._entries:
            key, expires_at = next(iter(self._entries.items()))
            if expires_at > now:
                break
            self._entries.pop(key, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


@dataclass(slots=True)
class SlidingWindowBudget:
    window_seconds: float
    _events: MutableMapping[tuple[str, str], Deque[float]] = field(
        default_factory=lambda: defaultdict(deque),
        init=False,
    )
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def allow(self, key: tuple[str, str], *, limit: int, now: float) -> bool:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise DefenseConfigurationError("budget limit must be positive")
        moment = _finite_timestamp(now, field_name="now")
        cutoff = moment - float(self.window_seconds)
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(moment)
            return True

    def count(self, key: tuple[str, str], *, now: float) -> int:
        moment = _finite_timestamp(now, field_name="now")
        cutoff = moment - float(self.window_seconds)
        with self._lock:
            bucket = self._events.get(key)
            if not bucket:
                return 0
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            return len(bucket)


@dataclass(frozen=True, slots=True)
class QuarantineEntry:
    subject: str
    reason: str
    created_at: float
    expires_at: float

    def active(self, now: float) -> bool:
        return now < self.expires_at


@dataclass(slots=True)
class QuarantineRegistry:
    max_entries: int = _MAX_QUARANTINES
    _entries: OrderedDict[str, QuarantineEntry] = field(
        default_factory=OrderedDict,
        init=False,
    )
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def quarantine(
        self,
        subject: str,
        *,
        reason: str,
        now: float,
        ttl_seconds: float,
    ) -> QuarantineEntry:
        identity = _required_text(subject, field_name="quarantine subject", limit=256)
        why = _required_text(reason, field_name="quarantine reason", limit=256)
        moment = _finite_timestamp(now, field_name="now")
        ttl = _finite_timestamp(ttl_seconds, field_name="ttl_seconds")
        if ttl <= 0:
            raise DefenseConfigurationError("quarantine ttl must be positive")
        entry = QuarantineEntry(
            subject=identity,
            reason=why,
            created_at=moment,
            expires_at=moment + ttl,
        )
        with self._lock:
            self._entries[identity] = entry
            self._entries.move_to_end(identity)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return entry

    def active(self, subject: str, *, now: float) -> QuarantineEntry | None:
        identity = _required_text(subject, field_name="quarantine subject", limit=256)
        moment = _finite_timestamp(now, field_name="now")
        with self._lock:
            entry = self._entries.get(identity)
            if entry is None:
                return None
            if not entry.active(moment):
                self._entries.pop(identity, None)
                return None
            return entry

    def release(self, subject: str) -> bool:
        identity = _required_text(subject, field_name="quarantine subject", limit=256)
        with self._lock:
            return self._entries.pop(identity, None) is not None


@dataclass(frozen=True, slots=True)
class AuditEntry:
    sequence: int
    timestamp: float
    event: str
    subject: str
    decision: str
    request_fingerprint: str
    previous_digest: str
    digest: str
    mac: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event": self.event,
            "subject": self.subject,
            "decision": self.decision,
            "request_fingerprint": self.request_fingerprint,
            "previous_digest": self.previous_digest,
            "digest": self.digest,
            "mac": self.mac,
        }


@dataclass(slots=True)
class IntegrityLedger:
    """Bounded append-only hash chain with optional HMAC authentication."""

    hmac_key: bytes | None = None
    max_entries: int = _MAX_LEDGER_ENTRIES
    _entries: Deque[AuditEntry] = field(default_factory=deque, init=False)
    _next_sequence: int = field(default=1, init=False)
    _anchor_digest: str = field(default="0" * 64, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.hmac_key is not None:
            if not isinstance(self.hmac_key, bytes) or len(self.hmac_key) < 32:
                raise DefenseConfigurationError("ledger HMAC key must be at least 32 bytes")
        if isinstance(self.max_entries, bool) or not isinstance(self.max_entries, int) or self.max_entries < 1:
            raise DefenseConfigurationError("ledger max_entries must be positive")

    def append(
        self,
        *,
        timestamp: float,
        event: str,
        subject: str,
        decision: str,
        request_fingerprint: str,
    ) -> AuditEntry:
        moment = _finite_timestamp(timestamp, field_name="timestamp")
        event_name = _identifier(event, field_name="event")
        actor = _required_text(subject, field_name="subject", limit=256)
        verdict = _required_text(decision, field_name="decision", limit=128)
        fingerprint = _required_text(
            request_fingerprint,
            field_name="request_fingerprint",
            limit=128,
        )
        with self._lock:
            previous = self._entries[-1].digest if self._entries else self._anchor_digest
            sequence = self._next_sequence
            body = {
                "sequence": sequence,
                "timestamp": moment,
                "event": event_name,
                "subject": actor,
                "decision": verdict,
                "request_fingerprint": fingerprint,
                "previous_digest": previous,
            }
            digest = hashlib.sha256(_json_bytes(body)).hexdigest()
            mac = ""
            if self.hmac_key is not None:
                mac = hmac.new(self.hmac_key, digest.encode("ascii"), hashlib.sha256).hexdigest()
            entry = AuditEntry(
                sequence=sequence,
                timestamp=moment,
                event=event_name,
                subject=actor,
                decision=verdict,
                request_fingerprint=fingerprint,
                previous_digest=previous,
                digest=digest,
                mac=mac,
            )
            self._entries.append(entry)
            self._next_sequence += 1
            while len(self._entries) > self.max_entries:
                removed = self._entries.popleft()
                self._anchor_digest = removed.digest
            return entry

    def entries(self) -> tuple[AuditEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    def verify(self) -> bool:
        with self._lock:
            previous = self._anchor_digest
            expected_sequence = (
                self._entries[0].sequence if self._entries else self._next_sequence
            )
            for entry in self._entries:
                if entry.sequence != expected_sequence:
                    return False
                body = {
                    "sequence": entry.sequence,
                    "timestamp": entry.timestamp,
                    "event": entry.event,
                    "subject": entry.subject,
                    "decision": entry.decision,
                    "request_fingerprint": entry.request_fingerprint,
                    "previous_digest": previous,
                }
                expected_digest = hashlib.sha256(_json_bytes(body)).hexdigest()
                if not hmac.compare_digest(expected_digest, entry.digest):
                    return False
                if entry.previous_digest != previous:
                    return False
                if self.hmac_key is not None:
                    expected_mac = hmac.new(
                        self.hmac_key,
                        entry.digest.encode("ascii"),
                        hashlib.sha256,
                    ).hexdigest()
                    if not hmac.compare_digest(expected_mac, entry.mac):
                        return False
                elif entry.mac:
                    return False
                previous = entry.digest
                expected_sequence += 1
            return True


@dataclass(slots=True)
class SignalAccumulator:
    window_seconds: float = 900.0
    max_per_subject: int = _MAX_SIGNALS_PER_SUBJECT
    _signals: MutableMapping[str, Deque[tuple[float, int, SignalKind]]] = field(
        default_factory=lambda: defaultdict(deque),
        init=False,
    )
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def add(self, subject: str, kind: SignalKind, *, now: float) -> int:
        identity = _required_text(subject, field_name="signal subject", limit=256)
        if not isinstance(kind, SignalKind):
            kind = SignalKind(kind)
        moment = _finite_timestamp(now, field_name="now")
        cutoff = moment - float(self.window_seconds)
        with self._lock:
            bucket = self._signals[identity]
            while bucket and bucket[0][0] <= cutoff:
                bucket.popleft()
            bucket.append((moment, _SIGNAL_WEIGHT[kind], kind))
            while len(bucket) > self.max_per_subject:
                bucket.popleft()
            return sum(weight for _, weight, _ in bucket)

    def score(self, subject: str, *, now: float) -> int:
        identity = _required_text(subject, field_name="signal subject", limit=256)
        moment = _finite_timestamp(now, field_name="now")
        cutoff = moment - float(self.window_seconds)
        with self._lock:
            bucket = self._signals.get(identity)
            if not bucket:
                return 0
            while bucket and bucket[0][0] <= cutoff:
                bucket.popleft()
            return sum(weight for _, weight, _ in bucket)


@dataclass(slots=True)
class DefensePlane:
    """Containment-oriented authorization and incident boundary."""

    policy: DefensePolicy = field(default_factory=DefensePolicy)
    mode: ContainmentMode = ContainmentMode.NORMAL
    clock: Callable[[], float] = time.time
    replay: ReplayWindow | None = None
    budget: SlidingWindowBudget | None = None
    quarantines: QuarantineRegistry = field(default_factory=QuarantineRegistry)
    signals: SignalAccumulator = field(default_factory=SignalAccumulator)
    ledger: IntegrityLedger = field(default_factory=IntegrityLedger)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.policy, DefensePolicy):
            raise DefenseConfigurationError("policy must be DefensePolicy")
        if not isinstance(self.mode, ContainmentMode):
            self.mode = ContainmentMode(self.mode)
        if not callable(self.clock):
            raise DefenseConfigurationError("clock must be callable")
        if self.replay is None:
            self.replay = ReplayWindow(self.policy.replay_ttl_seconds)
        if self.budget is None:
            self.budget = SlidingWindowBudget(self.policy.mutation_window_seconds)

    def set_mode(self, mode: ContainmentMode | str) -> None:
        selected = ContainmentMode(mode)
        with self._lock:
            self.mode = selected

    def evaluate(self, request: SecurityRequest) -> DefenseDecision:
        if not isinstance(request, SecurityRequest):
            raise DefenseIntegrityError("request must be SecurityRequest")
        now = _finite_timestamp(self.clock(), field_name="clock")
        fingerprint = request.fingerprint

        if request.issued_at > now + self.policy.max_future_skew_seconds:
            return self._deny(
                request,
                DecisionCode.DENY_FUTURE,
                "request timestamp is too far in the future",
                now,
            )
        if now - request.issued_at > self.policy.max_request_age_seconds:
            return self._deny(
                request,
                DecisionCode.DENY_STALE,
                "request is older than the authorization window",
                now,
            )

        replay_key = hashlib.sha256(
            f"{request.actor.fingerprint}\x1f{request.request_id}\x1f{request.nonce}".encode(
                "utf-8"
            )
        ).hexdigest()
        assert self.replay is not None
        if self.replay.seen_or_record(replay_key, now):
            self.report_signal(
                request.actor.fingerprint,
                SignalKind.REPLAY,
                now=now,
            )
            return self._deny(
                request,
                DecisionCode.DENY_REPLAY,
                "request identity has already been consumed",
                now,
            )

        quarantine = self.quarantines.active(request.actor.fingerprint, now=now)
        if quarantine is not None:
            return self._deny(
                request,
                DecisionCode.DENY_QUARANTINE,
                "actor is quarantined",
                now,
            )

        mode_denial = self._containment_denial(request)
        if mode_denial is not None:
            return self._deny(
                request,
                DecisionCode.DENY_CONTAINMENT,
                mode_denial,
                now,
            )

        trust_denial = self._trust_denial(request)
        if trust_denial is not None:
            self.report_signal(
                request.actor.fingerprint,
                SignalKind.MALFORMED_AUTHORITY,
                now=now,
            )
            return self._deny(
                request,
                DecisionCode.DENY_TRUST,
                trust_denial,
                now,
            )

        if self._requests_capability_escalation(request):
            self.report_signal(
                request.actor.fingerprint,
                SignalKind.CAPABILITY_ESCALATION,
                now=now,
            )
            return self._deny(
                request,
                DecisionCode.DENY_ESCALATION,
                "request metadata attempts to alter its own authority",
                now,
            )

        required = _REQUIRED_CAPABILITIES[request.action]
        missing = sorted(required - request.capabilities)
        if missing:
            return self._deny(
                request,
                DecisionCode.DENY_CAPABILITY,
                "required capability is missing",
                now,
                required=required,
                missing=missing,
            )

        if request.action in _MUTATING_ACTIONS:
            limit = self.policy.limit_for(request.action)
            assert limit is not None
            assert self.budget is not None
            key = (request.actor.fingerprint, request.action.value)
            if not self.budget.allow(key, limit=limit, now=now):
                self.report_signal(
                    request.actor.fingerprint,
                    SignalKind.RATE_ABUSE,
                    now=now,
                )
                return self._deny(
                    request,
                    DecisionCode.DENY_BUDGET,
                    "action budget is exhausted",
                    now,
                    required=required,
                )

        decision = DefenseDecision(
            allowed=True,
            code=DecisionCode.ALLOW,
            reason="request satisfies containment, trust, capability, and budget policy",
            request_fingerprint=fingerprint,
            mode=self.mode,
            required_capabilities=tuple(sorted(required)),
            missing_capabilities=(),
        )
        self._record(request, decision, now)
        return decision

    def report_signal(
        self,
        subject: str,
        kind: SignalKind | str,
        *,
        now: float | None = None,
    ) -> int:
        moment = _finite_timestamp(
            self.clock() if now is None else now,
            field_name="signal timestamp",
        )
        signal_kind = kind if isinstance(kind, SignalKind) else SignalKind(kind)
        score = self.signals.add(subject, signal_kind, now=moment)
        if score >= self.policy.quarantine_threshold:
            self.quarantines.quarantine(
                subject,
                reason=f"automatic containment threshold reached ({signal_kind.value})",
                now=moment,
                ttl_seconds=self.policy.quarantine_seconds,
            )
        return score

    def _containment_denial(self, request: SecurityRequest) -> str | None:
        if self.mode is ContainmentMode.NORMAL:
            return None
        if self.mode is ContainmentMode.RESTRICTED:
            if request.action in _PRIVILEGED_ACTIONS:
                return "privileged action disabled in restricted mode"
            return None
        if self.mode is ContainmentMode.QUARANTINE:
            if request.action not in {ActionClass.OBSERVE, ActionClass.READ}:
                return "mutating action disabled in quarantine mode"
            return None
        if self.mode is ContainmentMode.LOCKDOWN:
            if request.action is not ActionClass.OBSERVE:
                return "only observation is permitted in lockdown mode"
            return None
        return "unknown containment mode fails closed"

    def _trust_denial(self, request: SecurityRequest) -> str | None:
        if request.actor.trust is TrustLevel.TRUSTED:
            return None
        if request.actor.trust is TrustLevel.AUTHENTICATED:
            if request.action in {ActionClass.POLICY, ActionClass.RELEASE, ActionClass.CREDENTIAL}:
                return "authenticated actor lacks trusted status for privileged action"
            return None
        if request.action is ActionClass.OBSERVE:
            return None
        if request.action is ActionClass.READ and self.policy.allow_untrusted_reads:
            return None
        return "untrusted actor cannot perform requested action"

    def _requests_capability_escalation(self, request: SecurityRequest) -> bool:
        if not request.metadata:
            return False
        for key, value in request.metadata:
            normalized_key = key.replace("-", "_")
            atoms = set(filter(None, re.split(r"[._:/]+", normalized_key)))
            if atoms.intersection(_ESCALATION_METADATA_KEYS):
                lowered = value.casefold()
                if lowered not in {"", "false", "0", "none", "observe"}:
                    return True
        return False

    def _deny(
        self,
        request: SecurityRequest,
        code: DecisionCode,
        reason: str,
        now: float,
        *,
        required: Iterable[str] = (),
        missing: Iterable[str] = (),
    ) -> DefenseDecision:
        decision = DefenseDecision(
            allowed=False,
            code=code,
            reason=reason,
            request_fingerprint=request.fingerprint,
            mode=self.mode,
            required_capabilities=tuple(sorted(required)),
            missing_capabilities=tuple(sorted(missing)),
        )
        self._record(request, decision, now)
        return decision

    def _record(
        self,
        request: SecurityRequest,
        decision: DefenseDecision,
        now: float,
    ) -> None:
        self.ledger.append(
            timestamp=now,
            event="defense.decision",
            subject=request.actor.fingerprint,
            decision=decision.code.value,
            request_fingerprint=request.fingerprint,
        )

    def snapshot(self) -> dict[str, object]:
        now = _finite_timestamp(self.clock(), field_name="clock")
        return {
            "mode": self.mode.value,
            "ledger_entries": len(self.ledger.entries()),
            "ledger_valid": self.ledger.verify(),
            "replay_entries": len(self.replay) if self.replay is not None else 0,
            "timestamp": now,
        }


__all__ = [
    "ActionClass",
    "ActorIdentity",
    "AuditEntry",
    "ContainmentMode",
    "DecisionCode",
    "DefenseConfigurationError",
    "DefenseDecision",
    "DefenseError",
    "DefenseIntegrityError",
    "DefensePlane",
    "DefensePolicy",
    "IntegrityLedger",
    "QuarantineEntry",
    "QuarantineRegistry",
    "ReplayWindow",
    "SecurityRequest",
    "SignalAccumulator",
    "SignalKind",
    "SlidingWindowBudget",
    "TrustLevel",
]
