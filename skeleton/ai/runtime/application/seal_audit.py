"""Import-free audit of live HMAC-seal gates versus charter and open prefixes.

``Depends(require_seal)`` is the explicit credential gate. ``require_charter``
composes it transitively. Command dispatch calls ``require_seal`` in-body for
``auth_required`` commands. This snapshot reports that split against default
HMAC open prefixes without widening them.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import (
    hmac_default_open_prefixes,
    live_handler_rows,
    path_matches_open_prefix,
    sidecar_router_handlers,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


SEAL_AUDIT_KIND: Final = "seal_audit"


def _route_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"


def _hmac_open(path: str, prefixes: list[str]) -> bool:
    return any(path_matches_open_prefix(path, prefix) for prefix in prefixes if prefix)


def seal_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable live-handler seal-gate audit."""

    prefixes = hmac_default_open_prefixes()
    rows: list[dict[str, object]] = []
    explicit: list[str] = []
    called: list[str] = []
    charter: list[str] = []
    open_and_sealed: list[str] = []
    for handler in live_handler_rows():
        path = str(handler["path"])
        key = _route_key(str(handler["method"]), path)
        depends_seal = bool(handler.get("seal_gated", False))
        calls_seal = bool(handler.get("calls_seal", False))
        charter_gated = bool(handler.get("charter_gated", False))
        hmac_open = _hmac_open(path, prefixes)
        explicit_seal = depends_seal or calls_seal
        if depends_seal:
            explicit.append(key)
        if calls_seal:
            called.append(key)
        if charter_gated:
            charter.append(key)
        if hmac_open and explicit_seal:
            open_and_sealed.append(key)
        rows.append(
            {
                "key": key,
                "method": handler["method"],
                "path": path,
                "handler": handler["handler"],
                "surface": handler["surface"],
                "depends_seal": depends_seal,
                "calls_seal": calls_seal,
                "charter_gated": charter_gated,
                "hmac_open": hmac_open,
                "explicit_seal": explicit_seal,
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": SEAL_AUDIT_KIND,
        "routes": rows,
        "depends_seal": explicit,
        "calls_seal": called,
        "charter_gated": charter,
        "hmac_open_and_seal_gated": open_and_sealed,
        "charter_without_explicit_seal": [
            str(row["key"]) for row in rows if row["charter_gated"] and not row["explicit_seal"]
        ],
        "sidecar_depends_seal": [
            f"{row['method']} {row['path']}"
            for row in sidecar_router_handlers()
            if row.get("seal_gated")
        ],
    }


def get_seal_audit_row(route_id: str) -> dict[str, object]:
    """Return one seal-audit row by ``METHOD /path`` key."""

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
    for row in seal_audit_snapshot()["routes"]:
        if row["key"] == key:
            return dict(row)
    raise KeyError(f"unknown route: {key}")
