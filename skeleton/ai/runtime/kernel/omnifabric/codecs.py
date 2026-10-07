"""Stable JSON + digest helpers for OmniFabric canonical forms.

F1 contract (gameforge-rs): every digest in the empire is SHA-256.
Canonical event hashing never covers the event's own hash field.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

GENESIS_HASH = "genesis"


def stable_json(value: Any) -> str:
    """Compact canonical JSON — keys sorted, no whitespace drift."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def digest_mapping(mapping: Mapping[str, Any]) -> str:
    """SHA-256 of stable JSON for arbitrary metadata maps."""
    return sha256_hex(stable_json(dict(mapping)))


def rfc3339_from_ts(ts: float) -> str:
    """UTC RFC3339 with microsecond precision (RS chrono::Utc::to_rfc3339)."""
    from datetime import datetime, timezone

    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    # match chrono default: +00:00 offset, microseconds if present
    return dt.isoformat().replace("+00:00", "Z") if False else dt.isoformat()


def parse_ts(value: float | str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    from datetime import datetime

    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).timestamp()
