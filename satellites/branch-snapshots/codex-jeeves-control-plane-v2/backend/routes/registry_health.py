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


@router.get("/registry")
async def registry_report() -> dict[str, Any]:
    """Last routes_registry registration summary — useful for verifying
    that no optional router got silently skipped during a deploy."""
    return {
        **_LAST_REPORT,
        "now": time.time(),
        "age_s": (time.time() - _LAST_REPORT.get("at", 0.0)) if _LAST_REPORT.get("at") else None,
        "env": "production" if os.environ.get("EMERGENT_DEPLOY") else "dev",
    }
