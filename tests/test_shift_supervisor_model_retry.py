from __future__ import annotations

import urllib.error
from email.message import Message

from core.shift_supervisor.model_gateway import ModelGateway


def _http_error(*, code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("https://example.invalid", code, "error", headers, None)


def test_429_honors_retry_after_with_upper_bound() -> None:
    gateway = ModelGateway(max_retry_delay_seconds=30)

    assert gateway._retry_delay(_http_error(code=429, retry_after="12"), 1) == 12
    assert gateway._retry_delay(_http_error(code=429, retry_after="120"), 1) == 30


def test_invalid_or_unrelated_retry_after_uses_bounded_backoff() -> None:
    gateway = ModelGateway(max_retry_delay_seconds=30)

    assert gateway._retry_delay(_http_error(code=429, retry_after="later"), 2) == 2
    assert gateway._retry_delay(_http_error(code=503, retry_after="20"), 3) == 4
