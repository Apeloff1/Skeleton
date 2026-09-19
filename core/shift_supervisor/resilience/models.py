from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


MAX_TEXT = 2_000
MAX_IDENTIFIER = 240
MAX_TAGS = 32
MAX_CAPABILITIES = 16
MAX_METADATA_ITEMS = 48
MAX_HISTORY_ITEMS = 256


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def bounded_text(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value or "").strip()[: max(0, int(limit))]


def bounded_identifier(value: Any) -> str:
    return bounded_text(value, MAX_IDENTIFIER)


def nonnegative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return max(0, int(default))


def positive_int(value: Any, default: int = 1) -> int:
    return max(1, nonnegative_int(value, default))


def nonnegative_float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError, OverflowError):
        return max(0.0, float(default))


def bounded_float(
    value: Any,
    *,
    minimum: float,
    maximum: float,
    default: float,
) -> float:
    parsed = nonnegative_float(value, default)
    return max(minimum, min(parsed, maximum))


def bounded_strings(
    values: Iterable[Any] | None,
    *,
    limit: int = MAX_TAGS,
    item_limit: int = MAX_IDENTIFIER,
) -> tuple[str, ...]:
    if values is None:
        return ()
    result: list[str] = []
    for value in values:
        text = bounded_text(value, item_limit)
        if not text or text in result:
            continue
        result.append(text)
        if len(result) >= limit:
            break
    return tuple(result)


