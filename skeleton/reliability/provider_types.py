from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class FailureKind(str, Enum):
    """Canonical provider failure classes used across resilience decisions."""

    RATE_LIMIT = "rate_limit"
    QUOTA_EXHAUSTED = "quota_exhausted"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BAD_REQUEST = "bad_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    DNS = "dns"
    TLS = "tls"
    CANCELLED = "cancelled"
    MALFORMED_RESPONSE = "malformed_response"
    RESPONSE_TOO_LARGE = "response_too_large"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    LOCAL_OVERLOAD = "local_overload"
    CIRCUIT_OPEN = "circuit_open"
    BUDGET_EXHAUSTED = "budget_exhausted"
    UNKNOWN = "unknown"


class FailureScope(str, Enum):
    """How broadly a failure should affect routing/admission."""

    REQUEST = "request"
    MODEL = "model"
    PROVIDER = "provider"
    PROJECT = "project"
    ORGANIZATION = "organization"
    LOCAL_PROCESS = "local_process"


class RetryDisposition(str, Enum):
    """Retry semantics independent of any particular provider."""

    RETRY_SAME_ROUTE = "retry_same_route"
    RETRY_FALLBACK_ROUTE = "retry_fallback_route"
    DEFER = "defer"
    FAIL_CLOSED = "fail_closed"
    SUCCEED = "succeed"


