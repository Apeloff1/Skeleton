"""Request-correlation identifiers with an untrusted-input boundary."""
from __future__ import annotations

import re
import uuid

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def normalize_request_id(value: str | None) -> str:
    """Accept a small log-safe inbound ID or mint a fresh server ID.

    Client-provided request IDs are useful for tracing but must not become an
    unbounded/log-injection channel. Newlines, control characters, whitespace,
    and oversized identifiers are rejected rather than sanitized ambiguously.
    """
    if value and _REQUEST_ID_RE.fullmatch(value):
        return value
    return uuid.uuid4().hex[:16]
