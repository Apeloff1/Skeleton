"""Error taxonomy for the provider/tool adapter surface.

Every failure raised by the adapter layer derives from :class:`IntegrationError`
and carries a machine-readable ``code`` plus a ``retryable`` flag.  Retry,
circuit-breaker and fallback logic make decisions from those two attributes
only, never from message text, so provider adapters must classify failures
when they translate transport errors into this taxonomy.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "IntegrationError",
    "ProviderError",
    "ProviderUnavailableError",
    "RateLimitedError",
    "AuthenticationError",
    "InvalidRequestError",
    "ResponseFormatError",
    "DeadlineExceededError",
    "OperationCancelledError",
    "CircuitOpenError",
    "RetryExhaustedError",
    "NoProviderAvailableError",
    "ProviderNotFoundError",
    "DuplicateRegistrationError",
    "CapabilityDeniedError",
    "ToolError",
    "ToolNotFoundError",
    "ToolArgumentError",
    "ToolExecutionError",
    "SchemaValidationError",
    "ConfigurationError",
    "classify_exception",
]


class IntegrationError(Exception):
    """Base class for all adapter-surface failures."""

    code: str = "integration_error"
    retryable: bool = False

    def __init__(
        self,
        message: str = "",
        *,
        code: str | None = None,
        retryable: bool | None = None,
        provider: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.provider = provider
        self.details: dict[str, Any] = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.provider is not None:
            payload["provider"] = self.provider
        if self.details:
            payload["details"] = dict(self.details)
        return payload

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


class ProviderError(IntegrationError):
    """A model provider failed to serve a request."""

    code = "provider_error"


class ProviderUnavailableError(ProviderError):
    """Transient provider-side failure (5xx, connection reset, overload)."""

    code = "provider_unavailable"
    retryable = True


class RateLimitedError(ProviderError):
    """Provider asked the caller to slow down."""

    code = "rate_limited"
    retryable = True

    def __init__(self, message: str = "", *, retry_after: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after if retry_after is None else max(0.0, float(retry_after))


class AuthenticationError(ProviderError):
    """Credentials were missing, rejected or expired.  Never retried."""

    code = "authentication_failed"
    retryable = False


class InvalidRequestError(ProviderError):
    """The request itself is malformed; retrying cannot help."""

    code = "invalid_request"
    retryable = False


class ResponseFormatError(ProviderError):
    """The provider answered with something the adapter cannot parse."""

    code = "response_format"
    retryable = True


class DeadlineExceededError(IntegrationError):
    """An operation ran past its deadline or per-attempt timeout."""

    code = "deadline_exceeded"
    retryable = True


class OperationCancelledError(IntegrationError):
    """The caller cancelled the operation.  Never retried."""

    code = "cancelled"
    retryable = False


class CircuitOpenError(IntegrationError):
    """The circuit breaker for a provider is open; fail fast."""

    code = "circuit_open"
    retryable = False

    def __init__(self, message: str = "", *, reopen_in: float | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.reopen_in = reopen_in


class RetryExhaustedError(IntegrationError):
    """All retry attempts failed; ``last_error`` holds the final failure."""

    code = "retry_exhausted"
    retryable = False

    def __init__(
        self,
        message: str = "",
        *,
        attempts: int = 0,
        last_error: BaseException | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.attempts = attempts
        self.last_error = last_error


class NoProviderAvailableError(IntegrationError):
    """No registered provider (including fallback) could serve the request."""

    code = "no_provider_available"
    retryable = False

    def __init__(self, message: str = "", *, failures: dict[str, BaseException] | None = None, **kwargs: Any):
        super().__init__(message, **kwargs)
        self.failures: dict[str, BaseException] = dict(failures or {})

    def as_dict(self) -> dict[str, Any]:
        payload = super().as_dict()
        payload["failures"] = {
            name: (err.as_dict() if isinstance(err, IntegrationError) else {"type": type(err).__name__})
            for name, err in self.failures.items()
        }
        return payload


class ProviderNotFoundError(IntegrationError):
    code = "provider_not_found"


class DuplicateRegistrationError(IntegrationError):
    code = "duplicate_registration"


class CapabilityDeniedError(IntegrationError):
    """The capability-security layer refused an invocation (fail-closed)."""

    code = "capability_denied"
    retryable = False

    def __init__(self, message: str = "", *, capability: str | None = None, reason: str = "", **kwargs: Any):
        super().__init__(message, **kwargs)
        self.capability = capability
        self.reason = reason


class ToolError(IntegrationError):
    code = "tool_error"


class ToolNotFoundError(ToolError):
    code = "tool_not_found"


class ToolArgumentError(ToolError):
    code = "tool_arguments_invalid"


class ToolExecutionError(ToolError):
    code = "tool_execution_failed"


class SchemaValidationError(IntegrationError):
    code = "schema_invalid"

    def __init__(self, message: str = "", *, path: str = "$", **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.path = path


class ConfigurationError(IntegrationError):
    code = "configuration_invalid"


def classify_exception(exc: BaseException, *, provider: str | None = None) -> IntegrationError:
    """Translate an arbitrary exception into the adapter taxonomy.

    ``IntegrationError`` instances pass through untouched.  Common stdlib
    transport errors map onto retryable/non-retryable classes; anything else
    becomes a non-retryable :class:`ProviderError` so unknown failures never
    trigger retry storms.
    """

    import asyncio
    import socket

    if isinstance(exc, IntegrationError):
        if provider is not None and exc.provider is None:
            exc.provider = provider
        return exc
    if isinstance(exc, asyncio.CancelledError):
        return OperationCancelledError("operation cancelled", provider=provider)
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return DeadlineExceededError(str(exc) or "timed out", provider=provider)
    if isinstance(exc, (ConnectionError, OSError)):
        return ProviderUnavailableError(str(exc) or type(exc).__name__, provider=provider)
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return ResponseFormatError(f"{type(exc).__name__}: {exc}", provider=provider, retryable=False)
    return ProviderError(f"{type(exc).__name__}: {exc}", provider=provider)
