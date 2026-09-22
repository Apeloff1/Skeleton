"""Import-free audit of request-bound environment limit names.

``SKELETON_GATE_MAX_BODY_BYTES`` / ``HEADER_BYTES`` / ``HEADER_COUNT`` are
separate from the F-43 process-ownership and seal flag inventory. This
snapshot lists those names without importing middleware or widening
``AUDITED_ENV_MODULES``.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import AUDITED_GATE_LIMIT_MODULES, audited_gate_limit_flags
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


GATE_LIMIT_AUDIT_KIND: Final = "gate_limit_audit"


def gate_limit_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable gate-limit environment-flag audit."""

    flags = audited_gate_limit_flags()
    rows: list[dict[str, object]] = []
    for item in flags:
        rows.append(
            {
                "name": item["name"],
                "module": item["module"],
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": GATE_LIMIT_AUDIT_KIND,
        "modules": list(AUDITED_GATE_LIMIT_MODULES),
        "flags": rows,
        "names": [str(item["name"]) for item in rows],
    }


def get_gate_limit_audit_row(flag_id: str) -> dict[str, object]:
    """Return one gate-limit audit row by environment variable name."""

    if not isinstance(flag_id, str):
        raise TypeError("flag_id must be a string")
    normalized = flag_id.strip()
    if not normalized:
        raise ValueError("flag_id must not be empty")
    for row in gate_limit_audit_snapshot()["flags"]:
        if row["name"] == normalized:
            return dict(row)
    raise KeyError(f"unknown flag: {normalized}")
