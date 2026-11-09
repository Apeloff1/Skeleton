"""Import-free audit of main-router handlers versus architecture.API_ROUTES."""

from __future__ import annotations

from typing import Final

from .audit_parse import architecture_api_routes, main_router_handlers
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


API_ROUTE_AUDIT_KIND: Final = "api_route_audit"


def _route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def api_route_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable main-router documentation audit."""

    handlers = main_router_handlers()
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
        drift = architecture is not None and architecture_protected != charter_gated
        if drift:
            protected_mismatch.append(key)
        rows.append(
            {
                "key": key,
                "method": handler["method"],
                "path": handler["path"],
                "handler": handler["handler"],
                "architecture_documented": architecture is not None,
                "charter_gated": charter_gated,
                "architecture_protected": architecture_protected,
                "protected_drift": drift,
            }
        )
    missing_from_architecture = sorted(key for key in handler_keys if key not in documented_map)
    missing_from_handlers = sorted(key for key in documented_map if key not in handler_keys)
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": API_ROUTE_AUDIT_KIND,
        "routes": rows,
        "missing_from_architecture": missing_from_architecture,
        "missing_from_handlers": missing_from_handlers,
        "protected_mismatch": protected_mismatch,
    }


def get_api_route_audit_row(route_id: str) -> dict[str, object]:
    """Return one route-audit row by ``METHOD /path`` key."""

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
    for row in api_route_audit_snapshot()["routes"]:
        if row["key"] == key:
            return dict(row)
    raise KeyError(f"unknown route: {key}")
