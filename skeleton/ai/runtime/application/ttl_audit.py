"""Import-free audit of HMAC seal and idempotency default TTLs.

``mint_seal`` defaults to ``DEFAULT_TTL_SECS`` and IdempotencyGuard caches
for ``default_ttl`` / ``IdempotencyEntry.ttl_seconds``. Those numbers must
stay the same five-minute identity. This snapshot reports that without
minting seals or caching responses.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import ttl_identity_rows
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


TTL_AUDIT_KIND: Final = "ttl_audit"


def _as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def ttl_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable HMAC/idempotency TTL identity audit."""

    rows = [{"source": item["source"], "value": item["value"]} for item in ttl_identity_rows()]
    numbers = [_as_number(row["value"]) for row in rows]
    expected = next((number for number in numbers if number is not None), None)
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": TTL_AUDIT_KIND,
        "ttls": rows,
        "values": [row["value"] for row in rows],
        "numbers": numbers,
        "drift": [
            str(row["source"])
            for row, number in zip(rows, numbers)
            if expected is None or number != expected
        ],
    }


def get_ttl_audit_row(source_id: str) -> dict[str, object]:
    """Return one TTL-identity row by source key."""

    if not isinstance(source_id, str):
        raise TypeError("source_id must be a string")
    normalized = source_id.strip()
    if not normalized:
        raise ValueError("source_id must not be empty")
    for row in ttl_audit_snapshot()["ttls"]:
        if row["source"] == normalized:
            return dict(row)
    raise KeyError(f"unknown source: {normalized}")
