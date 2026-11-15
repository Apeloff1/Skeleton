"""Evidence-based GameForge coverage; source discovery never executes modules."""
from __future__ import annotations

import time
from pathlib import Path

from core.public_exception_route import PublicExceptionRoute
from fastapi import APIRouter, Depends, Query, Request
from fastapi.routing import APIRoute
from gameforge.coverage_inventory import InventoryCache
from routes.gameforge_auth import require_role

router = APIRouter(route_class=PublicExceptionRoute, prefix="/api/gameforge/coverage",
                   tags=["gameforge-coverage"], dependencies=[Depends(require_role("viewer"))])

_INVENTORY = InventoryCache(Path(__file__).resolve().parents[1] / "gameforge")

# Explicit registration contracts. Do not call these routes as health probes:
# even GET handlers may require an identity, contact a service or mutate state.
SUBSYSTEMS = (
    ("Auth + RBAC", "/api/auth", "/api/auth/me"),
    ("CNS Studio (14-gate)", "/api/gameforge/studio", "/api/gameforge/studio/flow"),
    ("MasterMap", "/api/gameforge/map", "/api/gameforge/map/overview"),
    ("Knowledge / free-API", "/api/gameforge/knowledge", "/api/gameforge/studio/jeeves/knowledge"),
    ("Build toolchains", "/api/gameforge/build", "/api/gameforge/build/toolchains"),
    ("Multi-agent runtime", "/api/gameforge/runtime", "/api/gameforge/runtime/status"),
    ("Strategic planning", "/api/gameforge/planning", "/api/gameforge/planning/plans"),
    ("Adversarial Jury Room", "/api/gameforge/jury", "/api/gameforge/jury/status"),
    ("Agent Tool System", "/api/gameforge/tools", "/api/gameforge/tools/status"),
    ("Persistent encrypted Vault", "/api/gameforge/studio/vault", None),
    ("Storage / Unbulk", "/api/storage", "/api/storage/savings"),
    ("Build ledger", "/api/galaxy-studio/builds", None),
)
LIVE_SUBSYSTEMS = [(name, prefix) for name, prefix, _ in SUBSYSTEMS]

# Historical archive claims are kept as provenance of the old dashboard,
# not counted as current verified parity. Original archive bytes and
# manifest-to-source mapping were not supplied to this source-only probe.
ZIP_AUDIT = (
    ("CNS_Zaibatsu_Final_Release_v1", 20),
    ("knowledge_nexus_v1", 69),
    ("Zaibatsu_Complete_Final", 146),
    ("gameforge_full_implementation_v1", 348),
    ("GameForge_Complete (1000-room catalog)", 565),
    ("Master_Release (tier1 gaps)", 12),
)


def route_inventory(routes) -> tuple[dict, ...]:
    """Inspect already-registered ASGI metadata only; never invoke a handler."""
    index: dict[str, set[str]] = {}
    for route in routes:
        if isinstance(route, APIRoute) and callable(route.endpoint):
            index.setdefault(route.path, set()).update(route.methods or ())
    results = []
    for name, prefix, exact in SUBSYSTEMS:
        matching = sorted(path for path in index if path == prefix or path.startswith(prefix + "/"))
        registered = bool("GET" in index.get(exact, set())) if exact else bool(matching)
        results.append({
            "name": name, "prefix": prefix, "expected_get": exact,
            "registered_routes": len(matching), "status": "registered" if registered else "missing_registration",
            "ok": registered, "runtime_qualified": False,
            "basis": "explicit_route_registration",
        })
    return tuple(results)


@router.get("/scan")
def scan(refresh: bool = False):
    return {"ok": True, **_INVENTORY.get(force=refresh).summary()}


@router.get("/sources")
def sources(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
            status: str = Query("engines", pattern="^(engines|errors|all)$")):
    return {"ok": True, **_INVENTORY.get().page(offset, limit, status)}


@router.post("/activate")
def activate():
    """Compatibility boundary: dynamic activation remains forbidden."""
    res = _INVENTORY.get(force=True).summary()
    return {"ok": False, "activated": 0, "blocked": res["discovered"],
            "unloadable": None, "unloadable_detail": [], "activation_allowed": False,
            "message": "Dynamic activation is disabled: discovered modules are inventory only. "
                       "Wire approved engines through explicit reviewed imports."}


@router.get("/selftest")
def selftest(request: Request):
    """Check static inventory and route registration; never claim live health."""
    t0 = time.monotonic()
    rows = list(route_inventory(request.app.routes))
    inventory = _INVENTORY.get()
    rows.append({"name": "Static source inventory", "ok": inventory.complete,
                 "basis": "bounded_ast_scan", "status": "parsed" if inventory.complete else "incomplete",
                 "runtime_qualified": False})
    passed = sum(bool(row["ok"]) for row in rows)
    return {"ok": True, "passed": passed, "total": len(rows),
            "registration_passed": passed == len(rows), "registration_complete": passed == len(rows), "ready": False,
            "scope": "static_registration_and_source_only",
            "production_qualified": False, "runtime_qualified": False,
            "inventory_sha256": inventory.manifest_sha256,
            "elapsed_ms": round((time.monotonic() - t0) * 1000, 1),
            "results": rows}


@router.get("")
def coverage(request: Request):
    snapshot = _INVENTORY.get()
    inventory = snapshot.summary()
    subsystems = list(route_inventory(request.app.routes))
    archives = [{"zip": name, "modules": count, "percent": None,
                 "status": "unverified_historical_inventory",
                 "verified_modules": None} for name, count in ZIP_AUDIT]
    return {
        "ok": True, "overall_percent": None,
        "coverage_basis": "archive_parity_not_established", "archive_qualification": "unverified",
        "production_qualified": False, "runtime_qualified": False,
        "subsystems": subsystems, "subsystem_count": len(subsystems),
        "registered_subsystems": sum(row["ok"] for row in subsystems),
        "registered_subsystem_count": sum(row["ok"] for row in subsystems),
        "zip_audit": archives, "historical_claimed_modules": sum(row["modules"] for row in archives),
        "engines": {"total": inventory["total_engine_modules"], **inventory},
    }
