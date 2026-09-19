from __future__ import annotations

import errno
import json
import re
import socket
import ssl
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

from .provider_types import (
    FailureKind,
    FailureScope,
    ProviderFailure,
    RateLimitHints,
    SafeProviderError,
    ensure_utc,
    optional_text,
    utcnow,
)


_QUOTA_CODES = frozenset(
    {
        "credit_balance_exhausted",
        "insufficient_quota",
        "organization_usage_limit_exceeded",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "billing_hard_limit_reached",
        "billing_not_active",
        "quota_exceeded",
    }
)

_QUOTA_TYPES = frozenset(
    {
        "insufficient_quota",
        "billing_error",
        "quota_exhausted",
    }
)

_RATE_LIMIT_CODES = frozenset(
    {
        "rate_limit_exceeded",
        "requests_limit_exceeded",
        "tokens_limit_exceeded",
        "concurrency_limit_exceeded",
        "too_many_requests",
    }
)

_AUTH_CODES = frozenset(
    {
        "invalid_api_key",
        "invalid_authentication",
        "authentication_required",
        "api_key_invalid",
    }
)

_AUTHZ_CODES = frozenset(
    {
        "permission_denied",
        "access_denied",
        "model_not_allowed",
        "project_not_authorized",
        "organization_not_authorized",
    }
)

_MODEL_CODES = frozenset(
    {
        "model_not_found",
        "model_unavailable",
        "model_overloaded",
        "model_deprecated",
        "deployment_not_found",
    }
)

_RETRYABLE_SERVER_CODES = frozenset(
    {
        "server_error",
        "service_unavailable",
        "temporarily_unavailable",
        "overloaded",
        "upstream_error",
        "gateway_timeout",
    }
)

_DURATION_RE = re.compile(
    r"^\s*(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?P<unit>ms|s|sec|secs|second|seconds|m|min|mins|minute|minutes)?\s*$",
    re.IGNORECASE,
)

_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.:/@-]+")


@dataclass(frozen=True, slots=True)
class ClassificationPolicy:
    """Limits governing safe extraction from provider failures."""

    max_error_body_bytes: int = 16_384
    max_code_chars: int = 160
    max_type_chars: int = 160
    max_request_id_chars: int = 200
    max_provider_chars: int = 120
    max_model_chars: int = 200
    max_retry_after_seconds: float = 3_600.0
    default_rate_limit_scope: FailureScope = FailureScope.MODEL

    def __post_init__(self) -> None:
        for field_name in (
            "max_error_body_bytes",
            "max_code_chars",
            "max_type_chars",
            "max_request_id_chars",
            "max_provider_chars",
            "max_model_chars",
        ):
            value = int(getattr(self, field_name))
            if value <= 0:
                raise ValueError(f"{field_name} must be positive")
            object.__setattr__(self, field_name, value)
        delay = float(self.max_retry_after_seconds)
        if delay <= 0:
            raise ValueError("max_retry_after_seconds must be positive")
        object.__setattr__(self, "max_retry_after_seconds", delay)
        if not isinstance(self.default_rate_limit_scope, FailureScope):
            object.__setattr__(
                self,
                "default_rate_limit_scope",
                FailureScope(str(self.default_rate_limit_scope)),
            )


def _header(headers: Mapping[str, Any] | Message | None, name: str) -> str:
    if headers is None:
        return ""
    try:
        value = headers.get(name)
    except (AttributeError, KeyError, TypeError):
        return ""
    return str(value or "").strip()


def _safe_token(value: Any, limit: int) -> str:
    text = optional_text(value, limit=limit)
    if not text:
        return ""
    return _SAFE_TOKEN_RE.sub("_", text)[:limit]


def parse_nonnegative_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_duration_seconds(value: Any) -> float | None:
    """Parse provider duration headers such as 1s or 250ms."""

    if value in (None, ""):
        return None
    text = str(value).strip()
    match = _DURATION_RE.match(text)
    if not match:
        return None
    try:
        amount = float(match.group("value"))
    except ValueError:
        return None
    unit = (match.group("unit") or "s").casefold()
    if unit == "ms":
        amount /= 1000.0
    elif unit in {"m", "min", "mins", "minute", "minutes"}:
        amount *= 60.0
    return max(0.0, amount)


