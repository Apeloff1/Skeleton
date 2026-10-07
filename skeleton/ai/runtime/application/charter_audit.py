"""Import-free audit of ``require_charter(domain, action)`` bindings.

Charter pairs live in ``Depends(require_charter(...))`` on main-router,
sidecar, and mounted handlers. Architecture ``protected: true`` is a
documentation flag, not the (domain, action) tuple. This snapshot reports
the live pairs without importing the API package or widening charters.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import architecture_api_routes, charter_route_bindings
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


CHARTER_AUDIT_KIND: Final = "charter_audit"


def _route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def charter_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable require_charter domain/action audit."""

    bindings = charter_route_bindings()
    documented = {
        _route_key(str(row["method"]), str(row["path"])): row for row in architecture_api_routes()
    }
    rows: list[dict[str, object]] = []
    pairs: list[str] = []
    for binding in bindings:
        key = str(binding["key"])
        architecture = documented.get(key)
        pair = f"{binding['domain']}.{binding['action']}"
        pairs.append(pair)
        rows.append(
            {
                "key": key,
                "method": binding["method"],
                "path": binding["path"],
                "handler": binding["handler"],
                "source": binding["source"],
                "domain": binding["domain"],
                "action": binding["action"],
                "pair": pair,
                "architecture_documented": architecture is not None,
                "architecture_protected": bool(architecture["protected"]) if architecture else False,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": CHARTER_AUDIT_KIND,
        "routes": rows,
        "pairs": sorted(set(pairs)),
        "undocumented": sorted(row["key"] for row in rows if not row["architecture_documented"]),
    }


def get_charter_audit_row(route_id: str) -> dict[str, object]:
    """Return one charter-audit row by ``METHOD /path`` key."""

    if not isinstance(route_id, str):
        raise TypeError("route_id must be a string")
    normalized = " ".join(route_id.strip().split())
    if not normalized:
        raise ValueError("route_id must not be empty")
    parts = normalized.split(" ", 1)
    if len(parts) != 2:
        raise ValueError("route_id must be 'METHOD /path'")
    method, path = parts[0].upper(), parts[1]
    if not path.startswith("/"):
        path = f"/{path}"
    key = _route_key(method, path)
    for row in charter_audit_snapshot()["routes"]:
        if row["key"] == key:
            return dict(row)
    raise KeyError(f"unknown route: {key}")
