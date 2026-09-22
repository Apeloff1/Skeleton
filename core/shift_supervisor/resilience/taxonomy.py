from __future__ import annotations

import json
import re
import socket
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from typing import Any, Mapping

from .models import (
    FailureClass,
    FailureDomain,
    RateLimitHints,
    SafeProviderError,
    bounded_identifier,
    bounded_text,
    nonnegative_float,
    utcnow,
)


MAX_ERROR_BODY_BYTES = 16_384
_DURATION_TOKEN = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h|d)", re.I)

QUOTA_CODES = frozenset(
    {
        "credit_balance_exhausted",
        "insufficient_quota",
        "organization_usage_limit_exceeded",
        "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded",
        "billing_hard_limit_reached",
        "usage_limit_exceeded",
    }
)

RATE_LIMIT_CODES = frozenset(
    {
        "rate_limit_exceeded",
        "requests",
        "requests_limit_exceeded",
        "tokens",
        "tokens_limit_exceeded",
        "too_many_requests",
    }
)

AUTH_CODES = frozenset(
    {
        "invalid_api_key",
        "invalid_authentication",
        "authentication_error",
        "missing_api_key",
    }
)

AUTHZ_CODES = frozenset(
    {
        "permission_denied",
        "forbidden",
        "policy_violation",
        "access_denied",
    }
)

MODEL_ACCESS_CODES = frozenset(
    {
        "model_not_found",
        "model_not_available",
        "model_access_denied",
        "unsupported_model",
    }
)

PAYLOAD_CODES = frozenset(
    {
        "context_length_exceeded",
        "request_too_large",
        "payload_too_large",
        "max_tokens_exceeded",
    }
)

TOOL_CODES = frozenset(
    {
        "tool_limit_exceeded",
        "too_many_tool_calls",
        "unsupported_tool",
        "invalid_tool",
    }
)


def header_value(headers: Mapping[str, Any] | None, name: str) -> str:
    if headers is None:
        return ""
    lower_name = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lower_name:
            return bounded_text(value, 500)
    return ""


def parse_duration_seconds(value: Any) -> float | None:
    text = bounded_text(value, 200)
    if not text:
        return None

    try:
        return max(0.0, float(text))
    except ValueError:
        pass

    total = 0.0
    position = 0
    matched = False
    for match in _DURATION_TOKEN.finditer(text):
        if match.start() != position and text[position : match.start()].strip():
            return None
        matched = True
        number = float(match.group("value"))
        unit = match.group("unit").lower()
        if unit == "ms":
            total += number / 1000.0
        elif unit == "s":
            total += number
        elif unit == "m":
            total += number * 60.0
        elif unit == "h":
            total += number * 3600.0
        elif unit == "d":
            total += number * 86400.0
        position = match.end()

    if not matched:
        return None
    if text[position:].strip():
        return None
    return max(0.0, total)


def parse_retry_after(
    value: Any,
    *,
    now: datetime | None = None,
) -> float | None:
    text = bounded_text(value, 500)
    if not text:
        return None

    duration = parse_duration_seconds(text)
    if duration is not None:
        return duration

    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    moment = (now or utcnow()).astimezone(timezone.utc)
    return max(0.0, (parsed.astimezone(timezone.utc) - moment).total_seconds())


def parse_optional_int(value: Any) -> int | None:
    text = bounded_text(value, 120)
    if not text:
        return None
    try:
        return max(0, int(float(text)))
    except (TypeError, ValueError, OverflowError):
        return None


def parse_rate_limit_hints(
    headers: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
) -> RateLimitHints:
    return RateLimitHints(
        retry_after_seconds=parse_retry_after(
            header_value(headers, "retry-after"),
            now=now,
        ),
        request_reset_seconds=parse_duration_seconds(
            header_value(headers, "x-ratelimit-reset-requests")
        ),
        token_reset_seconds=parse_duration_seconds(
            header_value(headers, "x-ratelimit-reset-tokens")
        ),
        remaining_requests=parse_optional_int(
            header_value(headers, "x-ratelimit-remaining-requests")
        ),
        remaining_tokens=parse_optional_int(
            header_value(headers, "x-ratelimit-remaining-tokens")
        ),
        limit_requests=parse_optional_int(
            header_value(headers, "x-ratelimit-limit-requests")
        ),
        limit_tokens=parse_optional_int(
            header_value(headers, "x-ratelimit-limit-tokens")
        ),
    )


def read_error_body(
    exc: urllib.error.HTTPError,
    *,
    max_bytes: int = MAX_ERROR_BODY_BYTES,
) -> bytes:
    limit = max(0, int(max_bytes))
    if limit == 0:
        return b""
    try:
        raw = exc.read(limit + 1)
    except (AttributeError, OSError, ValueError, HTTPException):
        return b""
    return raw[:limit]


