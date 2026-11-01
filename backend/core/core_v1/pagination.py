"""Keyset (cursor) pagination.

Cursors are opaque, tamper-evident tokens: base64url(JSON) + a truncated
HMAC so a client cannot forge a cursor into another scope or sort order.
Ordering is always (created_at, id) so pages are stable under concurrent
inserts.
"""
from __future__ import annotations

import base64
import binascii
import math
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar

from .errors import validation

T = TypeVar("T")
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@dataclass(frozen=True)
class PageRequest:
    limit: int = DEFAULT_LIMIT
    after: tuple[float, str] | None = None  # (created_at, id) of last seen row


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    next_cursor: str | None

    def as_dict(self, render) -> dict:
        return {"items": [render(i) for i in self.items], "next_cursor": self.next_cursor,
                "has_more": self.next_cursor is not None}


class CursorCodec:
    def __init__(self, key: bytes) -> None:
        if type(key) is not bytes or len(key) < 16:
            raise ValueError("cursor key must be at least 16 bytes")
        self._key = key

    def _mac(self, body: bytes) -> str:
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()[:16]

    def encode(self, scope: str, created_at: float, item_id: str) -> str:
        if (type(scope) is not str or not 1 <= len(scope) <= 128
                or type(item_id) is not str or not 1 <= len(item_id) <= 96
                or type(created_at) not in (int, float) or not math.isfinite(created_at)):
            raise ValueError("cursor inputs must be bounded and finite")
        body = json.dumps({"s": scope, "t": created_at, "i": item_id},
                          separators=(",", ":"), sort_keys=True).encode()
        token = base64.urlsafe_b64encode(body).decode().rstrip("=")
        return f"{token}.{self._mac(body)}"

    def decode(self, scope: str, cursor: str) -> tuple[float, str]:
        bad = validation("CORE.PAGINATION.INVALID_CURSOR", "cursor is invalid")
        if not isinstance(cursor, str) or cursor.count(".") != 1 or len(cursor) > 512:
            raise bad
        token, mac = cursor.split(".")
        try:
            body = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            data = json.loads(body)
        except (ValueError, binascii.Error, UnicodeError):
            raise bad from None
        if not hmac.compare_digest(mac, self._mac(body)):
            raise bad
        if not isinstance(data, dict) or data.get("s") != scope:
            raise bad
        t, i = data.get("t"), data.get("i")
        if (type(t) not in (int, float) or not math.isfinite(t)
                or type(i) is not str or not 1 <= len(i) <= 96):
            raise bad
        return float(t), i


def parse_limit(raw: int | str | None) -> int:
    if raw is None:
        return DEFAULT_LIMIT
    try:
        if type(raw) is bool:
            raise ValueError("boolean limit")
        value = int(raw)
    except (TypeError, ValueError):
        raise validation("CORE.PAGINATION.INVALID_LIMIT", "limit must be an integer",
                         max=MAX_LIMIT) from None
    if not 1 <= value <= MAX_LIMIT:
        raise validation("CORE.PAGINATION.INVALID_LIMIT", "limit out of range",
                         min=1, max=MAX_LIMIT)
    return value


def build_page(rows: Sequence[T], limit: int, key, codec: CursorCodec, scope: str) -> Page[T]:
    """``rows`` must hold up to ``limit + 1`` items; the extra signals more pages."""
    more = len(rows) > limit
    items = tuple(rows[:limit])
    cursor = None
    if more and items:
        created_at, item_id = key(items[-1])
        cursor = codec.encode(scope, created_at, item_id)
    return Page(items, cursor)
