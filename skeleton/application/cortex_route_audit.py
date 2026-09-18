"""Import-free audit of unmounted cortex ``register_routes`` versus API_ROUTES.

Cortex handlers bind nested ``@app.get`` inside ``register_routes`` and are
never ``include_router``'d by ``create_app``. Main-router F-19 coverage does
not see them. This snapshot reports that without importing cortex or restoring
CommandDeck.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import architecture_api_routes, cortex_route_handlers
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


CORTEX_ROUTE_AUDIT_KIND: Final = "cortex_route_audit"


def _route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def cortex_route_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable unmounted-cortex documentation audit."""

    handlers = cortex_route_handlers()
    documented = architecture_api_routes()
    documented_map = {_route_key(str(row["method"]), str(row["path"])): row for row in documented}
    handler_keys = {_route_key(str(row["method"]), str(row["path"])) for row in handlers}
    rows: list[dict[str, object]] = []
    protected_mismatch: list[str] = []
    for handler in handlers:
        key = _route_key(str(handler["method"]), str(handler["path"]))
        architecture = documented_map.get(key)
        architecture_protected = bool(architecture["protected"]) if architecture else False
        charter_gated = bool(handler["charter_gated"])
        seal_gated = bool(handler["seal_gated"])
        drift = architecture is not None and architecture_protected != charter_gated
        if drift:
            protected_mismatch.append(key)
        rows.append(
            {
                "key": key,
                "method": handler["method"],
                "path": handler["path"],
                "handler": handler["handler"],
                "source": handler["source"],
                "architecture_documented": architecture is not None,
                "charter_gated": charter_gated,
                "seal_gated": seal_gated,
                "architecture_protected": architecture_protected,
                "protected_drift": drift,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": CORTEX_ROUTE_AUDIT_KIND,
        "routes": rows,
        "missing_from_architecture": sorted(key for key in handler_keys if key not in documented_map),
        "protected_mismatch": protected_mismatch,
    }


def get_cortex_route_audit_row(route_id: str) -> dict[str, object]:
    """Return one cortex-route audit row by ``METHOD /path`` key."""

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
    for row in cortex_route_audit_snapshot()["routes"]:
        if row["key"] == key:
            return dict(row)
    raise KeyError(f"unknown route: {key}")