def safe_error_payload(raw: bytes) -> dict[str, str]:
    if not raw:
        return {}

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {}

    try:
        value = json.loads(decoded)
    except json.JSONDecodeError:
        return {}

    if not isinstance(value, dict):
        return {}

    error = value.get("error", value)
    if not isinstance(error, dict):
        return {}

    return {
        "code": bounded_identifier(error.get("code")),
        "type": bounded_identifier(error.get("type")),
        "param": bounded_identifier(error.get("param")),
    }


def classify_error_code(
    error_code: str,
    error_type: str,
) -> tuple[FailureClass, FailureDomain, bool] | None:
    code = bounded_identifier(error_code).lower()
    kind = bounded_identifier(error_type).lower()
    values = {code, kind}

    if values & QUOTA_CODES:
        return FailureClass.QUOTA, FailureDomain.PROVIDER, False

    if values & RATE_LIMIT_CODES:
        return FailureClass.RATE_LIMIT, FailureDomain.PROVIDER, True

    if values & AUTH_CODES:
        return FailureClass.AUTHENTICATION, FailureDomain.PROVIDER, False

    if values & AUTHZ_CODES:
        return FailureClass.AUTHORIZATION, FailureDomain.PROVIDER, False

    if values & MODEL_ACCESS_CODES:
        return FailureClass.MODEL_ACCESS, FailureDomain.CAPABILITY, False

    if values & PAYLOAD_CODES:
        return FailureClass.PAYLOAD_LIMIT, FailureDomain.RESPONSE, False

    if values & TOOL_CODES:
        return FailureClass.TOOL_LIMIT, FailureDomain.CAPABILITY, False

    if "timeout" in code or "timeout" in kind:
        return FailureClass.TIMEOUT, FailureDomain.TRANSPORT, True

    if "server" in code or "server" in kind:
        return FailureClass.SERVER, FailureDomain.PROVIDER, True

    if "network" in code or "connection" in code:
        return FailureClass.NETWORK, FailureDomain.TRANSPORT, True

    return None


def classify_http_status(
    status: int,
    *,
    error_code: str = "",
    error_type: str = "",
) -> tuple[FailureClass, FailureDomain, bool]:
    explicit = classify_error_code(error_code, error_type)
    if explicit is not None:
        return explicit

    if status == 429:
        return FailureClass.RATE_LIMIT, FailureDomain.PROVIDER, True

    if status == 401:
        return FailureClass.AUTHENTICATION, FailureDomain.PROVIDER, False

    if status == 403:
        return FailureClass.AUTHORIZATION, FailureDomain.PROVIDER, False

    if status == 404:
        return FailureClass.NOT_FOUND, FailureDomain.PROVIDER, False

    if status == 408:
        return FailureClass.TIMEOUT, FailureDomain.TRANSPORT, True

    if status == 409:
        return FailureClass.CONFLICT, FailureDomain.PROVIDER, False

    if status == 413:
        return FailureClass.PAYLOAD_LIMIT, FailureDomain.RESPONSE, False

    if status == 422:
        return FailureClass.BAD_REQUEST, FailureDomain.PROVIDER, False

    if status in {
        400,
        405,
        406,
        410,
        411,
        414,
        415,
        417,
        431,
    }:
        return FailureClass.BAD_REQUEST, FailureDomain.PROVIDER, False

    if 500 <= status <= 599:
        return FailureClass.SERVER, FailureDomain.PROVIDER, True

    if 300 <= status <= 399:
        return FailureClass.CONTRACT, FailureDomain.RESPONSE, False

    return FailureClass.UNKNOWN, FailureDomain.PROVIDER, False


def classify_exception(
    exc: BaseException,
) -> tuple[FailureClass, FailureDomain, bool]:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return FailureClass.TIMEOUT, FailureDomain.TRANSPORT, True

    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return FailureClass.TIMEOUT, FailureDomain.TRANSPORT, True
        return FailureClass.NETWORK, FailureDomain.TRANSPORT, True

    if isinstance(exc, ConnectionError):
        return FailureClass.NETWORK, FailureDomain.TRANSPORT, True

    if isinstance(exc, OSError):
        return FailureClass.NETWORK, FailureDomain.TRANSPORT, True

    if isinstance(exc, UnicodeDecodeError):
        return FailureClass.DECODE, FailureDomain.RESPONSE, False

    if isinstance(exc, json.JSONDecodeError):
        return FailureClass.DECODE, FailureDomain.RESPONSE, False

    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return FailureClass.CONTRACT, FailureDomain.RESPONSE, False

    return FailureClass.UNKNOWN, FailureDomain.INTERNAL, False