def parse_retry_after(
    value: Any,
    *,
    now: datetime | None = None,
    max_seconds: float = 3_600.0,
) -> float | None:
    """Parse RFC Retry-After numeric seconds or HTTP-date safely."""

    if value in (None, ""):
        return None
    moment = ensure_utc(now or utcnow())
    text = str(value).strip()
    duration = parse_duration_seconds(text)
    if duration is not None:
        return min(duration, max_seconds)
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    reset = ensure_utc(parsed)
    return min(max(0.0, (reset - moment).total_seconds()), max_seconds)


def parse_reset_at(
    value: Any,
    *,
    now: datetime | None = None,
    max_seconds: float = 86_400.0,
) -> datetime | None:
    """Parse absolute epochs, RFC dates, or provider duration reset headers."""

    if value in (None, ""):
        return None
    moment = ensure_utc(now or utcnow())
    text = str(value).strip()

    duration = parse_duration_seconds(text)
    if duration is not None:
        return moment + timedelta(seconds=min(duration, max_seconds))

    try:
        epoch = float(text)
    except (TypeError, ValueError):
        epoch = -1.0
    if epoch >= 0:
        if epoch < 10_000_000:
            return moment + timedelta(seconds=min(epoch, max_seconds))
        try:
            absolute = datetime.fromtimestamp(epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            absolute = None
        if absolute is not None:
            upper = moment + timedelta(seconds=max_seconds)
            return min(max(absolute, moment), upper)

    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    upper = moment + timedelta(seconds=max_seconds)
    return min(max(ensure_utc(parsed), moment), upper)


def parse_rate_limit_hints(
    headers: Mapping[str, Any] | Message | None,
    *,
    now: datetime | None = None,
    max_retry_after_seconds: float = 3_600.0,
) -> RateLimitHints:
    moment = ensure_utc(now or utcnow())
    retry_after = parse_retry_after(
        _header(headers, "Retry-After"),
        now=moment,
        max_seconds=max_retry_after_seconds,
    )

    request_reset_raw = (
        _header(headers, "x-ratelimit-reset-requests")
        or _header(headers, "ratelimit-reset")
        or _header(headers, "x-rate-limit-reset")
    )
    token_reset_raw = _header(headers, "x-ratelimit-reset-tokens")

    remaining_requests = parse_nonnegative_int(
        _header(headers, "x-ratelimit-remaining-requests")
        or _header(headers, "ratelimit-remaining")
        or _header(headers, "x-rate-limit-remaining")
    )
    remaining_tokens = parse_nonnegative_int(
        _header(headers, "x-ratelimit-remaining-tokens")
    )
    limit_requests = parse_nonnegative_int(
        _header(headers, "x-ratelimit-limit-requests")
        or _header(headers, "ratelimit-limit")
        or _header(headers, "x-rate-limit-limit")
    )
    limit_tokens = parse_nonnegative_int(
        _header(headers, "x-ratelimit-limit-tokens")
    )

    return RateLimitHints(
        retry_after_seconds=retry_after,
        request_reset_at=parse_reset_at(request_reset_raw, now=moment),
        token_reset_at=parse_reset_at(token_reset_raw, now=moment),
        remaining_requests=remaining_requests,
        remaining_tokens=remaining_tokens,
        limit_requests=limit_requests,
        limit_tokens=limit_tokens,
    )


def _safe_json_error_fields(
    body: bytes,
    *,
    policy: ClassificationPolicy,
) -> tuple[str, str]:
    if not body:
        return "", ""
    raw = body[: policy.max_error_body_bytes]
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "", ""
    if not isinstance(payload, Mapping):
        return "", ""
    error = payload.get("error", {})
    if not isinstance(error, Mapping):
        return "", ""
    code = _safe_token(error.get("code"), policy.max_code_chars)
    error_type = _safe_token(error.get("type"), policy.max_type_chars)
    return code, error_type


def read_http_error_metadata(
    exc: urllib.error.HTTPError,
    *,
    provider: str = "",
    model: str = "",
    policy: ClassificationPolicy | None = None,
    now: datetime | None = None,
) -> SafeProviderError:
    """Read a bounded error body and retain only safe structured metadata."""

    active = policy or ClassificationPolicy()
    try:
        body = exc.read(active.max_error_body_bytes + 1)
    except (AttributeError, OSError, ValueError):
        body = b""
    code, error_type = _safe_json_error_fields(body, policy=active)
    request_id = (
        _header(exc.headers, "x-request-id")
        or _header(exc.headers, "request-id")
        or _header(exc.headers, "x-correlation-id")
    )
    return SafeProviderError(
        http_status=exc.code,
        error_code=code,
        error_type=error_type,
        request_id=_safe_token(request_id, active.max_request_id_chars),
        provider=_safe_token(provider, active.max_provider_chars),
        model=_safe_token(model, active.max_model_chars),
        hints=parse_rate_limit_hints(
            exc.headers,
            now=now,
            max_retry_after_seconds=active.max_retry_after_seconds,
        ),
    )


def classify_http_status(
    status: int,
    *,
    error_code: str = "",
    error_type: str = "",
    default_rate_limit_scope: FailureScope = FailureScope.MODEL,
) -> tuple[FailureKind, FailureScope, bool, str]:
    """Return kind, scope, retryability and a safe detail tag."""

    code = str(error_code or "").casefold()
    kind_text = str(error_type or "").casefold()

    if status == 429:
        if code in _QUOTA_CODES or kind_text in _QUOTA_TYPES:
            scope = (
                FailureScope.ORGANIZATION
                if "organization" in code
                else FailureScope.PROJECT
            )
            return FailureKind.QUOTA_EXHAUSTED, scope, False, "quota"
        if code in _RATE_LIMIT_CODES or "rate" in kind_text or not code:
            return FailureKind.RATE_LIMIT, default_rate_limit_scope, True, "rate-limit"
        return FailureKind.RATE_LIMIT, default_rate_limit_scope, True, "rate-limit"

    if status == 401:
        return FailureKind.AUTHENTICATION, FailureScope.PROVIDER, False, "authentication"
    if status == 403:
        if code in _AUTH_CODES:
            return FailureKind.AUTHENTICATION, FailureScope.PROVIDER, False, "authentication"
        return FailureKind.AUTHORIZATION, FailureScope.MODEL, False, "authorization"
    if status == 404 and code in _MODEL_CODES:
        return FailureKind.MODEL_UNAVAILABLE, FailureScope.MODEL, False, "model"
    if status == 408:
        return FailureKind.TIMEOUT, FailureScope.REQUEST, True, "request-timeout"
    if status == 409:
        return FailureKind.SERVER_ERROR, FailureScope.REQUEST, True, "conflict"
    if status == 425:
        return FailureKind.SERVER_ERROR, FailureScope.REQUEST, True, "too-early"
    if status == 499:
        return FailureKind.CANCELLED, FailureScope.REQUEST, False, "cancelled"
    if status in {500, 502, 503, 504}:
        detail = "server"
        if code in _MODEL_CODES:
            return FailureKind.MODEL_UNAVAILABLE, FailureScope.MODEL, True, "model"
        if code in _RETRYABLE_SERVER_CODES:
            detail = code
        return FailureKind.SERVER_ERROR, FailureScope.PROVIDER, True, detail
    if 500 <= status <= 599:
        return FailureKind.SERVER_ERROR, FailureScope.PROVIDER, True, "server"
    if 400 <= status <= 499:
        if code in _AUTH_CODES:
            return FailureKind.AUTHENTICATION, FailureScope.PROVIDER, False, "authentication"
        if code in _AUTHZ_CODES:
            return FailureKind.AUTHORIZATION, FailureScope.MODEL, False, "authorization"
        if code in _MODEL_CODES:
            return FailureKind.MODEL_UNAVAILABLE, FailureScope.MODEL, False, "model"
        return FailureKind.BAD_REQUEST, FailureScope.REQUEST, False, "client"
    return FailureKind.UNKNOWN, FailureScope.REQUEST, False, "http"


def classify_http_error(
    exc: urllib.error.HTTPError,
    *,
    provider: str = "",
    model: str = "",
    correlation_id: str = "",
    policy: ClassificationPolicy | None = None,
    now: datetime | None = None,
) -> ProviderFailure:
    active = policy or ClassificationPolicy()
    safe = read_http_error_metadata(
        exc,
        provider=provider,
        model=model,
        policy=active,
        now=now,
    )
    kind, scope, retryable, detail = classify_http_status(
        int(exc.code),
        error_code=safe.error_code,
        error_type=safe.error_type,
        default_rate_limit_scope=active.default_rate_limit_scope,
    )
    return ProviderFailure(
        kind=kind,
        scope=scope,
        retryable=retryable,
        safe_error=safe,
        occurred_at=ensure_utc(now or utcnow()),
        correlation_id=correlation_id,
        detail_tag=detail,
    )


def _errno_kind(value: int | None) -> tuple[FailureKind, str]:
    if value in {errno.ETIMEDOUT}:
        return FailureKind.TIMEOUT, "socket-timeout"
    if value in {
        errno.ECONNRESET,
        errno.ECONNREFUSED,
        errno.ECONNABORTED,
        errno.ENETUNREACH,
        errno.EHOSTUNREACH,
    }:
        return FailureKind.CONNECTION, "connection"
    return FailureKind.CONNECTION, "network"


def classify_exception(
    exc: BaseException,
    *,
    provider: str = "",
    model: str = "",
    correlation_id: str = "",
    policy: ClassificationPolicy | None = None,
    now: datetime | None = None,
) -> ProviderFailure:
    """Normalize transport/parse failures without embedding exception prose."""

    active = policy or ClassificationPolicy()
    moment = ensure_utc(now or utcnow())
    safe = SafeProviderError(
        provider=_safe_token(provider, active.max_provider_chars),
        model=_safe_token(model, active.max_model_chars),
    )

    if isinstance(exc, urllib.error.HTTPError):
        return classify_http_error(
            exc,
            provider=provider,
            model=model,
            correlation_id=correlation_id,
            policy=active,
            now=moment,
        )

    if isinstance(exc, (TimeoutError, socket.timeout)):
        return ProviderFailure(
            kind=FailureKind.TIMEOUT,
            scope=FailureScope.REQUEST,
            retryable=True,
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag="timeout",
        )

    if isinstance(exc, ssl.SSLError):
        return ProviderFailure(
            kind=FailureKind.TLS,
            scope=FailureScope.PROVIDER,
            retryable=False,
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag="tls",
        )

    if isinstance(exc, socket.gaierror):
        return ProviderFailure(
            kind=FailureKind.DNS,
            scope=FailureScope.PROVIDER,
            retryable=True,
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag="dns",
        )

    if isinstance(exc, ConnectionError):
        return ProviderFailure(
            kind=FailureKind.CONNECTION,
            scope=FailureScope.PROVIDER,
            retryable=True,
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag="connection",
        )

    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, BaseException) and reason is not exc:
            nested = classify_exception(
                reason,
                provider=provider,
                model=model,
                correlation_id=correlation_id,
                policy=active,
                now=moment,
            )
            return ProviderFailure(
                kind=nested.kind,
                scope=nested.scope,
                retryable=nested.retryable,
                safe_error=safe,
                occurred_at=moment,
                correlation_id=correlation_id,
                detail_tag=f"url-{nested.detail_tag}"[:200],
            )
        return ProviderFailure(
            kind=FailureKind.CONNECTION,
            scope=FailureScope.PROVIDER,
            retryable=True,
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag="url",
        )

    if isinstance(exc, OSError):
        kind, detail = _errno_kind(getattr(exc, "errno", None))
        return ProviderFailure(
            kind=kind,
            scope=FailureScope.PROVIDER,
            retryable=kind in {
                FailureKind.TIMEOUT,
                FailureKind.CONNECTION,
                FailureKind.DNS,
            },
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag=detail,
        )

    if isinstance(exc, UnicodeDecodeError):
        return ProviderFailure(
            kind=FailureKind.MALFORMED_RESPONSE,
            scope=FailureScope.REQUEST,
            retryable=True,
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag="decode",
        )

    if isinstance(exc, json.JSONDecodeError):
        return ProviderFailure(
            kind=FailureKind.MALFORMED_RESPONSE,
            scope=FailureScope.REQUEST,
            retryable=True,
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag="json",
        )

    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return ProviderFailure(
            kind=FailureKind.MALFORMED_RESPONSE,
            scope=FailureScope.REQUEST,
            retryable=False,
            safe_error=safe,
            occurred_at=moment,
            correlation_id=correlation_id,
            detail_tag="contract",
        )

    return ProviderFailure(
        kind=FailureKind.UNKNOWN,
        scope=FailureScope.REQUEST,
        retryable=False,
        safe_error=safe,
        occurred_at=moment,
        correlation_id=correlation_id,
        detail_tag=type(exc).__name__[:120],
    )