def bounded_metadata(
    value: Mapping[str, Any] | None,
    *,
    limit: int = MAX_METADATA_ITEMS,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for raw_key, raw_value in list(value.items())[:limit]:
        key = bounded_text(raw_key, 100)
        if not key:
            continue
        if raw_value is None or isinstance(raw_value, (bool, int, float)):
            result[key] = raw_value
        elif isinstance(raw_value, str):
            result[key] = bounded_text(raw_value, MAX_TEXT)
        elif isinstance(raw_value, (list, tuple, set, frozenset)):
            result[key] = list(
                bounded_strings(raw_value, limit=24, item_limit=500)
            )
        elif isinstance(raw_value, Mapping):
            nested: dict[str, Any] = {}
            for nested_key, nested_value in list(raw_value.items())[:16]:
                name = bounded_text(nested_key, 100)
                if not name:
                    continue
                if nested_value is None or isinstance(
                    nested_value,
                    (bool, int, float),
                ):
                    nested[name] = nested_value
                else:
                    nested[name] = bounded_text(nested_value, 500)
            result[key] = nested
        else:
            result[key] = bounded_text(raw_value, 500)
    return result


class FailureDomain(str, Enum):
    PROVIDER = "provider"
    TRANSPORT = "transport"
    RESPONSE = "response"
    CONFIGURATION = "configuration"
    CAPABILITY = "capability"
    POLICY = "policy"
    INTERNAL = "internal"


class FailureClass(str, Enum):
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    MODEL_ACCESS = "model_access"
    NOT_FOUND = "not_found"
    BAD_REQUEST = "bad_request"
    CONFLICT = "conflict"
    SERVER = "server"
    NETWORK = "network"
    TIMEOUT = "timeout"
    DECODE = "decode"
    CONTRACT = "contract"
    PAYLOAD_LIMIT = "payload_limit"
    TOOL_LIMIT = "tool_limit"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class RetryAction(str, Enum):
    RETRY_PRIMARY = "retry_primary"
    RETRY_FALLBACK = "retry_fallback"
    DEFER = "defer"
    FAIL_FAST = "fail_fast"
    OPEN_CIRCUIT = "open_circuit"
    SUCCEED = "succeed"


class CircuitPhase(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BackpressureAction(str, Enum):
    PROCEED = "proceed"
    DEFER = "defer"
    SAFE_NOOP = "safe_noop"
    FAIL_CLOSED = "fail_closed"


class HealthGrade(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class Capability(str, Enum):
    JSON_OBJECT = "json_object"
    WEB_SEARCH = "web_search"
    FUNCTION_CALLING = "function_calling"
    LARGE_CONTEXT = "large_context"
    HIGH_OUTPUT = "high_output"
    REASONING = "reasoning"
    IMAGE_INPUT = "image_input"
    FILE_SEARCH = "file_search"
    COMPUTER_USE = "computer_use"


@dataclass(frozen=True, slots=True)
class RateLimitHints:
    retry_after_seconds: float | None = None
    request_reset_seconds: float | None = None
    token_reset_seconds: float | None = None
    remaining_requests: int | None = None
    remaining_tokens: int | None = None
    limit_requests: int | None = None
    limit_tokens: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "retry_after_seconds",
            "request_reset_seconds",
            "token_reset_seconds",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in (
            "remaining_requests",
            "remaining_tokens",
            "limit_requests",
            "limit_tokens",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")

    @property
    def strongest_cooldown_seconds(self) -> float | None:
        values = [
            value
            for value in (
                self.retry_after_seconds,
                self.request_reset_seconds,
                self.token_reset_seconds,
            )
            if value is not None
        ]
        return max(values) if values else None

    def with_cap(self, maximum: float) -> "RateLimitHints":
        cap = max(0.0, float(maximum))

        def clipped(value: float | None) -> float | None:
            if value is None:
                return None
            return min(max(0.0, value), cap)

        return replace(
            self,
            retry_after_seconds=clipped(self.retry_after_seconds),
            request_reset_seconds=clipped(self.request_reset_seconds),
            token_reset_seconds=clipped(self.token_reset_seconds),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "retry_after_seconds": self.retry_after_seconds,
            "request_reset_seconds": self.request_reset_seconds,
            "token_reset_seconds": self.token_reset_seconds,
            "remaining_requests": self.remaining_requests,
            "remaining_tokens": self.remaining_tokens,
            "limit_requests": self.limit_requests,
            "limit_tokens": self.limit_tokens,
        }


@dataclass(frozen=True, slots=True)
class SafeProviderError:
    failure_class: FailureClass
    domain: FailureDomain
    http_status: int | None = None
    error_code: str = ""
    error_type: str = ""
    request_id: str = ""
    operation: str = ""
    retryable: bool = False
    safe_message: str = ""
    rate_limit: RateLimitHints = field(default_factory=RateLimitHints)
    occurred_at: datetime = field(default_factory=utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.http_status is not None and not (100 <= self.http_status <= 599):
            raise ValueError("http_status must be a valid HTTP status")
        object.__setattr__(self, "error_code", bounded_identifier(self.error_code))
        object.__setattr__(self, "error_type", bounded_identifier(self.error_type))
        object.__setattr__(self, "request_id", bounded_identifier(self.request_id))
        object.__setattr__(self, "operation", bounded_identifier(self.operation))
        object.__setattr__(self, "safe_message", bounded_text(self.safe_message))
        object.__setattr__(self, "occurred_at", ensure_utc(self.occurred_at))
        object.__setattr__(self, "metadata", bounded_metadata(self.metadata))

    @property
    def is_rate_limited(self) -> bool:
        return self.failure_class is FailureClass.RATE_LIMIT

    @property
    def is_fail_fast(self) -> bool:
        return self.failure_class in {
            FailureClass.QUOTA,
            FailureClass.AUTHENTICATION,
            FailureClass.AUTHORIZATION,
            FailureClass.MODEL_ACCESS,
            FailureClass.BAD_REQUEST,
            FailureClass.CONTRACT,
            FailureClass.PAYLOAD_LIMIT,
            FailureClass.TOOL_LIMIT,
        }

    @property
    def fingerprint(self) -> tuple[str, str, int | None, str, str]:
        return (
            self.failure_class.value,
            self.domain.value,
            self.http_status,
            self.error_code,
            self.error_type,
        )

    def summary(self) -> str:
        parts = [self.failure_class.value]
        if self.http_status is not None:
            parts.append(f"http={self.http_status}")
        if self.error_code:
            parts.append(f"code={self.error_code}")
        if self.error_type:
            parts.append(f"type={self.error_type}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class.value,
            "domain": self.domain.value,
            "http_status": self.http_status,
            "error_code": self.error_code,
            "error_type": self.error_type,
            "request_id": self.request_id,
            "operation": self.operation,
            "retryable": self.retryable,
            "safe_message": self.safe_message,
            "rate_limit": self.rate_limit.to_dict(),
            "occurred_at": self.occurred_at.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AttemptBudget:
    max_attempts: int = 6
    primary_attempts: int = 3
    max_total_delay_seconds: float = 90.0
    max_single_delay_seconds: float = 30.0
    deadline_seconds: float = 180.0
    max_fallback_models: int = 2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if self.primary_attempts < 1:
            raise ValueError("primary_attempts must be positive")
        if self.primary_attempts > self.max_attempts:
            raise ValueError("primary_attempts cannot exceed max_attempts")
        if self.max_total_delay_seconds < 0:
            raise ValueError("max_total_delay_seconds must be non-negative")
        if self.max_single_delay_seconds < 0:
            raise ValueError("max_single_delay_seconds must be non-negative")
        if self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be positive")
        if self.max_fallback_models < 0:
            raise ValueError("max_fallback_models must be non-negative")

    @property
    def fallback_attempts(self) -> int:
        return max(0, self.max_attempts - self.primary_attempts)

    def clamp_delay(self, value: float) -> float:
        return min(max(0.0, float(value)), self.max_single_delay_seconds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "primary_attempts": self.primary_attempts,
            "fallback_attempts": self.fallback_attempts,
            "max_total_delay_seconds": self.max_total_delay_seconds,
            "max_single_delay_seconds": self.max_single_delay_seconds,
            "deadline_seconds": self.deadline_seconds,
            "max_fallback_models": self.max_fallback_models,
        }


@dataclass(frozen=True, slots=True)
class ProviderEndpoint:
    provider: str
    endpoint: str
    region: str = ""
    tenant: str = ""
    capabilities: frozenset[Capability] = frozenset()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        provider = bounded_identifier(self.provider)
        endpoint = bounded_text(self.endpoint, 1_000)
        if not provider:
            raise ValueError("provider is required")
        if not endpoint:
            raise ValueError("endpoint is required")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "endpoint", endpoint)
        object.__setattr__(self, "region", bounded_identifier(self.region))
        object.__setattr__(self, "tenant", bounded_identifier(self.tenant))
        object.__setattr__(
            self,
            "capabilities",
            frozenset(list(self.capabilities)[:MAX_CAPABILITIES]),
        )
        object.__setattr__(self, "tags", bounded_strings(self.tags))

    @property
    def key(self) -> str:
        region = f":{self.region}" if self.region else ""
        tenant = f":{self.tenant}" if self.tenant else ""
        return f"{self.provider}{region}{tenant}:{self.endpoint}"

    def supports(self, requirements: Iterable[Capability]) -> bool:
        required = set(requirements)
        return required.issubset(self.capabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "region": self.region,
            "tenant": self.tenant,
            "capabilities": sorted(value.value for value in self.capabilities),
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    model: str
    endpoint: ProviderEndpoint
    priority: int = 100
    capabilities: frozenset[Capability] = frozenset()
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    enabled: bool = True
    cost_rank: int = 100
    quality_rank: int = 100
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        model = bounded_identifier(self.model)
        if not model:
            raise ValueError("model is required")
        if self.priority < 0:
            raise ValueError("priority must be non-negative")
        if self.cost_rank < 0 or self.quality_rank < 0:
            raise ValueError("rank values must be non-negative")
        if self.max_input_tokens is not None and self.max_input_tokens < 1:
            raise ValueError("max_input_tokens must be positive")
        if self.max_output_tokens is not None and self.max_output_tokens < 1:
            raise ValueError("max_output_tokens must be positive")
        object.__setattr__(self, "model", model)
        object.__setattr__(
            self,
            "capabilities",
            frozenset(list(self.capabilities)[:MAX_CAPABILITIES]),
        )
        object.__setattr__(self, "metadata", bounded_metadata(self.metadata))

    @property
    def key(self) -> str:
        return f"{self.endpoint.key}::{self.model}"

    @property
    def all_capabilities(self) -> frozenset[Capability]:
        return frozenset(set(self.endpoint.capabilities) | set(self.capabilities))

    def supports(self, requirements: "RequestRequirements") -> bool:
        if not self.enabled:
            return False
        if not requirements.capabilities.issubset(self.all_capabilities):
            return False
        if (
            requirements.input_tokens is not None
            and self.max_input_tokens is not None
            and requirements.input_tokens > self.max_input_tokens
        ):
            return False
        if (
            requirements.output_tokens is not None
            and self.max_output_tokens is not None
            and requirements.output_tokens > self.max_output_tokens
        ):
            return False
        if requirements.provider_allowlist and (
            self.endpoint.provider not in requirements.provider_allowlist
        ):
            return False
        if requirements.model_allowlist and self.model not in requirements.model_allowlist:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "endpoint": self.endpoint.to_dict(),
            "priority": self.priority,
            "capabilities": sorted(value.value for value in self.capabilities),
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "enabled": self.enabled,
            "cost_rank": self.cost_rank,
            "quality_rank": self.quality_rank,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RequestRequirements:
    capabilities: frozenset[Capability] = frozenset()
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_allowlist: tuple[str, ...] = ()
    model_allowlist: tuple[str, ...] = ()
    require_same_provider: bool = False
    require_primary_model: bool = False
    allow_degraded_health: bool = True

    def __post_init__(self) -> None:
        if self.input_tokens is not None and self.input_tokens < 0:
            raise ValueError("input_tokens must be non-negative")
        if self.output_tokens is not None and self.output_tokens < 0:
            raise ValueError("output_tokens must be non-negative")
        object.__setattr__(
            self,
            "capabilities",
            frozenset(list(self.capabilities)[:MAX_CAPABILITIES]),
        )
        object.__setattr__(
            self,
            "provider_allowlist",
            bounded_strings(self.provider_allowlist),
        )
        object.__setattr__(
            self,
            "model_allowlist",
            bounded_strings(self.model_allowlist),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": sorted(value.value for value in self.capabilities),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "provider_allowlist": list(self.provider_allowlist),
            "model_allowlist": list(self.model_allowlist),
            "require_same_provider": self.require_same_provider,
            "require_primary_model": self.require_primary_model,
            "allow_degraded_health": self.allow_degraded_health,
        }


@dataclass(frozen=True, slots=True)
class AttemptPlan:
    attempt_number: int
    candidate: ModelCandidate
    action: RetryAction
    delay_seconds: float = 0.0
    reason: str = ""
    deadline_at: datetime | None = None
    idempotency_key: str = ""
    previous_failure: SafeProviderError | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        object.__setattr__(self, "reason", bounded_text(self.reason, 500))
        object.__setattr__(
            self,
            "idempotency_key",
            bounded_text(self.idempotency_key, 500),
        )
        if self.deadline_at is not None:
            object.__setattr__(self, "deadline_at", ensure_utc(self.deadline_at))

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "candidate": self.candidate.to_dict(),
            "action": self.action.value,
            "delay_seconds": self.delay_seconds,
            "reason": self.reason,
            "deadline_at": (
                self.deadline_at.isoformat()
                if self.deadline_at is not None
                else None
            ),
            "idempotency_key": self.idempotency_key,
            "previous_failure": (
                self.previous_failure.to_dict()
                if self.previous_failure is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    correlation_id: str
    attempt_number: int
    candidate_key: str
    model: str
    provider: str
    started_at: datetime
    finished_at: datetime
    action: RetryAction
    success: bool
    delay_before_seconds: float = 0.0
    failure: SafeProviderError | None = None
    response_bytes: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        started = ensure_utc(self.started_at)
        finished = ensure_utc(self.finished_at)
        if finished < started:
            raise ValueError("finished_at cannot precede started_at")
        object.__setattr__(self, "correlation_id", bounded_identifier(self.correlation_id))
        object.__setattr__(self, "candidate_key", bounded_text(self.candidate_key, 1_000))
        object.__setattr__(self, "model", bounded_identifier(self.model))
        object.__setattr__(self, "provider", bounded_identifier(self.provider))
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "finished_at", finished)
        object.__setattr__(
            self,
            "delay_before_seconds",
            nonnegative_float(self.delay_before_seconds),
        )
        if self.response_bytes is not None and self.response_bytes < 0:
            raise ValueError("response_bytes must be non-negative")
        if self.input_tokens is not None and self.input_tokens < 0:
            raise ValueError("input_tokens must be non-negative")
        if self.output_tokens is not None and self.output_tokens < 0:
            raise ValueError("output_tokens must be non-negative")
        object.__setattr__(self, "metadata", bounded_metadata(self.metadata))

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, (self.finished_at - self.started_at).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "attempt_number": self.attempt_number,
            "candidate_key": self.candidate_key,
            "model": self.model,
            "provider": self.provider,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "elapsed_seconds": self.elapsed_seconds,
            "action": self.action.value,
            "success": self.success,
            "delay_before_seconds": self.delay_before_seconds,
            "failure": self.failure.to_dict() if self.failure else None,
            "response_bytes": self.response_bytes,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    key: str
    phase: CircuitPhase
    consecutive_failures: int = 0
    recent_failures: int = 0
    recent_successes: int = 0
    opened_at: datetime | None = None
    cooldown_until: datetime | None = None
    half_open_probes: int = 0
    last_failure: SafeProviderError | None = None
    last_success_at: datetime | None = None
    generation: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", bounded_text(self.key, 1_000))
        for name in (
            "consecutive_failures",
            "recent_failures",
            "recent_successes",
            "half_open_probes",
            "generation",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.opened_at is not None:
            object.__setattr__(self, "opened_at", ensure_utc(self.opened_at))
        if self.cooldown_until is not None:
            object.__setattr__(
                self,
                "cooldown_until",
                ensure_utc(self.cooldown_until),
            )
        if self.last_success_at is not None:
            object.__setattr__(
                self,
                "last_success_at",
                ensure_utc(self.last_success_at),
            )

    def is_available(self, at: datetime | None = None) -> bool:
        moment = ensure_utc(at or utcnow())
        if self.phase is CircuitPhase.CLOSED:
            return True
        if self.phase is CircuitPhase.HALF_OPEN:
            return self.half_open_probes == 0
        if self.cooldown_until is None:
            return False
        return moment >= self.cooldown_until

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "phase": self.phase.value,
            "consecutive_failures": self.consecutive_failures,
            "recent_failures": self.recent_failures,
            "recent_successes": self.recent_successes,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "cooldown_until": (
                self.cooldown_until.isoformat()
                if self.cooldown_until
                else None
            ),
            "half_open_probes": self.half_open_probes,
            "last_failure": (
                self.last_failure.to_dict()
                if self.last_failure is not None
                else None
            ),
            "last_success_at": (
                self.last_success_at.isoformat()
                if self.last_success_at
                else None
            ),
            "generation": self.generation,
        }


@dataclass(frozen=True, slots=True)
class ModelHealth:
    candidate_key: str
    grade: HealthGrade
    success_rate: float | None = None
    average_latency_seconds: float | None = None
    recent_requests: int = 0
    recent_failures: int = 0
    rate_limit_failures: int = 0
    quota_failures: int = 0
    circuit: CircuitSnapshot | None = None
    cooldown_until: datetime | None = None
    observed_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_key",
            bounded_text(self.candidate_key, 1_000),
        )
        if self.success_rate is not None and not 0.0 <= self.success_rate <= 1.0:
            raise ValueError("success_rate must be between 0 and 1")
        if (
            self.average_latency_seconds is not None
            and self.average_latency_seconds < 0
        ):
            raise ValueError("average_latency_seconds must be non-negative")
        for name in (
            "recent_requests",
            "recent_failures",
            "rate_limit_failures",
            "quota_failures",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.cooldown_until is not None:
            object.__setattr__(
                self,
                "cooldown_until",
                ensure_utc(self.cooldown_until),
            )
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))

    def available(self, at: datetime | None = None) -> bool:
        moment = ensure_utc(at or utcnow())
        if self.grade is HealthGrade.UNHEALTHY:
            if self.cooldown_until is None or moment < self.cooldown_until:
                return False
        if self.circuit is not None and not self.circuit.is_available(moment):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_key": self.candidate_key,
            "grade": self.grade.value,
            "success_rate": self.success_rate,
            "average_latency_seconds": self.average_latency_seconds,
            "recent_requests": self.recent_requests,
            "recent_failures": self.recent_failures,
            "rate_limit_failures": self.rate_limit_failures,
            "quota_failures": self.quota_failures,
            "circuit": self.circuit.to_dict() if self.circuit else None,
            "cooldown_until": (
                self.cooldown_until.isoformat()
                if self.cooldown_until
                else None
            ),
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class PoolSnapshot:
    candidates: tuple[ModelCandidate, ...]
    health: Mapping[str, ModelHealth] = field(default_factory=dict)
    primary_key: str = ""
    generated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates[:64]))
        object.__setattr__(self, "health", dict(list(self.health.items())[:64]))
        object.__setattr__(self, "primary_key", bounded_text(self.primary_key, 1_000))
        object.__setattr__(self, "generated_at", ensure_utc(self.generated_at))

    def candidate(self, key: str) -> ModelCandidate | None:
        return next((item for item in self.candidates if item.key == key), None)

    def health_for(self, key: str) -> ModelHealth | None:
        return self.health.get(key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "health": {
                key: value.to_dict()
                for key, value in self.health.items()
            },
            "primary_key": self.primary_key,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class BackpressureInput:
    queued_actions_runs: int = 0
    actions_queue_threshold: int = 40
    active_provider_requests: int = 0
    provider_parallelism_limit: int = 4
    provider_cooldown_seconds: float = 0.0
    circuit_open_count: int = 0
    available_candidate_count: int = 1
    canonical_plan_age_seconds: float | None = None
    canonical_plan_max_age_seconds: float = 1_200.0
    pending_plan_items: int = 0
    active_squads: int = 0
    blocked_workers: int = 0
    total_workers: int = 0
    retry_backlog: int = 0
    retry_backlog_limit: int = 16
    emergency_override: bool = False
    evidence_complete: bool = True

    def __post_init__(self) -> None:
        for name in (
            "queued_actions_runs",
            "actions_queue_threshold",
            "active_provider_requests",
            "provider_parallelism_limit",
            "circuit_open_count",
            "available_candidate_count",
            "pending_plan_items",
            "active_squads",
            "blocked_workers",
            "total_workers",
            "retry_backlog",
            "retry_backlog_limit",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.provider_cooldown_seconds < 0:
            raise ValueError("provider_cooldown_seconds must be non-negative")
        if (
            self.canonical_plan_age_seconds is not None
            and self.canonical_plan_age_seconds < 0
        ):
            raise ValueError("canonical_plan_age_seconds must be non-negative")
        if self.canonical_plan_max_age_seconds <= 0:
            raise ValueError("canonical_plan_max_age_seconds must be positive")

    @property
    def actions_queue_saturated(self) -> bool:
        threshold = max(1, self.actions_queue_threshold)
        return self.queued_actions_runs >= threshold

    @property
    def provider_parallelism_saturated(self) -> bool:
        limit = max(1, self.provider_parallelism_limit)
        return self.active_provider_requests >= limit

    @property
    def retry_backlog_saturated(self) -> bool:
        limit = max(1, self.retry_backlog_limit)
        return self.retry_backlog >= limit

    @property
    def plan_stale(self) -> bool:
        if self.canonical_plan_age_seconds is None:
            return True
        return self.canonical_plan_age_seconds >= self.canonical_plan_max_age_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "queued_actions_runs": self.queued_actions_runs,
            "actions_queue_threshold": self.actions_queue_threshold,
            "active_provider_requests": self.active_provider_requests,
            "provider_parallelism_limit": self.provider_parallelism_limit,
            "provider_cooldown_seconds": self.provider_cooldown_seconds,
            "circuit_open_count": self.circuit_open_count,
            "available_candidate_count": self.available_candidate_count,
            "canonical_plan_age_seconds": self.canonical_plan_age_seconds,
            "canonical_plan_max_age_seconds": self.canonical_plan_max_age_seconds,
            "pending_plan_items": self.pending_plan_items,
            "active_squads": self.active_squads,
            "blocked_workers": self.blocked_workers,
            "total_workers": self.total_workers,
            "retry_backlog": self.retry_backlog,
            "retry_backlog_limit": self.retry_backlog_limit,
            "emergency_override": self.emergency_override,
            "evidence_complete": self.evidence_complete,
        }


@dataclass(frozen=True, slots=True)
class BackpressureDecision:
    action: BackpressureAction
    reason: str
    score: int = 0
    retry_after_seconds: float | None = None
    contributing_signals: tuple[str, ...] = ()
    observed_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", bounded_text(self.reason, 1_000))
        object.__setattr__(
            self,
            "contributing_signals",
            bounded_strings(self.contributing_signals, limit=24),
        )
        object.__setattr__(self, "observed_at", ensure_utc(self.observed_at))
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "score": self.score,
            "retry_after_seconds": self.retry_after_seconds,
            "contributing_signals": list(self.contributing_signals),
            "observed_at": self.observed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class LedgerSnapshot:
    request_count: int
    attempt_count: int
    success_count: int
    failure_count: int
    active_count: int
    by_failure_class: Mapping[str, int]
    by_model: Mapping[str, int]
    oldest_at: datetime | None = None
    newest_at: datetime | None = None
    generated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        for name in (
            "request_count",
            "attempt_count",
            "success_count",
            "failure_count",
            "active_count",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        object.__setattr__(
            self,
            "by_failure_class",
            {
                bounded_identifier(key): nonnegative_int(value)
                for key, value in list(self.by_failure_class.items())[:64]
            },
        )
        object.__setattr__(
            self,
            "by_model",
            {
                bounded_identifier(key): nonnegative_int(value)
                for key, value in list(self.by_model.items())[:64]
            },
        )
        if self.oldest_at is not None:
            object.__setattr__(self, "oldest_at", ensure_utc(self.oldest_at))
        if self.newest_at is not None:
            object.__setattr__(self, "newest_at", ensure_utc(self.newest_at))
        object.__setattr__(self, "generated_at", ensure_utc(self.generated_at))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "attempt_count": self.attempt_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "active_count": self.active_count,
            "by_failure_class": dict(self.by_failure_class),
            "by_model": dict(self.by_model),
            "oldest_at": self.oldest_at.isoformat() if self.oldest_at else None,
            "newest_at": self.newest_at.isoformat() if self.newest_at else None,
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    name: str
    correlation_id: str = ""
    candidate_key: str = ""
    model: str = ""
    provider: str = ""
    failure_class: FailureClass | None = None
    attempt_number: int | None = None
    duration_seconds: float | None = None
    value: float | None = None
    tags: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        name = bounded_identifier(self.name)
        if not name:
            raise ValueError("event name is required")
        object.__setattr__(self, "name", name)
        object.__setattr__(
            self,
            "correlation_id",
            bounded_identifier(self.correlation_id),
        )
        object.__setattr__(
            self,
            "candidate_key",
            bounded_text(self.candidate_key, 1_000),
        )
        object.__setattr__(self, "model", bounded_identifier(self.model))
        object.__setattr__(self, "provider", bounded_identifier(self.provider))
        if self.attempt_number is not None and self.attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        if self.duration_seconds is not None and self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")
        object.__setattr__(self, "tags", bounded_metadata(self.tags, limit=24))
        object.__setattr__(self, "occurred_at", ensure_utc(self.occurred_at))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "correlation_id": self.correlation_id,
            "candidate_key": self.candidate_key,
            "model": self.model,
            "provider": self.provider,
            "failure_class": (
                self.failure_class.value
                if self.failure_class is not None
                else None
            ),
            "attempt_number": self.attempt_number,
            "duration_seconds": self.duration_seconds,
            "value": self.value,
            "tags": dict(self.tags),
            "occurred_at": self.occurred_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ResilienceConfig:
    attempt_budget: AttemptBudget = field(default_factory=AttemptBudget)
    circuit_failure_threshold: int = 4
    circuit_window_seconds: float = 300.0
    circuit_open_seconds: float = 60.0
    circuit_max_open_seconds: float = 900.0
    circuit_half_open_probes: int = 1
    health_window_size: int = 64
    ledger_max_requests: int = 512
    ledger_max_attempts: int = 2_048
    telemetry_max_events: int = 2_048
    fallback_on_rate_limit: bool = True
    fallback_on_server_error: bool = True
    fallback_on_network_error: bool = True
    fallback_on_timeout: bool = True
    fail_fast_on_quota: bool = True
    fail_fast_on_auth: bool = True

    def __post_init__(self) -> None:
        if self.circuit_failure_threshold < 1:
            raise ValueError("circuit_failure_threshold must be positive")
        if self.circuit_window_seconds <= 0:
            raise ValueError("circuit_window_seconds must be positive")
        if self.circuit_open_seconds < 0:
            raise ValueError("circuit_open_seconds must be non-negative")
        if self.circuit_max_open_seconds < self.circuit_open_seconds:
            raise ValueError(
                "circuit_max_open_seconds cannot be below circuit_open_seconds"
            )
        if self.circuit_half_open_probes < 1:
            raise ValueError("circuit_half_open_probes must be positive")
        if self.health_window_size < 1:
            raise ValueError("health_window_size must be positive")
        if self.ledger_max_requests < 1 or self.ledger_max_attempts < 1:
            raise ValueError("ledger limits must be positive")
        if self.telemetry_max_events < 1:
            raise ValueError("telemetry_max_events must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_budget": self.attempt_budget.to_dict(),
            "circuit_failure_threshold": self.circuit_failure_threshold,
            "circuit_window_seconds": self.circuit_window_seconds,
            "circuit_open_seconds": self.circuit_open_seconds,
            "circuit_max_open_seconds": self.circuit_max_open_seconds,
            "circuit_half_open_probes": self.circuit_half_open_probes,
            "health_window_size": self.health_window_size,
            "ledger_max_requests": self.ledger_max_requests,
            "ledger_max_attempts": self.ledger_max_attempts,
            "telemetry_max_events": self.telemetry_max_events,
            "fallback_on_rate_limit": self.fallback_on_rate_limit,
            "fallback_on_server_error": self.fallback_on_server_error,
            "fallback_on_network_error": self.fallback_on_network_error,
            "fallback_on_timeout": self.fallback_on_timeout,
            "fail_fast_on_quota": self.fail_fast_on_quota,
            "fail_fast_on_auth": self.fail_fast_on_auth,
        }


@dataclass(frozen=True, slots=True)
class RequestContext:
    correlation_id: str
    operation: str
    requirements: RequestRequirements = field(default_factory=RequestRequirements)
    budget: AttemptBudget = field(default_factory=AttemptBudget)
    created_at: datetime = field(default_factory=utcnow)
    deadline_at: datetime | None = None
    preferred_candidate_key: str = ""
    idempotency_seed: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        correlation_id = bounded_identifier(self.correlation_id)
        operation = bounded_identifier(self.operation)
        if not correlation_id:
            raise ValueError("correlation_id is required")
        if not operation:
            raise ValueError("operation is required")
        created = ensure_utc(self.created_at)
        deadline = (
            ensure_utc(self.deadline_at)
            if self.deadline_at is not None
            else created + timedelta(seconds=self.budget.deadline_seconds)
        )
        if deadline <= created:
            raise ValueError("deadline_at must follow created_at")
        object.__setattr__(self, "correlation_id", correlation_id)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "deadline_at", deadline)
        object.__setattr__(
            self,
            "preferred_candidate_key",
            bounded_text(self.preferred_candidate_key, 1_000),
        )
        object.__setattr__(
            self,
            "idempotency_seed",
            bounded_text(self.idempotency_seed, 500),
        )
        object.__setattr__(self, "metadata", bounded_metadata(self.metadata))

    def remaining_seconds(self, at: datetime | None = None) -> float:
        moment = ensure_utc(at or utcnow())
        assert self.deadline_at is not None
        return max(0.0, (self.deadline_at - moment).total_seconds())

    def expired(self, at: datetime | None = None) -> bool:
        return self.remaining_seconds(at) <= 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "operation": self.operation,
            "requirements": self.requirements.to_dict(),
            "budget": self.budget.to_dict(),
            "created_at": self.created_at.isoformat(),
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "preferred_candidate_key": self.preferred_candidate_key,
            "idempotency_seed": self.idempotency_seed,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class RequestOutcome:
    correlation_id: str
    success: bool
    attempts: tuple[AttemptRecord, ...]
    candidate_key: str = ""
    model: str = ""
    provider: str = ""
    value: Any = None
    failure: SafeProviderError | None = None
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime = field(default_factory=utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "correlation_id",
            bounded_identifier(self.correlation_id),
        )
        object.__setattr__(self, "attempts", tuple(self.attempts[:64]))
        object.__setattr__(
            self,
            "candidate_key",
            bounded_text(self.candidate_key, 1_000),
        )
        object.__setattr__(self, "model", bounded_identifier(self.model))
        object.__setattr__(self, "provider", bounded_identifier(self.provider))
        started = ensure_utc(self.started_at)
        finished = ensure_utc(self.finished_at)
        if finished < started:
            raise ValueError("finished_at cannot precede started_at")
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "finished_at", finished)
        object.__setattr__(self, "metadata", bounded_metadata(self.metadata))
        if self.success and self.failure is not None:
            raise ValueError("successful outcomes cannot carry a failure")
        if not self.success and self.failure is None:
            raise ValueError("failed outcomes require a failure")

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, (self.finished_at - self.started_at).total_seconds())

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    def to_dict(self, *, include_value: bool = False) -> dict[str, Any]:
        result = {
            "correlation_id": self.correlation_id,
            "success": self.success,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "candidate_key": self.candidate_key,
            "model": self.model,
            "provider": self.provider,
            "failure": self.failure.to_dict() if self.failure else None,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "elapsed_seconds": self.elapsed_seconds,
            "metadata": dict(self.metadata),
        }
        if include_value:
            result["value"] = self.value
        return result


def health_grade_from_window(
    *,
    requests: int,
    failures: int,
    circuit_phase: CircuitPhase | None = None,
) -> HealthGrade:
    if circuit_phase is CircuitPhase.OPEN:
        return HealthGrade.UNHEALTHY
    if requests <= 0:
        return HealthGrade.UNKNOWN
    ratio = max(0.0, min(1.0, failures / requests))
    if ratio >= 0.5:
        return HealthGrade.UNHEALTHY
    if ratio >= 0.2:
        return HealthGrade.DEGRADED
    return HealthGrade.HEALTHY


def merge_capabilities(
    *values: Iterable[Capability],
) -> frozenset[Capability]:
    result: set[Capability] = set()
    for group in values:
        result.update(group)
        if len(result) >= MAX_CAPABILITIES:
            break
    return frozenset(result)


def sort_attempts(
    attempts: Sequence[AttemptRecord],
) -> tuple[AttemptRecord, ...]:
    return tuple(
        sorted(
            attempts[:MAX_HISTORY_ITEMS],
            key=lambda item: (
                item.started_at,
                item.attempt_number,
                item.candidate_key,
            ),
        )
    )