@dataclass(frozen=True, slots=True)
class ClassificationInput:
    operation: str = ""
    http_status: int | None = None
    headers: Mapping[str, Any] | None = None
    error_code: str = ""
    error_type: str = ""
    request_id: str = ""
    exception: BaseException | None = None
    occurred_at: datetime | None = None
    metadata: Mapping[str, Any] | None = None


class ProviderErrorClassifier:
    """Convert provider and transport failures into safe machine evidence."""

    def __init__(
        self,
        *,
        max_error_body_bytes: int = MAX_ERROR_BODY_BYTES,
        max_rate_limit_hint_seconds: float = 3_600.0,
    ) -> None:
        self.max_error_body_bytes = max(0, int(max_error_body_bytes))
        self.max_rate_limit_hint_seconds = max(
            0.0,
            float(max_rate_limit_hint_seconds),
        )

    def classify_http_error(
        self,
        exc: urllib.error.HTTPError,
        *,
        operation: str = "",
        occurred_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> SafeProviderError:
        raw = read_error_body(
            exc,
            max_bytes=self.max_error_body_bytes,
        )
        payload = safe_error_payload(raw)
        error_code = payload.get("code", "").lower()
        error_type = payload.get("type", "").lower()

        failure_class, domain, retryable = classify_http_status(
            exc.code,
            error_code=error_code,
            error_type=error_type,
        )

        moment = occurred_at or utcnow()
        hints = parse_rate_limit_hints(
            exc.headers,
            now=moment,
        ).with_cap(self.max_rate_limit_hint_seconds)

        request_id = header_value(exc.headers, "x-request-id")
        if not request_id:
            request_id = header_value(exc.headers, "request-id")

        return SafeProviderError(
            failure_class=failure_class,
            domain=domain,
            http_status=exc.code,
            error_code=error_code,
            error_type=error_type,
            request_id=request_id,
            operation=operation,
            retryable=retryable,
            safe_message=self.safe_message(
                failure_class,
                http_status=exc.code,
            ),
            rate_limit=hints,
            occurred_at=moment,
            metadata=metadata or {},
        )

    def classify_exception(
        self,
        exc: BaseException,
        *,
        operation: str = "",
        occurred_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> SafeProviderError:
        if isinstance(exc, urllib.error.HTTPError):
            return self.classify_http_error(
                exc,
                operation=operation,
                occurred_at=occurred_at,
                metadata=metadata,
            )

        failure_class, domain, retryable = classify_exception(exc)
        return SafeProviderError(
            failure_class=failure_class,
            domain=domain,
            operation=operation,
            retryable=retryable,
            safe_message=self.safe_message(failure_class),
            occurred_at=occurred_at or utcnow(),
            metadata=metadata or {},
        )

    def classify_input(
        self,
        value: ClassificationInput,
    ) -> SafeProviderError:
        if value.exception is not None:
            return self.classify_exception(
                value.exception,
                operation=value.operation,
                occurred_at=value.occurred_at,
                metadata=value.metadata,
            )

        moment = value.occurred_at or utcnow()

        if value.http_status is not None:
            failure_class, domain, retryable = classify_http_status(
                value.http_status,
                error_code=value.error_code,
                error_type=value.error_type,
            )
        else:
            explicit = classify_error_code(
                value.error_code,
                value.error_type,
            )
            if explicit is None:
                failure_class, domain, retryable = (
                    FailureClass.UNKNOWN,
                    FailureDomain.PROVIDER,
                    False,
                )
            else:
                failure_class, domain, retryable = explicit

        return SafeProviderError(
            failure_class=failure_class,
            domain=domain,
            http_status=value.http_status,
            error_code=value.error_code,
            error_type=value.error_type,
            request_id=value.request_id,
            operation=value.operation,
            retryable=retryable,
            safe_message=self.safe_message(
                failure_class,
                http_status=value.http_status,
            ),
            rate_limit=parse_rate_limit_hints(
                value.headers,
                now=moment,
            ).with_cap(self.max_rate_limit_hint_seconds),
            occurred_at=moment,
            metadata=value.metadata or {},
        )

    @staticmethod
    def safe_message(
        failure_class: FailureClass,
        *,
        http_status: int | None = None,
    ) -> str:
        suffix = f" (HTTP {http_status})" if http_status is not None else ""
        messages = {
            FailureClass.RATE_LIMIT: "provider rate limit encountered",
            FailureClass.QUOTA: "provider quota or spend limit encountered",
            FailureClass.AUTHENTICATION: "provider authentication failed",
            FailureClass.AUTHORIZATION: "provider authorization failed",
            FailureClass.MODEL_ACCESS: "requested model is unavailable",
            FailureClass.NOT_FOUND: "provider resource was not found",
            FailureClass.BAD_REQUEST: "provider rejected the request contract",
            FailureClass.CONFLICT: "provider reported a request conflict",
            FailureClass.SERVER: "provider server failure",
            FailureClass.NETWORK: "provider network transport failure",
            FailureClass.TIMEOUT: "provider request timed out",
            FailureClass.DECODE: "provider response could not be decoded safely",
            FailureClass.CONTRACT: "provider response violated the expected contract",
            FailureClass.PAYLOAD_LIMIT: "provider rejected the request payload size",
            FailureClass.TOOL_LIMIT: "provider rejected the requested tool contract",
            FailureClass.CANCELLED: "provider request was cancelled",
            FailureClass.UNKNOWN: "provider request failed for an unknown reason",
        }
        return messages[failure_class] + suffix


def failure_is_retryable(
    failure: SafeProviderError,
) -> bool:
    if failure.failure_class in {
        FailureClass.QUOTA,
        FailureClass.AUTHENTICATION,
        FailureClass.AUTHORIZATION,
        FailureClass.MODEL_ACCESS,
        FailureClass.BAD_REQUEST,
        FailureClass.CONTRACT,
        FailureClass.PAYLOAD_LIMIT,
        FailureClass.TOOL_LIMIT,
    }:
        return False
    return failure.retryable


def failure_supports_fallback(
    failure: SafeProviderError,
) -> bool:
    return failure.failure_class in {
        FailureClass.RATE_LIMIT,
        FailureClass.SERVER,
        FailureClass.NETWORK,
        FailureClass.TIMEOUT,
    }


def failure_opens_circuit(
    failure: SafeProviderError,
) -> bool:
    return failure.failure_class in {
        FailureClass.RATE_LIMIT,
        FailureClass.SERVER,
        FailureClass.NETWORK,
        FailureClass.TIMEOUT,
        FailureClass.QUOTA,
        FailureClass.AUTHENTICATION,
        FailureClass.AUTHORIZATION,
        FailureClass.MODEL_ACCESS,
    }


def cooldown_from_failure(
    failure: SafeProviderError,
    *,
    fallback_seconds: float,
    maximum_seconds: float,
) -> float:
    hinted = failure.rate_limit.strongest_cooldown_seconds
    if hinted is None:
        hinted = nonnegative_float(fallback_seconds)
    maximum = max(0.0, nonnegative_float(maximum_seconds))
    return min(max(0.0, hinted), maximum)


def sanitize_headers(
    headers: Mapping[str, Any] | None,
) -> dict[str, str]:
    if headers is None:
        return {}

    allowed = (
        "retry-after",
        "x-request-id",
        "request-id",
        "x-ratelimit-limit-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-requests",
        "x-ratelimit-reset-tokens",
    )

    result: dict[str, str] = {}
    for name in allowed:
        value = header_value(headers, name)
        if value:
            result[name] = value
    return result


def normalized_failure_key(
    failure: SafeProviderError,
) -> str:
    status = failure.http_status if failure.http_status is not None else 0
    code = failure.error_code or "-"
    kind = failure.error_type or "-"
    return (
        f"{failure.failure_class.value}:"
        f"{failure.domain.value}:"
        f"{status}:"
        f"{code}:"
        f"{kind}"
    )


def failure_weight(
    failure: SafeProviderError,
) -> int:
    weights = {
        FailureClass.RATE_LIMIT: 3,
        FailureClass.QUOTA: 8,
        FailureClass.AUTHENTICATION: 10,
        FailureClass.AUTHORIZATION: 10,
        FailureClass.MODEL_ACCESS: 8,
        FailureClass.NOT_FOUND: 4,
        FailureClass.BAD_REQUEST: 2,
        FailureClass.CONFLICT: 2,
        FailureClass.SERVER: 4,
        FailureClass.NETWORK: 4,
        FailureClass.TIMEOUT: 4,
        FailureClass.DECODE: 3,
        FailureClass.CONTRACT: 3,
        FailureClass.PAYLOAD_LIMIT: 2,
        FailureClass.TOOL_LIMIT: 2,
        FailureClass.CANCELLED: 1,
        FailureClass.UNKNOWN: 5,
    }
    return weights[failure.failure_class]


def quota_like(
    *,
    error_code: str = "",
    error_type: str = "",
) -> bool:
    values = {
        bounded_identifier(error_code).lower(),
        bounded_identifier(error_type).lower(),
    }
    return bool(values & QUOTA_CODES)


def rate_limit_like(
    *,
    error_code: str = "",
    error_type: str = "",
) -> bool:
    values = {
        bounded_identifier(error_code).lower(),
        bounded_identifier(error_type).lower(),
    }
    return bool(values & RATE_LIMIT_CODES)