def failure_is_quota(failure: ProviderFailure) -> bool:
    return failure.kind is FailureKind.QUOTA_EXHAUSTED


def failure_is_rate_limit(failure: ProviderFailure) -> bool:
    return failure.kind is FailureKind.RATE_LIMIT


def failure_is_transport(failure: ProviderFailure) -> bool:
    return failure.kind in {
        FailureKind.TIMEOUT,
        FailureKind.CONNECTION,
        FailureKind.DNS,
        FailureKind.TLS,
        FailureKind.SERVER_ERROR,
    }


def failure_penalizes_provider(failure: ProviderFailure) -> bool:
    return failure.scope in {
        FailureScope.PROVIDER,
        FailureScope.ORGANIZATION,
    } or failure.kind in {
        FailureKind.SERVER_ERROR,
        FailureKind.CONNECTION,
        FailureKind.DNS,
        FailureKind.TLS,
    }


def failure_penalizes_model(failure: ProviderFailure) -> bool:
    return failure.scope in {
        FailureScope.MODEL,
        FailureScope.PROJECT,
        FailureScope.ORGANIZATION,
    } or failure.kind in {
        FailureKind.RATE_LIMIT,
        FailureKind.MODEL_UNAVAILABLE,
        FailureKind.QUOTA_EXHAUSTED,
    }


