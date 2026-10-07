"""Tests for the adapter error taxonomy and exception classification."""

from __future__ import annotations

import asyncio
import socket

from .errors import (
    AuthenticationError,
    CapabilityDeniedError,
    DeadlineExceededError,
    IntegrationError,
    InvalidRequestError,
    NoProviderAvailableError,
    OperationCancelledError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitedError,
    ResponseFormatError,
    classify_exception,
)


def test_retryable_defaults():
    assert ProviderUnavailableError().retryable
    assert RateLimitedError().retryable
    assert DeadlineExceededError().retryable
    assert not AuthenticationError().retryable
    assert not InvalidRequestError().retryable
    assert not OperationCancelledError().retryable
    assert not CapabilityDeniedError().retryable


def test_overrides_and_as_dict():
    err = ProviderError("boom", code="custom", retryable=True, provider="p", details={"status": 503})
    payload = err.as_dict()
    assert payload == {
        "type": "ProviderError",
        "code": "custom",
        "message": "boom",
        "retryable": True,
        "provider": "p",
        "details": {"status": 503},
    }
    assert "custom" in repr(err)


def test_rate_limited_retry_after_clamped():
    assert RateLimitedError(retry_after=-5).retry_after == 0.0
    assert RateLimitedError(retry_after=2.5).retry_after == 2.5
    assert RateLimitedError().retry_after is None


def test_classify_passthrough_sets_provider():
    original = ProviderUnavailableError("x")
    assert classify_exception(original, provider="p") is original
    assert original.provider == "p"


def test_classify_stdlib_errors():
    assert isinstance(classify_exception(TimeoutError()), DeadlineExceededError)
    assert isinstance(classify_exception(socket.timeout()), DeadlineExceededError)
    assert isinstance(classify_exception(ConnectionResetError("r")), ProviderUnavailableError)
    assert isinstance(classify_exception(asyncio.CancelledError()), OperationCancelledError)
    fmt = classify_exception(ValueError("bad"))
    assert isinstance(fmt, ResponseFormatError) and not fmt.retryable
    other = classify_exception(RuntimeError("weird"), provider="q")
    assert type(other) is ProviderError and not other.retryable and other.provider == "q"


def test_no_provider_available_serialises_failures():
    err = NoProviderAvailableError("none", failures={"a": ProviderUnavailableError("down"), "b": RuntimeError()})
    payload = err.as_dict()
    assert payload["failures"]["a"]["code"] == "provider_unavailable"
    assert payload["failures"]["b"] == {"type": "RuntimeError"}
    assert isinstance(err, IntegrationError)
