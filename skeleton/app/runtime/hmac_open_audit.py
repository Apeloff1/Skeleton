"""Import-free audit of HMAC open prefixes versus architecture.API_ROUTES.

Architecture ``protected: False`` is a charter/documentation flag. HMAC open
prefixes are a separate credential-seal skip list. Most documented-unprotected
routes still require an HMAC seal (missing secret → 503). This snapshot reports
that split without importing the API package or widening the open surface.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import (
    architecture_api_routes,
    hmac_default_open_prefixes,
    hmac_dev_open_prefixes,
    hmac_runtime_root_open,
    path_matches_open_prefix,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


HMAC_OPEN_AUDIT_KIND: Final = "hmac_open_audit"


def _route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def _hmac_open(path: str, prefixes: list[str]) -> bool:
    return any(path_matches_open_prefix(path, prefix) for prefix in prefixes if prefix)


def hmac_open_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable HMAC-open versus API_ROUTES audit."""

    prefixes = hmac_default_open_prefixes()
    documented = architecture_api_routes()
    rows: list[dict[str, object]] = []
    sealed_unprotected: list[str] = []
    open_protected: list[str] = []
    for route in documented:
        method = str(route["method"])
        path = str(route["path"])
        key = _route_key(method, path)
        architecture_protected = bool(route["protected"])
        hmac_open = _hmac_open(path, prefixes)
        sealed_but_documented_open = (not architecture_protected) and (not hmac_open)
        open_but_documented_protected = architecture_protected and hmac_open
        if sealed_but_documented_open:
            sealed_unprotected.append(key)
        if open_but_documented_protected:
            open_protected.append(key)
        rows.append(
            {
                "key": key,
                "method": method,
                "path": path,
                "architecture_protected": architecture_protected,
                "hmac_open": hmac_open,
                "hmac_sealed_but_documented_unprotected": sealed_but_documented_open,
                "hmac_open_but_documented_protected": open_but_documented_protected,
            }
        )
    documented_paths = [str(route["path"]) for route in documented]
    undocumented_open_prefixes = [
        prefix
        for prefix in prefixes
        if not any(path_matches_open_prefix(path, prefix) for path in documented_paths)
    ]
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": HMAC_OPEN_AUDIT_KIND,
        "open_prefixes": prefixes,
        "dev_open_prefixes": hmac_dev_open_prefixes(),
        "runtime_root_open": hmac_runtime_root_open(),
        "routes": rows,
        "hmac_sealed_unprotected": sealed_unprotected,
        "hmac_open_protected": open_protected,
        "undocumented_open_prefixes": undocumented_open_prefixes,
    }


def get_hmac_open_audit_row(route_id: str) -> dict[str, object]:
    """Return one HMAC-open audit row by ``METHOD /path`` key."""

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
    for row in hmac_open_audit_snapshot()["routes"]:
        if row["key"] == key:
            return dict(row)
    raise KeyError(f"unknown route: {key}")
