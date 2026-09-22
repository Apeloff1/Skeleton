"""Import-free audit of MATERIALISE_TARGETS / PROGRESSION_CURVES call sites.

Allow-lists live on the shared command contract. HTTP and runtime handlers
must pass them to ``require_text`` / ``_text_field``. This snapshot reports
those sites without executing GameForge.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import (
    allow_list_usages,
    assigned_str_tuple,
    parse_module_tree,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


ALLOW_LIST_AUDIT_KIND: Final = "allow_list_audit"


def allow_list_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable allow-list usage audit."""

    usages = allow_list_usages()
    rows: list[dict[str, object]] = []
    for item in usages:
        rows.append(
            {
                "key": item["key"],
                "module": item["module"],
                "handler": item["handler"],
                "catalog": item["catalog"],
            }
        )
    tree = parse_module_tree("skeleton.application.command_contracts")
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": ALLOW_LIST_AUDIT_KIND,
        "targets": assigned_str_tuple(tree, "MATERIALISE_TARGETS"),
        "curves": assigned_str_tuple(tree, "PROGRESSION_CURVES"),
        "usages": rows,
        "keys": [str(row["key"]) for row in rows],
    }


def get_allow_list_audit_row(handler_id: str) -> dict[str, object]:
    """Return one allow-list usage row by ``module:handler`` key."""

    if not isinstance(handler_id, str):
        raise TypeError("handler_id must be a string")
    normalized = handler_id.strip()
    if not normalized:
        raise ValueError("handler_id must not be empty")
    for row in allow_list_audit_snapshot()["usages"]:
        if row["key"] == normalized or row["handler"] == normalized:
            return dict(row)
    raise KeyError(f"unknown handler: {normalized}")
