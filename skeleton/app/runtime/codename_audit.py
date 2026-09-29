"""Import-free audit of advertised Skeleton codename literals.

Package metadata, architecture, setup config, and the shared configuration
command must advertise the same codename. This snapshot reports that without
booting genesis.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import codename_identity_rows
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


CODENAME_AUDIT_KIND: Final = "codename_audit"


def codename_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable codename-identity audit."""

    rows = [{"source": item["source"], "value": item["value"]} for item in codename_identity_rows()]
    values = [str(row["value"]) for row in rows]
    unique = list(dict.fromkeys(values))
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": CODENAME_AUDIT_KIND,
        "codenames": rows,
        "values": unique,
        "drift": [str(row["source"]) for row in rows if row["value"] != unique[0]] if unique else [str(row["source"]) for row in rows],
    }


def get_codename_audit_row(source_id: str) -> dict[str, object]:
    """Return one codename-identity row by source key."""

    if not isinstance(source_id, str):
        raise TypeError("source_id must be a string")
    normalized = source_id.strip()
    if not normalized:
        raise ValueError("source_id must not be empty")
    for row in codename_audit_snapshot()["codenames"]:
        if row["source"] == normalized:
            return dict(row)
    raise KeyError(f"unknown source: {normalized}")
