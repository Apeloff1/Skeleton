"""Import-free HMAC open-prefix audit against live handler paths.

F-21 compares HMAC prefixes to ``architecture.API_ROUTES``. Live handlers also
exist on sidecars, swarm mounts, cortex, and create_app inline routes. This
snapshot reports default-prefix openness across that union without widening
``DEFAULT_OPEN_PREFIXES``.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import (
    hmac_default_open_prefixes,
    hmac_dev_open_prefixes,
    hmac_runtime_root_open,
    live_handler_rows,
    path_matches_open_prefix,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


LIVE_HMAC_AUDIT_KIND: Final = "live_hmac_audit"


def _route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def _hmac_open(path: str, prefixes: list[str]) -> bool:
    return any(path_matches_open_prefix(path, prefix) for prefix in prefixes if prefix)


def live_hmac_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable live-handler HMAC-open audit."""

    prefixes = hmac_default_open_prefixes()
    handlers = live_handler_rows()
    rows: list[dict[str, object]] = []
    open_live: list[str] = []
    for handler in handlers:
        path = str(handler["path"])
        key = _route_key(str(handler["method"]), path)
        opened = _hmac_open(path, prefixes)
        if opened:
            open_live.append(key)
        rows.append(
            {
                "key": key,
                "method": handler["method"],
                "path": path,
                "handler": handler["handler"],
                "surface": handler["surface"],
                "source": handler["source"],
                "hmac_open": opened,
            }
        )
    live_paths = [str(handler["path"]) for handler in handlers]
    undocumented_open_prefixes = [
        prefix
        for prefix in prefixes
        if not any(path_matches_open_prefix(path, prefix) for path in live_paths)
    ]
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": LIVE_HMAC_AUDIT_KIND,
        "open_prefixes": prefixes,
        "dev_open_prefixes": hmac_dev_open_prefixes(),
        "runtime_root_open": hmac_runtime_root_open(),
        "routes": rows,
        "hmac_open_live": open_live,
        "undocumented_open_prefixes": undocumented_open_prefixes,
    }


def get_live_hmac_audit_row(route_id: str) -> dict[str, object]:
    """Return one live-HMAC audit row by ``METHOD /path`` key."""

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
    for row in live_hmac_audit_snapshot()["routes"]:
        if row["key"] == key:
            return dict(row)
    raise KeyError(f"unknown route: {key}")
