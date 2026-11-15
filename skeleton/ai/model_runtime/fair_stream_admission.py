"""Canonical bounded read-only admission inventories for private runtime ledgers.

These are observations, not cross-process reservations. Every execution and
publication still requires its independent writer transaction and replay fence.
"""
from __future__ import annotations

MAX_ADMISSION_BATCH = 4096
MAX_REQUEST_ID_BYTES = 128


def validate_request_identity(value: object) -> str:
    if (type(value) is not str or not value
            or len(value) > MAX_REQUEST_ID_BYTES
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("bounded request identity required")
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeEncodeError as exc:
        raise ValueError("bounded request identity required") from exc
    if not 1 <= size <= MAX_REQUEST_ID_BYTES:
        raise ValueError("bounded request identity required")
    return value


def validate_admission_batch(
    request_ids: tuple[str, ...], *, additional_queued: int, maximum: int,
) -> tuple[str, ...]:
    """Validate identities before opening a SQLite transaction or lock.

    Additional queued slots are a pessimistic capacity allowance for callers
    of the legacy single-item preflight, never a replay authorization.
    """
    if type(request_ids) is not tuple or not 1 <= len(request_ids) <= MAX_ADMISSION_BATCH:
        raise ValueError("bounded nonempty request inventory required")
    if type(additional_queued) is not int or not 0 <= additional_queued <= maximum:
        raise ValueError("invalid queued request count")
    identities = tuple(validate_request_identity(item) for item in request_ids)
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate admission request identity")
    return identities
