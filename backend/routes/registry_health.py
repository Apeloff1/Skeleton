"""
routes/registry_health.py — Tiny diagnostic router that exposes the live
route-registration report so the /api/health surface can show how many
routers were loaded vs skipped. Mounted under /api/health/registry.

This was added Feb 2026 alongside the routes_registry decomposition. It is
intentionally read-only — no mutation endpoints — so it can ship to prod
without rate-limit / auth concerns.
"""
from __future__ import annotations
import os
import time
from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])

# First-party product routes whose absence must fail deployment readiness.
# Optional plugins may degrade, but these shipped application capabilities may
# not silently disappear behind register_routes' optional import fallback.
# A required capability must mount its expected public endpoint; an unrelated
# route or empty APIRouter is never evidence of product readiness.
CRITICAL_ROUTE_PATHS: dict[str, str] = {
    "routes.creator_economy": "/api/creators",
    "routes.git_operations": "/api/git/status",
    "routes.jeeves_media": "/api/jeeves/media/types",
    "routes.lafs": "/api/lafs/stats",
    "routes.marketplace": "/api/marketplace/listings",
    "routes.sorting_vault": "/api/sorting-vault/connections",
    "routes.swarm_cold_legion": "/api/galaxy-studio/swarm/cold/stats",
    "routes.swarm_hub": "/api/galaxy-studio/swarm/agents",
}
CRITICAL_BOOT_ROUTERS = frozenset(CRITICAL_ROUTE_PATHS)

# Filled in by core.routes_registry.register_known_routes — the helper
# stores its last summary report here so we can surface it via API.
_LAST_REPORT: dict[str, Any] = {
    "ok": 0,
    "skipped": 0,
    "skipped_names": [],
    "at": 0.0,
}


def record_registry_report(report: dict[str, Any]) -> None:
    """Called from core.routes_registry.register_known_routes()."""
    global _LAST_REPORT
    _LAST_REPORT = {**report, "at": time.time()}


def critical_router_readiness() -> dict[str, Any]:
    """Bounded, I/O-free readiness check for required first-party routes.

    No exception details are exposed: health reports reveal only which
    declared application capabilities failed to mount or were unregistered.
    """
    from core.routes_registry import KNOWN_ROUTES, KNOWN_ROUTES_WITH_PREFIX

    registered = {entry[0] for entry in (*KNOWN_ROUTES, *KNOWN_ROUTES_WITH_PREFIX)}
    # A declared route is not a mounted route. Require positive evidence of
    # actual FastAPI registration from the current boot, not merely absence
    # from the skipped list (which could be truncated or malformed).
    mounted = _LAST_REPORT.get("mounted_names")
    observed_mounts = {
        item for item in mounted if isinstance(item, str)
    } if isinstance(mounted, list) else set()
    observed_paths = _LAST_REPORT.get("mounted_paths")
    route_paths = observed_paths if isinstance(observed_paths, dict) else {}
    checked = (
        bool(_LAST_REPORT.get("at"))
        and isinstance(mounted, list)
        and isinstance(observed_paths, dict)
        and int(_LAST_REPORT.get("ok", 0)) + int(_LAST_REPORT.get("skipped", 0)) > 0
    )
    missing = sorted(
        module for module, required_path in CRITICAL_ROUTE_PATHS.items()
        if module not in registered
        or module not in observed_mounts
        or not isinstance(route_paths.get(module), list)
        or required_path not in route_paths[module]
    )
    return {"ok": checked and not missing, "missing": missing, "report_available": checked}


@router.get("/registry")
async def registry_report() -> dict[str, Any]:
    """Last routes_registry registration summary — useful for verifying
    that no optional router got silently skipped during a deploy."""
    return {
        **_LAST_REPORT,
        "critical_routes": critical_router_readiness(),
        "now": time.time(),
        "age_s": (time.time() - _LAST_REPORT.get("at", 0.0)) if _LAST_REPORT.get("at") else None,
        "env": "production" if os.environ.get("EMERGENT_DEPLOY") else "dev",
    }
