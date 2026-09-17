"""Import-free structural audit for the organism, social, and galaxy planes.

F-15 grew three planes while earlier waves landed. This snapshot reports
export drift, genesis wiring, and boot-phase documentation without importing
those packages, so CLI/API consumers can inspect them the same way lifecycle
inspects capability readiness.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Final

from .audit_parse import (
    architecture_exports,
    boot_phase_catalog,
    export_drift,
    genesis_wire_map,
    public_exports,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION, get_capability


AUDITED_PLANE_IDS: Final[tuple[str, ...]] = ("organism", "social", "galaxy")
PLANE_AUDIT_KIND: Final = "plane_audit"


def plane_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable F-15 plane audit without importing the planes."""

    wire_map = genesis_wire_map()
    catalog = boot_phase_catalog()
    rows: list[dict[str, object]] = []
    for plane_id in AUDITED_PLANE_IDS:
        capability = get_capability(plane_id)
        public = public_exports(capability.module)
        documented = architecture_exports(capability.module)
        handles = list(wire_map.get(plane_id, []))
        rows.append(
            {
                "id": capability.id,
                "module": capability.module,
                "description": capability.description,
                "resolvable": find_spec(capability.module) is not None,
                "public_exports": public,
                "architecture_exports": documented,
                "export_drift": export_drift(public, documented),
                "genesis_wired": bool(handles),
                "genesis_handles": handles,
                "boot_phase_listed": plane_id in catalog,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": PLANE_AUDIT_KIND,
        "planes": rows,
    }


def get_plane_audit_row(plane_id: str) -> dict[str, object]:
    """Return one audited plane row without importing the plane package."""

    if not isinstance(plane_id, str):
        raise TypeError("plane_id must be a string")
    normalized = plane_id.strip().lower()
    if not normalized:
        raise ValueError("plane_id must not be empty")
    if normalized not in AUDITED_PLANE_IDS:
        raise KeyError(f"unknown plane: {normalized}")
    for row in plane_audit_snapshot()["planes"]:
        if row["id"] == normalized:
            return dict(row)
    raise KeyError(f"unknown plane: {normalized}")
