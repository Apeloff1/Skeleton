"""Security control plane for autonomous repository automation.

Automation is treated as a privileged principal, not as a trusted script.
Mutating work is authorized only when all of the following remain true:

* the run identity is fully bound to repository/workflow/ref/commit provenance;
* a short-lived HMAC-authenticated permit authorizes the exact operation;
* the permit is bound to this actor and cannot be replayed across runs;
* resource scope, use count, and mutation budgets remain within bounds;
* the circuit breaker and repository defense plane are both healthy;
* operator pause/quarantine controls do not block the run.

The design is intentionally containment-only. It never retaliates against
external systems and it never grants itself additional authority.
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
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Iterable, Mapping, MutableMapping, Sequence

from skeleton.automation.automation_safety import AutomationSafety
from skeleton.security.defense_plane import (
    ActionClass,
    ActorIdentity,
    DecisionCode,
    DefenseDecision,
    DefenseIntegrityError,
    DefensePlane,
    SecurityRequest,
    TrustLevel,
)

_MAX_TOKEN_BYTES = 16_384
_MAX_OPERATIONS = 32
_MAX_RESOURCE_SCOPES = 64
_MAX_RESOURCE_LENGTH = 2048
_MAX_REASON = 256
_MAX_LEDGER_ENTRIES = 20_000
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PERMIT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class AutomationControlError(RuntimeError):
    """Raised when automation authority or evidence is invalid."""


class AutomationOperation(str, Enum):
    OBSERVE = "observe"
    READ_REPOSITORY = "repository.read"
    COMMENT = "issue.comment"
    LABEL = "issue.label"
    CREATE_ISSUE = "issue.create"
    UPDATE_ISSUE = "issue.update"
    CREATE_BRANCH = "branch.create"
    WRITE_CONTENT = "contents.write"
    CREATE_PULL_REQUEST = "pull_request.create"
    UPDATE_PULL_REQUEST = "pull_request.update"
    REQUEST_REVIEW = "pull_request.request_review"
    MERGE_PULL_REQUEST = "pull_request.merge"
    DISPATCH_WORKFLOW = "workflow.dispatch"
    CANCEL_WORKFLOW = "workflow.cancel"
    DELETE_BRANCH = "branch.delete"
    RELEASE = "release.publish"
    POLICY_CHANGE = "policy.change"
    SECRET_READ = "secret.read"


class OperationRisk(str, Enum):
    READ_ONLY = "read_only"
    MUTATION = "mutation"
    PRIVILEGED = "privileged"
    DESTRUCTIVE = "destructive"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


_OPERATION_RISK = {
    AutomationOperation.OBSERVE: OperationRisk.READ_ONLY,
    AutomationOperation.READ_REPOSITORY: OperationRisk.READ_ONLY,
    AutomationOperation.COMMENT: OperationRisk.MUTATION,
    AutomationOperation.LABEL: OperationRisk.MUTATION,
    AutomationOperation.CREATE_ISSUE: OperationRisk.MUTATION,
    AutomationOperation.UPDATE_ISSUE: OperationRisk.MUTATION,
    AutomationOperation.CREATE_BRANCH: OperationRisk.MUTATION,
    AutomationOperation.WRITE_CONTENT: OperationRisk.PRIVILEGED,
    AutomationOperation.CREATE_PULL_REQUEST: OperationRisk.MUTATION,
    AutomationOperation.UPDATE_PULL_REQUEST: OperationRisk.MUTATION,
    AutomationOperation.REQUEST_REVIEW: OperationRisk.MUTATION,
    AutomationOperation.MERGE_PULL_REQUEST: OperationRisk.PRIVILEGED,
    AutomationOperation.DISPATCH_WORKFLOW: OperationRisk.PRIVILEGED,
    AutomationOperation.CANCEL_WORKFLOW: OperationRisk.PRIVILEGED,
    AutomationOperation.DELETE_BRANCH: OperationRisk.DESTRUCTIVE,
    AutomationOperation.RELEASE: OperationRisk.DESTRUCTIVE,
    AutomationOperation.POLICY_CHANGE: OperationRisk.DESTRUCTIVE,
    AutomationOperation.SECRET_READ: OperationRisk.DESTRUCTIVE,
}

_DEFENSE_ACTION = {
    OperationRisk.READ_ONLY: ActionClass.READ,
    OperationRisk.MUTATION: ActionClass.WRITE,
    OperationRisk.PRIVILEGED: ActionClass.EXECUTE,
    OperationRisk.DESTRUCTIVE: ActionClass.POLICY,
}

_OPERATION_CAPABILITY = {
    AutomationOperation.OBSERVE: "resource.read",
    AutomationOperation.READ_REPOSITORY: "resource.read",
    AutomationOperation.COMMENT: "resource.write",
    AutomationOperation.LABEL: "resource.write",
    AutomationOperation.CREATE_ISSUE: "resource.write",
    AutomationOperation.UPDATE_ISSUE: "resource.write",
    AutomationOperation.CREATE_BRANCH: "resource.write",
    AutomationOperation.WRITE_CONTENT: "execution.run",
    AutomationOperation.CREATE_PULL_REQUEST: "resource.write",
    AutomationOperation.UPDATE_PULL_REQUEST: "resource.write",
    AutomationOperation.REQUEST_REVIEW: "resource.write",
    AutomationOperation.MERGE_PULL_REQUEST: "execution.run",
    AutomationOperation.DISPATCH_WORKFLOW: "execution.run",
    AutomationOperation.CANCEL_WORKFLOW: "execution.run",
    AutomationOperation.DELETE_BRANCH: "policy.write",
    AutomationOperation.RELEASE: "policy.write",
    AutomationOperation.POLICY_CHANGE: "policy.write",
    AutomationOperation.SECRET_READ: "policy.write",
}


def _canonical_text(
    value: object,
    *,
    field_name: str,
    limit: int,
    allow_empty: bool = False,
) -> str:
    if not isinstance(value, str):
        raise AutomationControlError(f"{field_name} must be a string")
    if value != value.strip():
        raise AutomationControlError(f"{field_name} must be canonical")
    if not value and not allow_empty:
        raise AutomationControlError(f"{field_name} must not be empty")
    if len(value) > limit:
        raise AutomationControlError(f"{field_name} exceeds maximum length")
    if _CONTROL_RE.search(value):
        raise AutomationControlError(f"{field_name} contains control characters")
    return value


def _permit_id(value: object) -> str:
    text = _canonical_text(value, field_name="permit_id", limit=128)
    if _PERMIT_ID_RE.fullmatch(text) is None:
        raise AutomationControlError("permit_id is invalid")
    return text


def _key_id(value: object) -> str:
    text = _canonical_text(value, field_name="key_id", limit=64)
    if _KEY_ID_RE.fullmatch(text) is None:
        raise AutomationControlError("key_id is invalid")
    return text


def _finite(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AutomationControlError(f"{field_name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise AutomationControlError(f"{field_name} must be finite and non-negative")
    return number


def _positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AutomationControlError(f"{field_name} must be a positive integer")
    return value


def _resource(value: object) -> str:
    return _canonical_text(value, field_name="resource", limit=_MAX_RESOURCE_LENGTH)


def _scope(value: object) -> str:
    text = _canonical_text(value, field_name="resource scope", limit=_MAX_RESOURCE_LENGTH)
    if "*" in text[:-1]:
        raise AutomationControlError("resource wildcard is allowed only as final character")
    if text.endswith("*"):
        prefix = text[:-1]
        if not prefix or prefix[-1] not in {"/", ":", "#"}:
            raise AutomationControlError(
                "wildcard resource scope must end a segment delimiter before *"
            )
    return text


def _scope_matches(scope: str, resource: str) -> bool:
    if scope.endswith("*"):
        return resource.startswith(scope[:-1])
    return hmac.compare_digest(scope, resource)


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise AutomationControlError("permit payload is empty")
    if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        raise AutomationControlError("permit payload is not canonical base64url")
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        raw = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise AutomationControlError("permit payload is invalid base64url") from exc
    if len(raw) > _MAX_TOKEN_BYTES:
        raise AutomationControlError("permit payload exceeds maximum size")
    return raw


def _reject_duplicate_pairs(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise AutomationControlError(f"duplicate permit field: {key}")
        out[key] = value
    return out


@dataclass(frozen=True, slots=True)
class AutomationRequest:
    request_id: str
    nonce: str
    issued_at: float
    operation: AutomationOperation
    resource: str
    actor: ActorIdentity
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _canonical_text(self.request_id, field_name="request_id", limit=128),
        )
        object.__setattr__(
            self,
            "nonce",
            _canonical_text(self.nonce, field_name="nonce", limit=128),
        )
        object.__setattr__(
            self,
            "issued_at",
            _finite(self.issued_at, field_name="issued_at"),
        )
        if not isinstance(self.operation, AutomationOperation):
            try:
                object.__setattr__(
                    self,
                    "operation",
                    AutomationOperation(self.operation),
                )
            except (TypeError, ValueError) as exc:
                raise AutomationControlError("automation operation is invalid") from exc
        object.__setattr__(self, "resource", _resource(self.resource))
        if not isinstance(self.actor, ActorIdentity):
            raise AutomationControlError("actor must be ActorIdentity")
        object.__setattr__(
            self,
            "reason",
            _canonical_text(self.reason, field_name="reason", limit=_MAX_REASON),
        )

    @property
    def risk(self) -> OperationRisk:
        return _OPERATION_RISK[self.operation]

    @property
    def fingerprint(self) -> str:
        payload = {
            "request_id": self.request_id,
            "nonce": self.nonce,
            "issued_at": self.issued_at,
            "operation": self.operation.value,
            "resource": self.resource,
            "actor": self.actor.to_dict(),
            "reason": self.reason,
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class PermitClaims:
    permit_id: str
    key_id: str
    actor_fingerprint: str
    repository: str
    operations: tuple[AutomationOperation, ...]
    resource_scopes: tuple[str, ...]
    issued_at: float
    expires_at: float
    max_uses: int
    generation: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "permit_id", _permit_id(self.permit_id))
        object.__setattr__(self, "key_id", _key_id(self.key_id))
        actor = _canonical_text(
            self.actor_fingerprint,
            field_name="actor_fingerprint",
            limit=64,
        ).casefold()
        if re.fullmatch(r"[0-9a-f]{64}", actor) is None:
            raise AutomationControlError("actor_fingerprint must be sha256 hex")
        object.__setattr__(self, "actor_fingerprint", actor)

        repository = _canonical_text(
            self.repository,
            field_name="repository",
            limit=201,
        )
        if repository.count("/") != 1:
            raise AutomationControlError("repository must be owner/name")
        object.__setattr__(self, "repository", repository)

        operations: list[AutomationOperation] = []
        for item in self.operations:
            try:
                operation = item if isinstance(item, AutomationOperation) else AutomationOperation(item)
            except (TypeError, ValueError) as exc:
                raise AutomationControlError("permit operation is invalid") from exc
            operations.append(operation)
        if not operations or len(operations) > _MAX_OPERATIONS:
            raise AutomationControlError("permit operations are empty or exceed limit")
        if len(set(operations)) != len(operations):
            raise AutomationControlError("permit operations must be unique")
        object.__setattr__(
            self,
            "operations",
            tuple(sorted(operations, key=lambda item: item.value)),
        )

        scopes = tuple(_scope(item) for item in self.resource_scopes)
        if not scopes or len(scopes) > _MAX_RESOURCE_SCOPES:
            raise AutomationControlError("permit resource scopes are empty or exceed limit")
        if len(set(scopes)) != len(scopes):
            raise AutomationControlError("permit resource scopes must be unique")
        object.__setattr__(self, "resource_scopes", tuple(sorted(scopes)))

        issued = _finite(self.issued_at, field_name="permit issued_at")
        expires = _finite(self.expires_at, field_name="permit expires_at")
        if expires <= issued:
            raise AutomationControlError("permit expires_at must be after issued_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(
            self,
            "max_uses",
            _positive_int(self.max_uses, field_name="max_uses"),
        )
        object.__setattr__(
            self,
            "generation",
            _positive_int(self.generation, field_name="generation"),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "v": 1,
            "permit_id": self.permit_id,
            "key_id": self.key_id,
            "actor_fingerprint": self.actor_fingerprint,
            "repository": self.repository,
            "operations": [item.value for item in self.operations],
            "resource_scopes": list(self.resource_scopes),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "max_uses": self.max_uses,
            "generation": self.generation,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "PermitClaims":
        expected = {
            "v",
            "permit_id",
            "key_id",
            "actor_fingerprint",
            "repository",
            "operations",
            "resource_scopes",
            "issued_at",
            "expires_at",
            "max_uses",
            "generation",
        }
        if set(payload) != expected:
            missing = sorted(expected - set(payload))
            extra = sorted(set(payload) - expected)
            raise AutomationControlError(
                f"permit fields mismatch missing={missing} extra={extra}"
            )
        if payload.get("v") != 1:
            raise AutomationControlError("unsupported permit version")
        raw_operations = payload.get("operations")
        raw_scopes = payload.get("resource_scopes")
        if not isinstance(raw_operations, list):
            raise AutomationControlError("permit operations must be an array")
        if not isinstance(raw_scopes, list):
            raise AutomationControlError("permit resource_scopes must be an array")
        return cls(
            permit_id=payload["permit_id"],
            key_id=payload["key_id"],
            actor_fingerprint=payload["actor_fingerprint"],
            repository=payload["repository"],
            operations=tuple(raw_operations),
            resource_scopes=tuple(raw_scopes),
            issued_at=payload["issued_at"],
            expires_at=payload["expires_at"],
            max_uses=payload["max_uses"],
            generation=payload["generation"],
        )


@dataclass(frozen=True, slots=True)
class PermitKey:
    key_id: str
    secret: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", _key_id(self.key_id))
        if not isinstance(self.secret, bytes) or len(self.secret) < 32:
            raise AutomationControlError("permit signing key must be at least 32 bytes")


@dataclass(slots=True)
class PermitAuthority:
    """Issue and verify short-lived automation permits with key rotation."""

    keys: tuple[PermitKey, ...]
    active_key_id: str
    max_ttl_seconds: float = 600.0
    max_future_skew_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.keys:
            raise AutomationControlError("permit authority requires at least one key")
        ids = [item.key_id for item in self.keys]
        if len(ids) != len(set(ids)):
            raise AutomationControlError("permit key ids must be unique")
        self.active_key_id = _key_id(self.active_key_id)
        if self.active_key_id not in ids:
            raise AutomationControlError("active permit key is unavailable")
        for field_name in ("max_ttl_seconds", "max_future_skew_seconds"):
            value = _finite(getattr(self, field_name), field_name=field_name)
            if value <= 0:
                raise AutomationControlError(f"{field_name} must be positive")

    @property
    def _key_map(self) -> dict[str, bytes]:
        return {item.key_id: item.secret for item in self.keys}

    def issue(self, claims: PermitClaims) -> str:
        if claims.key_id != self.active_key_id:
            raise AutomationControlError("new permits must use the active signing key")
        if claims.expires_at - claims.issued_at > self.max_ttl_seconds:
            raise AutomationControlError("permit ttl exceeds authority policy")
        payload = _canonical_json(claims.to_payload())
        if len(payload) > _MAX_TOKEN_BYTES:
            raise AutomationControlError("permit payload exceeds maximum size")
        encoded = _b64encode(payload)
        signing_input = f"v1.{encoded}".encode("ascii")
        secret = self._key_map[claims.key_id]
        signature = hmac.new(secret, signing_input, hashlib.sha256).hexdigest()
        return f"v1.{encoded}.{signature}"

    def verify(
        self,
        token: str,
        *,
        actor: ActorIdentity,
        now: float,
    ) -> PermitClaims:
        raw = _canonical_text(token, field_name="permit token", limit=_MAX_TOKEN_BYTES * 2)
        parts = raw.split(".")
        if len(parts) != 3 or parts[0] != "v1":
            raise AutomationControlError("permit token format is invalid")
        encoded = parts[1]
        signature = parts[2]
        if re.fullmatch(r"[0-9a-f]{64}", signature) is None:
            raise AutomationControlError("permit signature is invalid")

        payload_bytes = _b64decode(encoded)
        try:
            payload = json.loads(
                payload_bytes.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_pairs,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AutomationControlError("permit payload is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AutomationControlError("permit payload must be an object")
        claims = PermitClaims.from_payload(payload)

        secret = self._key_map.get(claims.key_id)
        if secret is None:
            raise AutomationControlError("permit signing key is not trusted")
        signing_input = f"v1.{encoded}".encode("ascii")
        expected = hmac.new(secret, signing_input, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise AutomationControlError("permit signature verification failed")

        moment = _finite(now, field_name="now")
        if claims.issued_at > moment + self.max_future_skew_seconds:
            raise AutomationControlError("permit is issued too far in the future")
        if moment >= claims.expires_at:
            raise AutomationControlError("permit has expired")
        if claims.expires_at - claims.issued_at > self.max_ttl_seconds:
            raise AutomationControlError("permit ttl exceeds authority policy")
        if not hmac.compare_digest(claims.actor_fingerprint, actor.fingerprint):
            raise AutomationControlError("permit actor binding mismatch")
        if claims.repository != actor.repository:
            raise AutomationControlError("permit repository binding mismatch")
        return claims


@dataclass(slots=True)
class PermitUseLedger:
    """Bounded in-memory anti-replay and max-use accounting."""

    max_entries: int = 50_000
    _uses: MutableMapping[str, int] = field(default_factory=dict, init=False)
    _requests: MutableMapping[str, str] = field(default_factory=dict, init=False)
    _order: Deque[tuple[str, str]] = field(default_factory=deque, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def consume(self, claims: PermitClaims, request: AutomationRequest) -> bool:
        key = hashlib.sha256(
            f"{claims.permit_id}\x1f{request.request_id}\x1f{request.nonce}".encode("utf-8")
        ).hexdigest()
        with self._lock:
            if key in self._requests:
                return False
            current = self._uses.get(claims.permit_id, 0)
            if current >= claims.max_uses:
                return False
            self._uses[claims.permit_id] = current + 1
            self._requests[key] = claims.permit_id
            self._order.append((key, claims.permit_id))
            while len(self._order) > self.max_entries:
                old_key, old_permit = self._order.popleft()
                self._requests.pop(old_key, None)
                # Use counts are intentionally not decremented. Eviction of
                # replay-detail cannot resurrect a consumed permit.
                if old_permit not in self._requests.values():
                    # Retain exhausted/use state until explicit reset to avoid
                    # accidental permit resurrection under memory pressure.
                    self._uses.setdefault(old_permit, current)
            return True

    def uses(self, permit_id: str) -> int:
        pid = _permit_id(permit_id)
        with self._lock:
            return self._uses.get(pid, 0)


@dataclass(frozen=True, slots=True)
class AutomationPolicy:
    max_mutations_per_run: int = 20
    max_privileged_per_run: int = 5
    max_destructive_per_run: int = 1
    failure_threshold: int = 4
    breaker_open_seconds: float = 300.0
    half_open_successes: int = 2
    require_permit_for_mutations: bool = True
    allow_destructive: bool = False

    def __post_init__(self) -> None:
        for name in (
            "max_mutations_per_run",
            "max_privileged_per_run",
            "max_destructive_per_run",
            "failure_threshold",
            "half_open_successes",
        ):
            _positive_int(getattr(self, name), field_name=name)
        duration = _finite(self.breaker_open_seconds, field_name="breaker_open_seconds")
        if duration <= 0:
            raise AutomationControlError("breaker_open_seconds must be positive")


@dataclass(slots=True)
class MutationBudget:
    policy: AutomationPolicy
    _counts: MutableMapping[tuple[str, OperationRisk], int] = field(
        default_factory=lambda: defaultdict(int),
        init=False,
    )
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def consume(self, actor: ActorIdentity, risk: OperationRisk) -> bool:
        if risk is OperationRisk.READ_ONLY:
            return True
        key = (actor.fingerprint, risk)
        limit = {
            OperationRisk.MUTATION: self.policy.max_mutations_per_run,
            OperationRisk.PRIVILEGED: self.policy.max_privileged_per_run,
            OperationRisk.DESTRUCTIVE: self.policy.max_destructive_per_run,
        }[risk]
        with self._lock:
            current = self._counts[key]
            if current >= limit:
                return False
            self._counts[key] = current + 1
            return True

    def count(self, actor: ActorIdentity, risk: OperationRisk) -> int:
        with self._lock:
            return self._counts.get((actor.fingerprint, risk), 0)


@dataclass(slots=True)
class CircuitBreaker:
    policy: AutomationPolicy
    clock: Callable[[], float] = time.time
    _state: MutableMapping[str, CircuitState] = field(default_factory=dict, init=False)
    _failures: MutableMapping[str, int] = field(default_factory=lambda: defaultdict(int), init=False)
    _opened_at: MutableMapping[str, float] = field(default_factory=dict, init=False)
    _half_open_success: MutableMapping[str, int] = field(default_factory=lambda: defaultdict(int), init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def state(self, actor: ActorIdentity) -> CircuitState:
        subject = actor.fingerprint
        now = _finite(self.clock(), field_name="clock")
        with self._lock:
            state = self._state.get(subject, CircuitState.CLOSED)
            if state is CircuitState.OPEN:
                opened = self._opened_at.get(subject, now)
                if now - opened >= self.policy.breaker_open_seconds:
                    self._state[subject] = CircuitState.HALF_OPEN
                    self._half_open_success[subject] = 0
                    return CircuitState.HALF_OPEN
            return state

    def allows(self, actor: ActorIdentity) -> bool:
        return self.state(actor) is not CircuitState.OPEN

    def record_failure(self, actor: ActorIdentity) -> CircuitState:
        subject = actor.fingerprint
        now = _finite(self.clock(), field_name="clock")
        with self._lock:
            self._half_open_success[subject] = 0
            self._failures[subject] += 1
            if (
                self._state.get(subject) is CircuitState.HALF_OPEN
                or self._failures[subject] >= self.policy.failure_threshold
            ):
                self._state[subject] = CircuitState.OPEN
                self._opened_at[subject] = now
                return CircuitState.OPEN
            self._state.setdefault(subject, CircuitState.CLOSED)
            return self._state[subject]

    def record_success(self, actor: ActorIdentity) -> CircuitState:
        subject = actor.fingerprint
        with self._lock:
            state = self._state.get(subject, CircuitState.CLOSED)
            if state is CircuitState.HALF_OPEN:
                self._half_open_success[subject] += 1
                if self._half_open_success[subject] >= self.policy.half_open_successes:
                    self._state[subject] = CircuitState.CLOSED
                    self._failures[subject] = 0
                    self._opened_at.pop(subject, None)
                    self._half_open_success[subject] = 0
            elif state is CircuitState.CLOSED:
                self._failures[subject] = 0
            return self._state.get(subject, CircuitState.CLOSED)


@dataclass(frozen=True, slots=True)
class AutomationDecision:
    allowed: bool
    reason: str
    operation: AutomationOperation
    request_fingerprint: str
    risk: OperationRisk
    permit_id: str = ""
    defense_code: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason",
            _canonical_text(self.reason, field_name="decision reason", limit=256),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "operation": self.operation.value,
            "request_fingerprint": self.request_fingerprint,
            "risk": self.risk.value,
            "permit_id": self.permit_id,
            "defense_code": self.defense_code,
        }


@dataclass(frozen=True, slots=True)
class AutomationReceipt:
    sequence: int
    request_fingerprint: str
    allowed: bool
    operation: str
    actor_fingerprint: str
    resource_digest: str
    permit_id: str
    previous_digest: str
    digest: str


@dataclass(slots=True)
class ReceiptLedger:
    max_entries: int = _MAX_LEDGER_ENTRIES
    _entries: Deque[AutomationReceipt] = field(default_factory=deque, init=False)
    _next_sequence: int = field(default=1, init=False)
    _anchor: str = field(default="0" * 64, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def append(
        self,
        request: AutomationRequest,
        decision: AutomationDecision,
    ) -> AutomationReceipt:
        with self._lock:
            previous = self._entries[-1].digest if self._entries else self._anchor
            payload = {
                "sequence": self._next_sequence,
                "request_fingerprint": request.fingerprint,
                "allowed": decision.allowed,
                "operation": request.operation.value,
                "actor_fingerprint": request.actor.fingerprint,
                "resource_digest": hashlib.sha256(
                    request.resource.encode("utf-8")
                ).hexdigest(),
                "permit_id": decision.permit_id,
                "previous_digest": previous,
            }
            digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
            receipt = AutomationReceipt(
                sequence=self._next_sequence,
                request_fingerprint=request.fingerprint,
                allowed=decision.allowed,
                operation=request.operation.value,
                actor_fingerprint=request.actor.fingerprint,
                resource_digest=payload["resource_digest"],
                permit_id=decision.permit_id,
                previous_digest=previous,
                digest=digest,
            )
            self._entries.append(receipt)
            self._next_sequence += 1
            while len(self._entries) > self.max_entries:
                removed = self._entries.popleft()
                self._anchor = removed.digest
            return receipt

    def entries(self) -> tuple[AutomationReceipt, ...]:
        with self._lock:
            return tuple(self._entries)


@dataclass(slots=True)
class AutomationControlPlane:
    """Authorize repository automation with layered fail-closed controls."""

    authority: PermitAuthority
    defense: DefensePlane
    safety: AutomationSafety
    policy: AutomationPolicy = field(default_factory=AutomationPolicy)
    clock: Callable[[], float] = time.time
    uses: PermitUseLedger = field(default_factory=PermitUseLedger)
    budget: MutationBudget | None = None
    breaker: CircuitBreaker | None = None
    receipts: ReceiptLedger = field(default_factory=ReceiptLedger)

    def __post_init__(self) -> None:
        if not isinstance(self.authority, PermitAuthority):
            raise AutomationControlError("authority must be PermitAuthority")
        if not isinstance(self.defense, DefensePlane):
            raise AutomationControlError("defense must be DefensePlane")
        if not isinstance(self.safety, AutomationSafety):
            raise AutomationControlError("safety must be AutomationSafety")
        if not callable(self.clock):
            raise AutomationControlError("clock must be callable")
        if self.budget is None:
            self.budget = MutationBudget(self.policy)
        if self.breaker is None:
            self.breaker = CircuitBreaker(self.policy, clock=self.clock)

    def authorize(
        self,
        request: AutomationRequest,
        *,
        permit_token: str | None = None,
    ) -> AutomationDecision:
        if not isinstance(request, AutomationRequest):
            raise AutomationControlError("request must be AutomationRequest")
        now = _finite(self.clock(), field_name="clock")

        if self.safety.blocked:
            return self._deny(request, f"automation is {self.safety.status}")

        assert self.breaker is not None
        if not self.breaker.allows(request.actor):
            return self._deny(request, "automation circuit breaker is open")

        if request.risk is OperationRisk.DESTRUCTIVE and not self.policy.allow_destructive:
            return self._deny(request, "destructive automation is disabled by policy")

        claims: PermitClaims | None = None
        needs_permit = (
            request.risk is not OperationRisk.READ_ONLY
            and self.policy.require_permit_for_mutations
        )
        if needs_permit:
            if permit_token is None:
                return self._deny(request, "mutating automation requires a permit")
            try:
                claims = self.authority.verify(
                    permit_token,
                    actor=request.actor,
                    now=now,
                )
            except AutomationControlError:
                self.breaker.record_failure(request.actor)
                return self._deny(request, "automation permit verification failed")

            if request.operation not in claims.operations:
                self.breaker.record_failure(request.actor)
                return self._deny(
                    request,
                    "automation permit does not authorize this operation",
                    permit_id=claims.permit_id,
                )
            if not any(
                _scope_matches(scope, request.resource)
                for scope in claims.resource_scopes
            ):
                self.breaker.record_failure(request.actor)
                return self._deny(
                    request,
                    "automation permit does not authorize this resource",
                    permit_id=claims.permit_id,
                )
            if not self.uses.consume(claims, request):
                self.breaker.record_failure(request.actor)
                return self._deny(
                    request,
                    "automation permit is exhausted or replayed",
                    permit_id=claims.permit_id,
                )

        assert self.budget is not None
        if not self.budget.consume(request.actor, request.risk):
            self.breaker.record_failure(request.actor)
            return self._deny(
                request,
                "automation mutation budget is exhausted",
                permit_id="" if claims is None else claims.permit_id,
            )

        capability = _OPERATION_CAPABILITY[request.operation]
        defense_request = SecurityRequest(
            request_id=request.request_id,
            nonce=request.nonce,
            issued_at=request.issued_at,
            action=_DEFENSE_ACTION[request.risk],
            resource=request.resource,
            actor=request.actor,
            capabilities=frozenset({capability}),
            metadata=(
                ("automation_operation", request.operation.value),
                ("permit_id", "" if claims is None else claims.permit_id),
            ),
        )
        try:
            defense_decision = self.defense.evaluate(defense_request)
        except DefenseIntegrityError:
            self.breaker.record_failure(request.actor)
            return self._deny(
                request,
                "repository defense plane rejected automation evidence",
                permit_id="" if claims is None else claims.permit_id,
                defense_code=DecisionCode.DENY_INTEGRITY.value,
            )

        if not defense_decision.allowed:
            self.breaker.record_failure(request.actor)
            return self._deny(
                request,
                "repository defense plane denied automation request",
                permit_id="" if claims is None else claims.permit_id,
                defense_code=defense_decision.code.value,
            )

        decision = AutomationDecision(
            allowed=True,
            reason="automation request is authorized",
            operation=request.operation,
            request_fingerprint=request.fingerprint,
            risk=request.risk,
            permit_id="" if claims is None else claims.permit_id,
            defense_code=defense_decision.code.value,
        )
        self.receipts.append(request, decision)
        return decision

    def record_outcome(
        self,
        request: AutomationRequest,
        *,
        succeeded: bool,
    ) -> CircuitState:
        assert self.breaker is not None
        if succeeded:
            return self.breaker.record_success(request.actor)
        return self.breaker.record_failure(request.actor)

    def _deny(
        self,
        request: AutomationRequest,
        reason: str,
        *,
        permit_id: str = "",
        defense_code: str = "",
    ) -> AutomationDecision:
        decision = AutomationDecision(
            allowed=False,
            reason=reason,
            operation=request.operation,
            request_fingerprint=request.fingerprint,
            risk=request.risk,
            permit_id=permit_id,
            defense_code=defense_code,
        )
        self.receipts.append(request, decision)
        return decision


def build_actor_from_github(
    *,
    subject: str,
    repository: str,
    workflow: str,
    run_id: int,
    run_attempt: int,
    ref: str,
    commit_sha: str,
    event: str,
    trusted: bool,
) -> ActorIdentity:
    """Construct a strict GitHub automation identity.

    Callers must decide whether the trigger is trusted from workflow semantics;
    this helper merely turns that prior determination into immutable identity.
    """

    return ActorIdentity(
        subject=subject,
        source="github-actions",
        repository=repository,
        workflow=workflow,
        run_id=run_id,
        run_attempt=run_attempt,
        ref=ref,
        commit_sha=commit_sha,
        event=event,
        trust=TrustLevel.TRUSTED if trusted else TrustLevel.UNTRUSTED,
    )


__all__ = [
    "AutomationControlError",
    "AutomationControlPlane",
    "AutomationDecision",
    "AutomationOperation",
    "AutomationPolicy",
    "AutomationReceipt",
    "AutomationRequest",
    "CircuitBreaker",
    "CircuitState",
    "MutationBudget",
    "OperationRisk",
    "PermitAuthority",
    "PermitClaims",
    "PermitKey",
    "PermitUseLedger",
    "ReceiptLedger",
    "build_actor_from_github",
]
