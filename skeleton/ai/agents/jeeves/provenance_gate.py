"""Provenance gate — Pareto asset legality and traceability.

No asset enters a catalog without identity and license.
"""

from __future__ import annotations

from typing import Any


REQUIRED_FIELDS = ["id", "source", "license", "era", "type"]


def validate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
    return {
        "valid": len(missing) == 0,
        "missing": missing,
        "entry_id": entry.get("id"),
        "rule": "Reject catalog insert if any required field is absent",
    }


def catalog_policy() -> dict[str, Any]:
    return {
        "required": REQUIRED_FIELDS,
        "forbidden": ["unlicensed scrape", "unknown source", "placeholder marked final"],
        "gate": "Content lock cannot pass with any invalid entry",
        "operator": "Operator may waive only with explicit written exception",
    }
