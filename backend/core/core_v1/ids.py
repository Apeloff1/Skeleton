"""Prefixed opaque identifiers (``whk_``, ``evt_``, ``dlv_``, ``whs_``)."""
from __future__ import annotations

import re
import secrets

PREFIXES = {"webhook": "whk", "event": "evt", "delivery": "dlv", "secret": "whs"}
_ID_RE = re.compile(r"^(whk|evt|dlv|whs)_[0-9a-f]{24}$")


def new_id(kind: str) -> str:
    try:
        prefix = PREFIXES[kind]
    except KeyError:
        raise ValueError(f"unknown id kind {kind!r}") from None
    return f"{prefix}_{secrets.token_hex(12)}"


def is_id(value: object, kind: str | None = None) -> bool:
    if not isinstance(value, str) or not _ID_RE.match(value):
        return False
    return kind is None or value.startswith(PREFIXES[kind] + "_")
