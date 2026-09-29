"""Import-free audit of opt-in public-dev prefixes versus HMAC defaults.

``_DEV_OPEN_PREFIXES`` only apply when ``SKELETON_PUBLIC_DEV_SURFACES`` is on.
They must not leak into ``DEFAULT_OPEN_PREFIXES``. This snapshot reports that
split without widening the default open surface.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import hmac_default_open_prefixes, hmac_dev_open_prefixes, hmac_runtime_root_open
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


OPEN_DEV_AUDIT_KIND: Final = "open_dev_audit"


def open_dev_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable public-dev prefix versus HMAC-default audit."""

    default = hmac_default_open_prefixes()
    dev = hmac_dev_open_prefixes()
    default_set = set(default)
    rows: list[dict[str, object]] = []
    leaked: list[str] = []
    extras: list[str] = []
    for prefix in dev:
        leak = prefix in default_set
        if leak:
            leaked.append(prefix)
        else:
            extras.append(prefix)
        rows.append(
            {
                "prefix": prefix,
                "in_default": leak,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": OPEN_DEV_AUDIT_KIND,
        "default": default,
        "dev": dev,
        "prefixes": rows,
        "leaked_into_default": leaked,
        "extras": extras,
        "runtime_root_open": hmac_runtime_root_open(),
    }


def get_open_dev_audit_row(prefix_id: str) -> dict[str, object]:
    """Return one public-dev prefix row by prefix path."""

    if not isinstance(prefix_id, str):
        raise TypeError("prefix_id must be a string")
    normalized = prefix_id.strip()
    if not normalized:
        raise ValueError("prefix_id must not be empty")
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    for row in open_dev_audit_snapshot()["prefixes"]:
        if row["prefix"] == normalized:
            return dict(row)
    raise KeyError(f"unknown prefix: {normalized}")
