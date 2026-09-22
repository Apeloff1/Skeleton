"""Import-free audit of HMAC/charter gate domains versus architecture.API_ROUTES.

``GatePolicy.required_domain`` is longest-prefix match over ``DEFAULT_DOMAIN_MAP``.
Unmapped paths 404 at the seal. Prefixes such as ``/cockpit`` and ``/cortex``
have no documented API_ROUTES row. This snapshot reports that split without
importing the API package or widening the domain map.
"""

from __future__ import annotations

from typing import Final

from .audit_parse import (
    architecture_api_routes,
    gate_domain_map,
    matching_gate_domain,
    path_matches_open_prefix,
)
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


GATE_DOMAIN_AUDIT_KIND: Final = "gate_domain_audit"


def gate_domain_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable gate-domain versus API_ROUTES audit."""

    documented = architecture_api_routes()
    domains = gate_domain_map()
    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    unmapped: list[str] = []
    for route in documented:
        path = str(route["path"])
        if path in seen:
            continue
        seen.add(path)
        domain = matching_gate_domain(path, domains)
        if domain is None:
            unmapped.append(path)
        rows.append(
            {
                "path": path,
                "domain": domain,
                "mapped": domain is not None,
                "architecture_documented": True,
            }
        )
    unused: list[dict[str, object]] = []
    for prefix, domain in domains:
        if not any(path_matches_open_prefix(path, prefix) for path in seen):
            unused.append({"prefix": prefix, "domain": domain})
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": GATE_DOMAIN_AUDIT_KIND,
        "domains": [{"prefix": prefix, "domain": domain} for prefix, domain in domains],
        "routes": rows,
        "unmapped_documented": unmapped,
        "unused_prefixes": unused,
    }


def get_gate_domain_audit_row(path: str) -> dict[str, object]:
    """Return one gate-domain audit row by documented path."""

    if not isinstance(path, str):
        raise TypeError("path must be a string")
    normalized = path.strip()
    if not normalized:
        raise ValueError("path must not be empty")
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    for row in gate_domain_audit_snapshot()["routes"]:
        if row["path"] == normalized:
            return dict(row)
    raise KeyError(f"unknown path: {normalized}")