class CircuitPhase(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class AdmissionReason(str, Enum):
    ADMITTED = "admitted"
    ROUTE_DISABLED = "route_disabled"
    MISSING_CAPABILITY = "missing_capability"
    MODEL_MISMATCH = "model_mismatch"
    CIRCUIT_OPEN = "circuit_open"
    REQUEST_BUDGET = "request_budget"
    TOKEN_BUDGET = "token_budget"
    CONCURRENCY_BUDGET = "concurrency_budget"
    COOLDOWN = "cooldown"
    HEALTH = "health"
    QUOTA = "quota"
    INVALID_REQUEST = "invalid_request"


class HealthBand(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    QUARANTINED = "quarantined"
    UNKNOWN = "unknown"


class RouteTier(str, Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"
    EMERGENCY = "emergency"


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Capability(str, Enum):
    JSON = "json"
    TOOLS = "tools"
    WEB_SEARCH = "web_search"
    VISION = "vision"
    AUDIO = "audio"
    STRUCTURED_OUTPUT = "structured_output"
    REASONING = "reasoning"
    STREAMING = "streaming"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return ensure_utc(value).isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid datetime: {text!r}") from exc
    return ensure_utc(parsed)


def nonempty(value: Any, *, name: str, limit: int = 512) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if len(text) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    return text


def optional_text(value: Any, *, limit: int = 2048) -> str:
    text = str(value or "").strip()
    return text[:limit]


def finite(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def nonnegative(value: Any, *, name: str) -> float:
    result = finite(value, name=name)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def positive(value: Any, *, name: str) -> float:
    result = finite(value, name=name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def bounded_ratio(value: Any, *, name: str) -> float:
    result = finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return result


def string_tuple(value: Any, *, limit: int = 64, item_limit: int = 256) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        raise ValueError("value must be a sequence of strings")
    result: list[str] = []
    for raw in value[:limit]:
        text = str(raw or "").strip()
        if text and text not in result:
            result.append(text[:item_limit])
    return tuple(result)


def enum_tuple(
    enum_type: type[Enum],
    value: Any,
    *,
    limit: int = 64,
) -> tuple[Enum, ...]:
    raw_values = string_tuple(value, limit=limit)
    result: list[Enum] = []
    for raw in raw_values:
        member = enum_type(raw)
        if member not in result:
            result.append(member)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class RateLimitHints:
    """Provider rate-limit metadata after safe parsing."""

    retry_after_seconds: float | None = None
    request_reset_at: datetime | None = None
    token_reset_at: datetime | None = None
    remaining_requests: int | None = None
    remaining_tokens: int | None = None
    limit_requests: int | None = None
    limit_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.retry_after_seconds is not None:
            object.__setattr__(
                self,
                "retry_after_seconds",
                nonnegative(self.retry_after_seconds, name="retry_after_seconds"),
            )
        for field_name in (
            "remaining_requests",
            "remaining_tokens",
            "limit_requests",
            "limit_tokens",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if parsed < 0:
                raise ValueError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, parsed)
        if self.request_reset_at is not None:
            object.__setattr__(self, "request_reset_at", ensure_utc(self.request_reset_at))
        if self.token_reset_at is not None:
            object.__setattr__(self, "token_reset_at", ensure_utc(self.token_reset_at))

    def earliest_reset(self) -> datetime | None:
        candidates = [
            value
            for value in (self.request_reset_at, self.token_reset_at)
            if value is not None
        ]
        return min(candidates) if candidates else None

    def as_json(self) -> dict[str, Any]:
        return {
            "retry_after_seconds": self.retry_after_seconds,
            "request_reset_at": isoformat(self.request_reset_at),
            "token_reset_at": isoformat(self.token_reset_at),
            "remaining_requests": self.remaining_requests,
            "remaining_tokens": self.remaining_tokens,
            "limit_requests": self.limit_requests,
            "limit_tokens": self.limit_tokens,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "RateLimitHints":
        return cls(
            retry_after_seconds=value.get("retry_after_seconds"),
            request_reset_at=parse_datetime(value.get("request_reset_at")),
            token_reset_at=parse_datetime(value.get("token_reset_at")),
            remaining_requests=value.get("remaining_requests"),
            remaining_tokens=value.get("remaining_tokens"),
            limit_requests=value.get("limit_requests"),
            limit_tokens=value.get("limit_tokens"),
        )


@dataclass(frozen=True, slots=True)
class SafeProviderError:
    """Safe provider error metadata. Raw provider prose is intentionally absent."""

    http_status: int | None = None
    error_code: str = ""
    error_type: str = ""
    request_id: str = ""
    provider: str = ""
    model: str = ""
    hints: RateLimitHints = field(default_factory=RateLimitHints)

    def __post_init__(self) -> None:
        if self.http_status is not None:
            try:
                status = int(self.http_status)
            except (TypeError, ValueError) as exc:
                raise ValueError("http_status must be an integer") from exc
            if not 100 <= status <= 599:
                raise ValueError("http_status must be between 100 and 599")
            object.__setattr__(self, "http_status", status)
        object.__setattr__(self, "error_code", optional_text(self.error_code, limit=160))
        object.__setattr__(self, "error_type", optional_text(self.error_type, limit=160))
        object.__setattr__(self, "request_id", optional_text(self.request_id, limit=200))
        object.__setattr__(self, "provider", optional_text(self.provider, limit=120))
        object.__setattr__(self, "model", optional_text(self.model, limit=200))
        if not isinstance(self.hints, RateLimitHints):
            object.__setattr__(self, "hints", RateLimitHints.from_json(self.hints))

    def as_json(self) -> dict[str, Any]:
        return {
            "http_status": self.http_status,
            "error_code": self.error_code,
            "error_type": self.error_type,
            "request_id": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "hints": self.hints.as_json(),
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "SafeProviderError":
        hints = value.get("hints", {})
        if not isinstance(hints, Mapping):
            hints = {}
        return cls(
            http_status=value.get("http_status"),
            error_code=value.get("error_code", ""),
            error_type=value.get("error_type", ""),
            request_id=value.get("request_id", ""),
            provider=value.get("provider", ""),
            model=value.get("model", ""),
            hints=RateLimitHints.from_json(hints),
        )


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """Normalized provider failure consumed by policy engines."""

    kind: FailureKind
    scope: FailureScope
    retryable: bool
    safe_error: SafeProviderError = field(default_factory=SafeProviderError)
    occurred_at: datetime = field(default_factory=utcnow)
    correlation_id: str = ""
    detail_tag: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FailureKind):
            object.__setattr__(self, "kind", FailureKind(str(self.kind)))
        if not isinstance(self.scope, FailureScope):
            object.__setattr__(self, "scope", FailureScope(str(self.scope)))
        object.__setattr__(self, "retryable", bool(self.retryable))
        object.__setattr__(self, "occurred_at", ensure_utc(self.occurred_at))
        object.__setattr__(
            self,
            "correlation_id",
            optional_text(self.correlation_id, limit=200),
        )
        object.__setattr__(
            self,
            "detail_tag",
            optional_text(self.detail_tag, limit=200),
        )
        if not isinstance(self.safe_error, SafeProviderError):
            object.__setattr__(
                self,
                "safe_error",
                SafeProviderError.from_json(self.safe_error),
            )

    def as_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "scope": self.scope.value,
            "retryable": self.retryable,
            "safe_error": self.safe_error.as_json(),
            "occurred_at": isoformat(self.occurred_at),
            "correlation_id": self.correlation_id,
            "detail_tag": self.detail_tag,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "ProviderFailure":
        safe_error = value.get("safe_error", {})
        if not isinstance(safe_error, Mapping):
            safe_error = {}
        return cls(
            kind=FailureKind(str(value["kind"])),
            scope=FailureScope(str(value["scope"])),
            retryable=bool(value.get("retryable")),
            safe_error=SafeProviderError.from_json(safe_error),
            occurred_at=parse_datetime(value.get("occurred_at")) or utcnow(),
            correlation_id=value.get("correlation_id", ""),
            detail_tag=value.get("detail_tag", ""),
        )


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Capabilities and hard limits advertised by a provider route."""

    capabilities: tuple[Capability, ...] = ()
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    supports_idempotency: bool = True
    supports_retry_after: bool = True

    def __post_init__(self) -> None:
        normalized: list[Capability] = []
        for raw in self.capabilities:
            capability = raw if isinstance(raw, Capability) else Capability(str(raw))
            if capability not in normalized:
                normalized.append(capability)
        object.__setattr__(self, "capabilities", tuple(normalized))
        for field_name in ("max_input_tokens", "max_output_tokens"):
            raw = getattr(self, field_name)
            try:
                parsed = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if parsed < 0:
                raise ValueError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, parsed)

    def has_all(self, required: Iterable[Capability]) -> bool:
        available = set(self.capabilities)
        return all(
            capability if isinstance(capability, Capability) else Capability(str(capability))
            in available
            for capability in required
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "capabilities": [item.value for item in self.capabilities],
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "supports_idempotency": self.supports_idempotency,
            "supports_retry_after": self.supports_retry_after,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "ProviderCapabilities":
        raw = value.get("capabilities", [])
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
            raw = []
        return cls(
            capabilities=tuple(Capability(str(item)) for item in raw),
            max_input_tokens=int(value.get("max_input_tokens", 0)),
            max_output_tokens=int(value.get("max_output_tokens", 0)),
            supports_idempotency=bool(value.get("supports_idempotency", True)),
            supports_retry_after=bool(value.get("supports_retry_after", True)),
        )


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    """One routable provider/model endpoint and its static policy."""

    route_id: str
    provider: str
    model: str
    endpoint: str
    tier: RouteTier = RouteTier.PRIMARY
    enabled: bool = True
    priority: int = 100
    weight: float = 1.0
    capabilities: ProviderCapabilities = field(default_factory=ProviderCapabilities)
    max_concurrency: int = 8
    request_timeout_seconds: float = 45.0
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", nonempty(self.route_id, name="route_id", limit=160))
        object.__setattr__(self, "provider", nonempty(self.provider, name="provider", limit=120))
        object.__setattr__(self, "model", nonempty(self.model, name="model", limit=200))
        object.__setattr__(self, "endpoint", nonempty(self.endpoint, name="endpoint", limit=2048))
        if not isinstance(self.tier, RouteTier):
            object.__setattr__(self, "tier", RouteTier(str(self.tier)))
        try:
            priority = int(self.priority)
        except (TypeError, ValueError) as exc:
            raise ValueError("priority must be an integer") from exc
        if not 0 <= priority <= 10_000:
            raise ValueError("priority must be between 0 and 10000")
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "weight", positive(self.weight, name="weight"))
        try:
            concurrency = int(self.max_concurrency)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_concurrency must be an integer") from exc
        if concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        object.__setattr__(self, "max_concurrency", concurrency)
        object.__setattr__(
            self,
            "request_timeout_seconds",
            positive(self.request_timeout_seconds, name="request_timeout_seconds"),
        )
        object.__setattr__(self, "tags", string_tuple(self.tags, limit=32, item_limit=120))
        if not isinstance(self.capabilities, ProviderCapabilities):
            object.__setattr__(
                self,
                "capabilities",
                ProviderCapabilities.from_json(self.capabilities),
            )

    def identity(self) -> tuple[str, str, str]:
        return (self.provider, self.model, self.endpoint)

    def supports(self, required: Iterable[Capability]) -> bool:
        return self.capabilities.has_all(required)

    def as_json(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "tier": self.tier.value,
            "enabled": self.enabled,
            "priority": self.priority,
            "weight": self.weight,
            "capabilities": self.capabilities.as_json(),
            "max_concurrency": self.max_concurrency,
            "request_timeout_seconds": self.request_timeout_seconds,
            "tags": list(self.tags),
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "ProviderRoute":
        capabilities = value.get("capabilities", {})
        if not isinstance(capabilities, Mapping):
            capabilities = {}
        return cls(
            route_id=value["route_id"],
            provider=value["provider"],
            model=value["model"],
            endpoint=value["endpoint"],
            tier=RouteTier(str(value.get("tier", RouteTier.PRIMARY.value))),
            enabled=bool(value.get("enabled", True)),
            priority=int(value.get("priority", 100)),
            weight=float(value.get("weight", 1.0)),
            capabilities=ProviderCapabilities.from_json(capabilities),
            max_concurrency=int(value.get("max_concurrency", 8)),
            request_timeout_seconds=float(value.get("request_timeout_seconds", 45.0)),
            tags=string_tuple(value.get("tags", ()), limit=32, item_limit=120),
        )


@dataclass(frozen=True, slots=True)
class RetryDecision:
    disposition: RetryDisposition
    delay_seconds: float = 0.0
    route_id: str = ""
    reason: str = ""
    attempt: int = 0
    max_attempts: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, RetryDisposition):
            object.__setattr__(
                self,
                "disposition",
                RetryDisposition(str(self.disposition)),
            )
        object.__setattr__(
            self,
            "delay_seconds",
            nonnegative(self.delay_seconds, name="delay_seconds"),
        )
        object.__setattr__(self, "route_id", optional_text(self.route_id, limit=160))
        object.__setattr__(self, "reason", optional_text(self.reason, limit=300))
        for field_name in ("attempt", "max_attempts"):
            try:
                parsed = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if parsed < 0:
                raise ValueError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, parsed)

    def as_json(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "delay_seconds": self.delay_seconds,
            "route_id": self.route_id,
            "reason": self.reason,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    allowed: bool
    reason: AdmissionReason
    route_id: str = ""
    retry_at: datetime | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.reason, AdmissionReason):
            object.__setattr__(self, "reason", AdmissionReason(str(self.reason)))
        object.__setattr__(self, "allowed", bool(self.allowed))
        object.__setattr__(self, "route_id", optional_text(self.route_id, limit=160))
        object.__setattr__(self, "detail", optional_text(self.detail, limit=300))
        if self.retry_at is not None:
            object.__setattr__(self, "retry_at", ensure_utc(self.retry_at))
        if self.allowed and self.reason is not AdmissionReason.ADMITTED:
            raise ValueError("allowed admission decisions must use reason=admitted")
        if not self.allowed and self.reason is AdmissionReason.ADMITTED:
            raise ValueError("rejected admission decisions cannot use reason=admitted")

    def as_json(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason.value,
            "route_id": self.route_id,
            "retry_at": isoformat(self.retry_at),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_id: str
    correlation_id: str
    route_id: str
    started_at: datetime
    finished_at: datetime
    status: OutcomeStatus
    latency_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    failure: ProviderFailure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempt_id", nonempty(self.attempt_id, name="attempt_id", limit=200))
        object.__setattr__(
            self,
            "correlation_id",
            nonempty(self.correlation_id, name="correlation_id", limit=200),
        )
        object.__setattr__(self, "route_id", nonempty(self.route_id, name="route_id", limit=160))
        object.__setattr__(self, "started_at", ensure_utc(self.started_at))
        object.__setattr__(self, "finished_at", ensure_utc(self.finished_at))
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if not isinstance(self.status, OutcomeStatus):
            object.__setattr__(self, "status", OutcomeStatus(str(self.status)))
        object.__setattr__(
            self,
            "latency_seconds",
            nonnegative(self.latency_seconds, name="latency_seconds"),
        )
        for field_name in ("input_tokens", "output_tokens"):
            try:
                parsed = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if parsed < 0:
                raise ValueError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, parsed)
        if self.status is OutcomeStatus.FAILURE and self.failure is None:
            raise ValueError("failed attempts require failure metadata")
        if self.status is OutcomeStatus.SUCCESS and self.failure is not None:
            raise ValueError("successful attempts cannot carry a failure")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_json(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "correlation_id": self.correlation_id,
            "route_id": self.route_id,
            "started_at": isoformat(self.started_at),
            "finished_at": isoformat(self.finished_at),
            "status": self.status.value,
            "latency_seconds": self.latency_seconds,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "failure": self.failure.as_json() if self.failure else None,
        }

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "AttemptRecord":
        failure_raw = value.get("failure")
        failure = (
            ProviderFailure.from_json(failure_raw)
            if isinstance(failure_raw, Mapping)
            else None
        )
        return cls(
            attempt_id=value["attempt_id"],
            correlation_id=value["correlation_id"],
            route_id=value["route_id"],
            started_at=parse_datetime(value["started_at"]) or utcnow(),
            finished_at=parse_datetime(value["finished_at"]) or utcnow(),
            status=OutcomeStatus(str(value["status"])),
            latency_seconds=float(value.get("latency_seconds", 0.0)),
            input_tokens=int(value.get("input_tokens", 0)),
            output_tokens=int(value.get("output_tokens", 0)),
            failure=failure,
        )


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    route_id: str
    captured_at: datetime
    request_limit: int
    requests_used: int
    token_limit: int
    tokens_used: int
    concurrency_limit: int
    concurrency_used: int
    window_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", nonempty(self.route_id, name="route_id", limit=160))
        object.__setattr__(self, "captured_at", ensure_utc(self.captured_at))
        for field_name in (
            "request_limit",
            "requests_used",
            "token_limit",
            "tokens_used",
            "concurrency_limit",
            "concurrency_used",
        ):
            try:
                parsed = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if parsed < 0:
                raise ValueError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, parsed)
        object.__setattr__(
            self,
            "window_seconds",
            positive(self.window_seconds, name="window_seconds"),
        )

    @property
    def request_remaining(self) -> int:
        return max(0, self.request_limit - self.requests_used)

    @property
    def token_remaining(self) -> int:
        return max(0, self.token_limit - self.tokens_used)

    @property
    def concurrency_remaining(self) -> int:
        return max(0, self.concurrency_limit - self.concurrency_used)

    def as_json(self) -> dict[str, Any]:
        result = asdict(self)
        result["captured_at"] = isoformat(self.captured_at)
        return result


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    route_id: str
    phase: CircuitPhase
    captured_at: datetime
    consecutive_failures: int = 0
    recent_failures: int = 0
    recent_successes: int = 0
    opened_at: datetime | None = None
    retry_at: datetime | None = None
    probe_in_flight: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", nonempty(self.route_id, name="route_id", limit=160))
        if not isinstance(self.phase, CircuitPhase):
            object.__setattr__(self, "phase", CircuitPhase(str(self.phase)))
        object.__setattr__(self, "captured_at", ensure_utc(self.captured_at))
        for field_name in (
            "consecutive_failures",
            "recent_failures",
            "recent_successes",
        ):
            try:
                parsed = int(getattr(self, field_name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name} must be an integer") from exc
            if parsed < 0:
                raise ValueError(f"{field_name} must be non-negative")
            object.__setattr__(self, field_name, parsed)
        if self.opened_at is not None:
            object.__setattr__(self, "opened_at", ensure_utc(self.opened_at))
        if self.retry_at is not None:
            object.__setattr__(self, "retry_at", ensure_utc(self.retry_at))

    def as_json(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "phase": self.phase.value,
            "captured_at": isoformat(self.captured_at),
            "consecutive_failures": self.consecutive_failures,
            "recent_failures": self.recent_failures,
            "recent_successes": self.recent_successes,
            "opened_at": isoformat(self.opened_at),
            "retry_at": isoformat(self.retry_at),
            "probe_in_flight": self.probe_in_flight,
        }


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    route_id: str
    captured_at: datetime
    band: HealthBand
    score: float
    success_rate: float
    timeout_rate: float
    rate_limit_rate: float
    p50_latency_seconds: float
    p95_latency_seconds: float
    sample_count: int
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "route_id", nonempty(self.route_id, name="route_id", limit=160))
        object.__setattr__(self, "captured_at", ensure_utc(self.captured_at))
        if not isinstance(self.band, HealthBand):
            object.__setattr__(self, "band", HealthBand(str(self.band)))
        object.__setattr__(self, "score", bounded_ratio(self.score, name="score"))
        object.__setattr__(
            self,
            "success_rate",
            bounded_ratio(self.success_rate, name="success_rate"),
        )
        object.__setattr__(
            self,
            "timeout_rate",
            bounded_ratio(self.timeout_rate, name="timeout_rate"),
        )
        object.__setattr__(
            self,
            "rate_limit_rate",
            bounded_ratio(self.rate_limit_rate, name="rate_limit_rate"),
        )
        object.__setattr__(
            self,
            "p50_latency_seconds",
            nonnegative(self.p50_latency_seconds, name="p50_latency_seconds"),
        )
        object.__setattr__(
            self,
            "p95_latency_seconds",
            nonnegative(self.p95_latency_seconds, name="p95_latency_seconds"),
        )
        try:
            sample_count = int(self.sample_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("sample_count must be an integer") from exc
        if sample_count < 0:
            raise ValueError("sample_count must be non-negative")
        object.__setattr__(self, "sample_count", sample_count)
        if self.last_success_at is not None:
            object.__setattr__(self, "last_success_at", ensure_utc(self.last_success_at))
        if self.last_failure_at is not None:
            object.__setattr__(self, "last_failure_at", ensure_utc(self.last_failure_at))

    def as_json(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "captured_at": isoformat(self.captured_at),
            "band": self.band.value,
            "score": self.score,
            "success_rate": self.success_rate,
            "timeout_rate": self.timeout_rate,
            "rate_limit_rate": self.rate_limit_rate,
            "p50_latency_seconds": self.p50_latency_seconds,
            "p95_latency_seconds": self.p95_latency_seconds,
            "sample_count": self.sample_count,
            "last_success_at": isoformat(self.last_success_at),
            "last_failure_at": isoformat(self.last_failure_at),
        }


@dataclass(frozen=True, slots=True)
class RouteDecision:
    route: ProviderRoute | None
    admitted: bool
    reason: AdmissionReason
    considered: tuple[str, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()
    score: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "admitted", bool(self.admitted))
        if not isinstance(self.reason, AdmissionReason):
            object.__setattr__(self, "reason", AdmissionReason(str(self.reason)))
        object.__setattr__(
            self,
            "considered",
            string_tuple(self.considered, limit=128, item_limit=160),
        )
        normalized_rejected: list[tuple[str, str]] = []
        for item in self.rejected[:128]:
            if len(item) != 2:
                raise ValueError("rejected entries must contain route_id and reason")
            route_id = optional_text(item[0], limit=160)
            reason = optional_text(item[1], limit=200)
            normalized_rejected.append((route_id, reason))
        object.__setattr__(self, "rejected", tuple(normalized_rejected))
        object.__setattr__(self, "score", finite(self.score, name="score"))
        if self.admitted and self.route is None:
            raise ValueError("admitted route decisions require a route")
        if self.admitted and self.reason is not AdmissionReason.ADMITTED:
            raise ValueError("admitted route decisions must use admitted reason")

    def as_json(self) -> dict[str, Any]:
        return {
            "route": self.route.as_json() if self.route else None,
            "admitted": self.admitted,
            "reason": self.reason.value,
            "considered": list(self.considered),
            "rejected": [list(item) for item in self.rejected],
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class ResilienceEvent:
    """One append-only safe event emitted by the provider control plane."""

    sequence: int
    event_id: str
    kind: str
    occurred_at: datetime
    route_id: str = ""
    correlation_id: str = ""
    attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        try:
            sequence = int(self.sequence)
        except (TypeError, ValueError) as exc:
            raise ValueError("sequence must be an integer") from exc
        if sequence < 0:
            raise ValueError("sequence must be non-negative")
        object.__setattr__(self, "sequence", sequence)
        object.__setattr__(self, "event_id", nonempty(self.event_id, name="event_id", limit=200))
        object.__setattr__(self, "kind", nonempty(self.kind, name="kind", limit=120))
        object.__setattr__(self, "occurred_at", ensure_utc(self.occurred_at))
        object.__setattr__(self, "route_id", optional_text(self.route_id, limit=160))
        object.__setattr__(
            self,
            "correlation_id",
            optional_text(self.correlation_id, limit=200),
        )
        normalized: list[tuple[str, str]] = []
        for pair in self.attributes[:64]:
            if len(pair) != 2:
                raise ValueError("attributes must be key/value pairs")
            key = nonempty(pair[0], name="attribute key", limit=120)
            value = optional_text(pair[1], limit=500)
            normalized.append((key, value))
        object.__setattr__(self, "attributes", tuple(normalized))

    def attribute_map(self) -> dict[str, str]:
        return dict(self.attributes)

    def as_json(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "kind": self.kind,
            "occurred_at": isoformat(self.occurred_at),
            "route_id": self.route_id,
            "correlation_id": self.correlation_id,
            "attributes": [[key, value] for key, value in self.attributes],
        }


def replace_route(route: ProviderRoute, **changes: Any) -> ProviderRoute:
    """Typed wrapper used by policy layers when deriving effective routes."""

    return replace(route, **changes)


def routes_by_id(routes: Iterable[ProviderRoute]) -> dict[str, ProviderRoute]:
    result: dict[str, ProviderRoute] = {}
    for route in routes:
        if route.route_id in result:
            raise ValueError(f"duplicate route_id: {route.route_id}")
        result[route.route_id] = route
    return result


def validate_route_catalog(routes: Iterable[ProviderRoute]) -> tuple[ProviderRoute, ...]:
    catalog = tuple(routes)
    routes_by_id(catalog)
    identities: set[tuple[str, str, str]] = set()
    for route in catalog:
        identity = route.identity()
        if identity in identities:
            raise ValueError(
                "duplicate provider/model/endpoint identity: "
                + "/".join(identity)
            )
        identities.add(identity)
    return catalog


__all__ = [
    "AdmissionDecision",
    "AdmissionReason",
    "AttemptRecord",
    "BudgetSnapshot",
    "Capability",
    "CircuitPhase",
    "CircuitSnapshot",
    "FailureKind",
    "FailureScope",
    "HealthBand",
    "HealthSnapshot",
    "OutcomeStatus",
    "ProviderCapabilities",
    "ProviderFailure",
    "ProviderRoute",
    "RateLimitHints",
    "ResilienceEvent",
    "RetryDecision",
    "RetryDisposition",
    "RouteDecision",
    "RouteTier",
    "SafeProviderError",
    "bounded_ratio",
    "ensure_utc",
    "finite",
    "isoformat",
    "nonempty",
    "nonnegative",
    "optional_text",
    "parse_datetime",
    "positive",
    "replace_route",
    "routes_by_id",
    "string_tuple",
    "utcnow",
    "validate_route_catalog",
]