def safe_failure_summary(failure: ProviderFailure) -> str:
    """Compact log-safe failure string containing no provider message body."""

    safe = failure.safe_error
    parts = [
        f"kind={failure.kind.value}",
        f"scope={failure.scope.value}",
        f"retryable={str(failure.retryable).lower()}",
    ]
    if safe.http_status is not None:
        parts.append(f"http={safe.http_status}")
    if safe.error_code:
        parts.append(f"code={safe.error_code}")
    if safe.error_type:
        parts.append(f"type={safe.error_type}")
    if safe.request_id:
        parts.append(f"request_id={safe.request_id}")
    if safe.provider:
        parts.append(f"provider={safe.provider}")
    if safe.model:
        parts.append(f"model={safe.model}")
    if failure.detail_tag:
        parts.append(f"detail={failure.detail_tag}")
    return " ".join(parts)


def merge_rate_limit_hints(
    left: RateLimitHints,
    right: RateLimitHints,
) -> RateLimitHints:
    """Combine provider hints conservatively."""

    def minimum(a: int | None, b: int | None) -> int | None:
        values = [value for value in (a, b) if value is not None]
        return min(values) if values else None

    def later(a: datetime | None, b: datetime | None) -> datetime | None:
        values = [value for value in (a, b) if value is not None]
        return max(values) if values else None

    delays = [
        value
        for value in (left.retry_after_seconds, right.retry_after_seconds)
        if value is not None
    ]
    return RateLimitHints(
        retry_after_seconds=max(delays) if delays else None,
        request_reset_at=later(left.request_reset_at, right.request_reset_at),
        token_reset_at=later(left.token_reset_at, right.token_reset_at),
        remaining_requests=minimum(left.remaining_requests, right.remaining_requests),
        remaining_tokens=minimum(left.remaining_tokens, right.remaining_tokens),
        limit_requests=minimum(left.limit_requests, right.limit_requests),
        limit_tokens=minimum(left.limit_tokens, right.limit_tokens),
    )


