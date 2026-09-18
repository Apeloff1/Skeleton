"""Import-free audit of dual SessionMode enum values.

``jeeves.core`` and ``jeeves.llm_core`` both advertise SessionMode. HTTP
session create allow-lists the core enum values. The two Enum classes must
keep identical string values or mode normalization silently drifts. This
snapshot reports that without importing either Jeeves module.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import session_mode_identity_rows
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


SESSION_MODE_AUDIT_KIND: Final = "session_mode_audit"


def session_mode_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable SessionMode identity audit."""

    rows = [
        {"source": item["source"], "member": item["member"], "value": item["value"]}
        for item in session_mode_identity_rows()
    ]
    core = [str(row["value"]) for row in rows if str(row["source"]).startswith("skeleton.jeeves.core:")]
    llm_core = [
        str(row["value"]) for row in rows if str(row["source"]).startswith("skeleton.jeeves.llm_core:")
    ]
    values = list(dict.fromkeys([*core, *llm_core]))
    core_set = set(core)
    llm_set = set(llm_core)
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": SESSION_MODE_AUDIT_KIND,
        "modes": rows,
        "core": core,
        "llm_core": llm_core,
        "values": values,
        "drift": [str(row["source"]) for row in rows if row["value"] not in core_set or row["value"] not in llm_set],
        "missing_from_core": [name for name in values if name not in core_set],
        "missing_from_llm_core": [name for name in values if name not in llm_set],
    }


def get_session_mode_audit_row(source_id: str) -> dict[str, object]:
    """Return one SessionMode identity row by source key."""

    if not isinstance(source_id, str):
        raise TypeError("source_id must be a string")
    normalized = source_id.strip()
    if not normalized:
        raise ValueError("source_id must not be empty")
    for row in session_mode_audit_snapshot()["modes"]:
        if row["source"] == normalized:
            return dict(row)
    raise KeyError(f"unknown source: {normalized}")
