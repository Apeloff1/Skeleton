"""Import-free export-drift audit for every curated capability.

F-15 locked organism/social/galaxy against architecture PACKAGES. The rest of
the F-16 manifest still drifts. This snapshot reports that without importing
capability packages or rewriting PACKAGES.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Final

from .audit_parse import (
    architecture_exports,
    architecture_package_exists,
    export_drift,
    public_exports,
)
from .capability_manifest import CAPABILITIES, CAPABILITY_MANIFEST_VERSION, get_capability


EXPORT_AUDIT_KIND: Final = "manifest_export_audit"


def export_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable export audit for the curated manifest."""

    rows: list[dict[str, object]] = []
    for capability in CAPABILITIES:
        public = public_exports(capability.module)
        documented = architecture_exports(capability.module)
        rows.append(
            {
                "id": capability.id,
                "module": capability.module,
                "description": capability.description,
                "resolvable": find_spec(capability.module) is not None,
                "in_architecture_registry": architecture_package_exists(capability.module),
                "public_export_count": len(public),
                "architecture_export_count": len(documented),
                "export_drift": export_drift(public, documented),
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": EXPORT_AUDIT_KIND,
        "capabilities": rows,
    }


def get_export_audit_row(capability_id: str) -> dict[str, object]:
    """Return one export-audit row by curated capability ID."""

    capability = get_capability(capability_id)
    for row in export_audit_snapshot()["capabilities"]:
        if row["id"] == capability.id:
            return dict(row)
    raise KeyError(f"unknown capability: {capability.id}")