def rate_limit_retry_at(
    failure: ProviderFailure,
    *,
    now: datetime | None = None,
    fallback_seconds: float = 1.0,
    maximum_seconds: float = 3_600.0,
) -> datetime:
    moment = ensure_utc(now or utcnow())
    hints = failure.safe_error.hints
    candidates: list[datetime] = []
    if hints.retry_after_seconds is not None:
        candidates.append(
            moment
            + timedelta(
                seconds=min(maximum_seconds, max(0.0, hints.retry_after_seconds))
            )
        )
    if hints.request_reset_at is not None:
        candidates.append(hints.request_reset_at)
    if hints.token_reset_at is not None:
        candidates.append(hints.token_reset_at)
    if candidates:
        return max(candidates)
    return moment + timedelta(seconds=min(maximum_seconds, max(0.0, fallback_seconds)))


__all__ = [
    "ClassificationPolicy",
    "classify_exception",
    "classify_http_error",
    "classify_http_status",
    "failure_is_quota",
    "failure_is_rate_limit",
    "failure_is_transport",
    "failure_penalizes_model",
    "failure_penalizes_provider",
    "merge_rate_limit_hints",
    "parse_duration_seconds",
    "parse_nonnegative_int",
    "parse_rate_limit_hints",
    "parse_reset_at",
    "parse_retry_after",
    "rate_limit_retry_at",
    "read_http_error_metadata",
    "safe_failure_summary",
]
