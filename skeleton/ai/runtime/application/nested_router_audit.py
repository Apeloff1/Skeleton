"""Import-free audit of nested ``router.include_router`` mounts.

``create_app`` mounts GameForge, which itself includes the command-contract
router. That nested include is invisible to F-34's create_app scan. This
snapshot reports nested includes without importing the API package.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import nested_router_includes
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


NESTED_ROUTER_AUDIT_KIND: Final = "nested_router_audit"


def nested_router_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable nested include_router audit."""

    includes = nested_router_includes()
    rows: list[dict[str, object]] = []
    for item in includes:
        rows.append(
            {
                "host_module": item["host_module"],
                "included_module": item["included_module"],
                "included_name": item["included_name"],
                "prefix": item["prefix"],
                "key": f"{item['host_module']} -> {item['included_module'] or item['included_name']}",
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": NESTED_ROUTER_AUDIT_KIND,
        "includes": rows,
    }


def get_nested_router_audit_row(include_id: str) -> dict[str, object]:
    """Return one nested-include audit row by host module name."""

    if not isinstance(include_id, str):
        raise TypeError("include_id must be a string")
    normalized = include_id.strip()
    if not normalized:
        raise ValueError("include_id must not be empty")
    for row in nested_router_audit_snapshot()["includes"]:
        if row["host_module"] == normalized or row["key"] == normalized:
            return dict(row)
    raise KeyError(f"unknown include: {normalized}")
