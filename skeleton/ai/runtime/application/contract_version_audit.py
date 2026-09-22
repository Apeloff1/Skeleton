"""Import-free audit of the shared command CONTRACT_VERSION literal.

CLI, HTTP, and CommandResult payloads advertise this version. A second
literal in the configuration handler would drift identity. This snapshot
reports the assignment without executing commands.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import contract_version_identity_rows
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


CONTRACT_VERSION_AUDIT_KIND: Final = "contract_version_audit"


def contract_version_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable command-contract-version identity audit."""

    rows = [
        {"source": item["source"], "value": item["value"]} for item in contract_version_identity_rows()
    ]
    values = [str(row["value"]) for row in rows]
    unique = list(dict.fromkeys(values))
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": CONTRACT_VERSION_AUDIT_KIND,
        "versions": rows,
        "values": unique,
        "drift": [str(row["source"]) for row in rows if row["value"] != unique[0]] if unique else [str(row["source"]) for row in rows],
    }


def get_contract_version_audit_row(source_id: str) -> dict[str, object]:
    """Return one contract-version identity row by source key."""

    if not isinstance(source_id, str):
        raise TypeError("source_id must be a string")
    normalized = source_id.strip()
    if not normalized:
        raise ValueError("source_id must not be empty")
    for row in contract_version_audit_snapshot()["versions"]:
        if row["source"] == normalized:
            return dict(row)
    raise KeyError(f"unknown source: {normalized}")
