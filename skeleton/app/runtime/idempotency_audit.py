"""Import-free audit of direct and decorated IdempotencyGuard handlers.

Materialise, archetype, and GameForge routes use replay/remember or the
operation/complete decorator. Both paths are audited without importing the API
package or changing replay semantics.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import idempotency_handler_rows
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


IDEMPOTENCY_AUDIT_KIND: Final = "idempotency_audit"


def idempotency_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable idempotency handler audit."""

    rows: list[dict[str, object]] = []
    for item in idempotency_handler_rows():
        rows.append(
            {
                "key": item["key"],
                "module": item["module"],
                "handler": item["handler"],
                "method": item["method"],
                "path": item["path"],
                "replay": bool(item["replay"]),
                "remember": bool(item["remember"]),
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": IDEMPOTENCY_AUDIT_KIND,
        "handlers": rows,
        "keys": [str(row["key"]) for row in rows],
        "missing_remember": [str(row["key"]) for row in rows if not row["remember"]],
        "missing_replay": [str(row["key"]) for row in rows if not row["replay"]],
    }


def get_idempotency_audit_row(handler_id: str) -> dict[str, object]:
    """Return one idempotency-audit row by ``module:handler`` key."""

    if not isinstance(handler_id, str):
        raise TypeError("handler_id must be a string")
    normalized = handler_id.strip()
    if not normalized:
        raise ValueError("handler_id must not be empty")
    for row in idempotency_audit_snapshot()["handlers"]:
        if row["key"] == normalized or row["handler"] == normalized:
            return dict(row)
    raise KeyError(f"unknown handler: {normalized}")
