"""Import-free audit of genesis boot order versus architecture BOOT_PHASES.

Genesis runs more phases than architecture documents. This snapshot reports
that split without importing or executing genesis, so operators can inspect
boot documentation the same way lifecycle inspects capability readiness.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import (
    boot_phase_catalog,
    genesis_boot_phase_order,
    genesis_report_phases,
    genesis_wire_map,
    parse_genesis_tree,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


GENESIS_BOOT_AUDIT_KIND: Final = "genesis_boot_audit"


def genesis_boot_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable genesis/architecture boot audit."""

    tree = parse_genesis_tree()
    boot_order = genesis_boot_phase_order(tree)
    report_phases = set(genesis_report_phases(tree))
    wire_map = genesis_wire_map(tree)
    catalog = boot_phase_catalog()
    rows: list[dict[str, object]] = []
    for phase in boot_order:
        rows.append(
            {
                "phase": phase,
                "listed_in_boot_phases": phase in catalog,
                "appended_to_report": phase in report_phases,
                "genesis_handles": list(wire_map.get(phase, [])),
                "documented_subsystems": list(catalog.get(phase, [])),
            }
        )
    missing_from_boot_phases = [phase for phase in boot_order if phase not in catalog]
    missing_from_genesis = [phase for phase in catalog if phase not in set(boot_order)]
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": GENESIS_BOOT_AUDIT_KIND,
        "phases": rows,
        "missing_from_boot_phases": missing_from_boot_phases,
        "missing_from_genesis": missing_from_genesis,
    }


def get_genesis_boot_audit_row(phase_id: str) -> dict[str, object]:
    """Return one genesis boot-audit row by phase name."""

    if not isinstance(phase_id, str):
        raise TypeError("phase_id must be a string")
    normalized = phase_id.strip().lower()
    if not normalized:
        raise ValueError("phase_id must not be empty")
    for row in genesis_boot_audit_snapshot()["phases"]:
        if row["phase"] == normalized:
            return dict(row)
    raise KeyError(f"unknown phase: {normalized}")
