"""Import-free audit of WriteAdmitMiddleware mutating methods versus live handlers.

Admission applies to POST/PUT/PATCH/DELETE after the HMAC seal. Live handlers
may not use every method in that set. This snapshot reports coverage without
importing admit_write or changing shed semantics.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import live_handler_rows, write_admit_mutating_methods
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


ADMIT_WRITE_AUDIT_KIND: Final = "admit_write_audit"


def admit_write_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable write-admit mutating-method audit."""

    mutating = write_admit_mutating_methods()
    mutating_set = set(mutating)
    handlers = live_handler_rows()
    live_methods = list(dict.fromkeys(str(row["method"]) for row in handlers))
    rows: list[dict[str, object]] = []
    for method in list(dict.fromkeys([*mutating, *live_methods])):
        live_count = sum(1 for row in handlers if str(row["method"]) == method)
        rows.append(
            {
                "method": method,
                "mutating": method in mutating_set,
                "live_count": live_count,
            }
        )
    live_mutating = [
        f"{row['method']} {row['path']}"
        for row in handlers
        if str(row["method"]) in mutating_set
    ]
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": ADMIT_WRITE_AUDIT_KIND,
        "methods": rows,
        "mutating": mutating,
        "live_mutating": live_mutating,
        "uncovered_mutating_live": sorted(
            {
                str(row["method"])
                for row in handlers
                if str(row["method"]) in {"POST", "PUT", "PATCH", "DELETE"}
                and str(row["method"]) not in mutating_set
            }
        ),
        "unused_mutating_methods": [method for method in mutating if method not in set(live_methods)],
    }


def get_admit_write_audit_row(method_id: str) -> dict[str, object]:
    """Return one write-admit audit row by HTTP method."""

    if not isinstance(method_id, str):
        raise TypeError("method_id must be a string")
    normalized = method_id.strip().upper()
    if not normalized:
        raise ValueError("method_id must not be empty")
    for row in admit_write_audit_snapshot()["methods"]:
        if row["method"] == normalized:
            return dict(row)
    raise KeyError(f"unknown method: {normalized}")
