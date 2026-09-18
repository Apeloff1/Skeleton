"""Import-free audit of create_app inline ``@app`` handlers versus API_ROUTES.

``create_app`` binds ``GET /`` and ``GET /cortex/status`` directly on the
FastAPI app. Those handlers are neither main-router F-19 coverage nor the
unmounted cortex ``register_routes`` snapshot. This reports that split
without importing the API package or adding them to ``API_ROUTES``.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import architecture_api_routes, create_app_inline_handlers
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


APP_ROUTE_AUDIT_KIND: Final = "app_route_audit"


def _route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def app_route_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable create_app inline-handler audit."""

    handlers = create_app_inline_handlers()
    documented = architecture_api_routes()
    documented_map = {_route_key(str(row["method"]), str(row["path"])): row for row in documented}
    handler_keys = {_route_key(str(row["method"]), str(row["path"])) for row in handlers}
    rows: list[dict[str, object]] = []
    for handler in handlers:
        key = _route_key(str(handler["method"]), str(handler["path"]))
        architecture = documented_map.get(key)
        rows.append(
            {
                "key": key,
                "method": handler["method"],
                "path": handler["path"],
                "handler": handler["handler"],
                "source": handler["source"],
                "architecture_documented": architecture is not None,
                "charter_gated": bool(handler["charter_gated"]),
                "seal_gated": bool(handler["seal_gated"]),
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": APP_ROUTE_AUDIT_KIND,
        "routes": rows,
        "missing_from_architecture": sorted(key for key in handler_keys if key not in documented_map),
    }


def get_app_route_audit_row(route_id: str) -> dict[str, object]:
    """Return one create_app inline-handler audit row by ``METHOD /path`` key."""

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
    for row in app_route_audit_snapshot()["routes"]:
        if row["key"] == key:
            return dict(row)
    raise KeyError(f"unknown route: {key}")
