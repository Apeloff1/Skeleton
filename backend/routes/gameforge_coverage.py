"""Truthful GameForge coverage and non-executable source inventory."""
from __future__ import annotations

from pathlib import Path
import threading
import time
from fastapi import APIRouter, Request
from core.public_exception_route import PublicExceptionRoute
from gameforge.coverage_inventory import scan_source, route_registration

router = APIRouter(route_class=PublicExceptionRoute, prefix="/api/gameforge/coverage", tags=["gameforge-coverage"])
_GAMEFORGE = Path(__file__).resolve().parents[1] / "gameforge"
LIVE_SUBSYSTEMS = [
    ("Auth + RBAC", "/api/auth"),
    ("CNS Studio (14-gate)", "/api/gameforge/studio"),
    ("MasterMap", "/api/gameforge/map"),
    ("Knowledge / free-API", "/api/gameforge/knowledge"),
    ("Build toolchains", "/api/gameforge/build"),
    ("Multi-agent runtime", "/api/gameforge/runtime"),
    ("Strategic planning", "/api/gameforge/planning"),
    ("Adversarial Jury Room", "/api/gameforge/jury"),
    ("Agent Tool System", "/api/gameforge/tools"),
    ("Persistent encrypted Vault", "/api/gameforge/studio/vault"),
    ("Storage / Unbulk", "/api/storage"),
    ("Build ledger", "/api/galaxy-studio/builds"),
]
# Historical denominators remain visible without pretending archive manifests,
# correspondence or operational behavior were verified.
ZIP_AUDIT = [
    {"zip": name, "modules": count, "percent": None, "status": "historical_unverified"}
    for name, count in [
        ("CNS_Zaibatsu_Final_Release_v1", 20),
        ("knowledge_nexus_v1", 69),
        ("Zaibatsu_Complete_Final", 146),
        ("gameforge_full_implementation_v1", 348),
        ("GameForge_Complete (1000-room catalog)", 565),
        ("Master_Release (tier1 gaps)", 12),
    ]
]
_CACHE_SECONDS = 60
_scan_cache: dict = {}
_scan_lock = threading.Lock()
_last_scan = 0.0


def _scan(force=False) -> dict:
    global _last_scan
    with _scan_lock:
        if not _scan_cache or (force and time.monotonic() - _last_scan >= 5) or time.monotonic() - _last_scan >= _CACHE_SECONDS:
            evidence = scan_source(_GAMEFORGE)
            rows = evidence.pop("modules")
            count = len(rows)
            _scan_cache.clear()
            _scan_cache.update(evidence, total_engine_modules=count, discovered=count,
                               live=0, failed=0, dormant_now=None, unqualified=count,
                               activation_allowed=False, discovered_detail=[r["module"] for r in rows[:100]],
                               module_evidence=rows[:100], detail_truncated=count > 100,
                               qualification="source_inventory_only", ts=time.time(), failed_detail=[])
            _last_scan = time.monotonic()
        return dict(_scan_cache)


def _iter_engine_modules() -> list[str]:
    """Compatibility helper that inventories the complete bounded source subset."""
    return [row["module"] for row in scan_source(_GAMEFORGE)["modules"]]


@router.get("/scan")
def scan():
    return {"ok": True, **_scan()}


@router.post("/activate")
def activate():
    res = _scan(force=True)
    return {"ok": False, "activated": 0, "blocked": res["discovered"],
            "unloadable": None, "unloadable_detail": [],
            "message": ("Dynamic activation is disabled: refreshed source inventory. "
                        "Discovered classes require explicit reviewed wiring and runtime qualification.")}


@router.get("/selftest")
def selftest(request: Request):
    results = route_registration(request.app.routes, LIVE_SUBSYSTEMS)
    passed = sum(row["ok"] for row in results)
    return {"ok": True, "passed": passed, "total": len(results),
            "registration_complete": passed == len(results), "ready": False,
            "scope": "route_registration_only", "results": results}


@router.get("")
def coverage(request: Request):
    result = _scan()
    rows = route_registration(request.app.routes, LIVE_SUBSYSTEMS)
    return {"ok": True, "overall_percent": None, "archive_qualification": "unverified",
            "subsystems": rows, "subsystem_count": len(rows),
            "registered_subsystem_count": sum(row["ok"] for row in rows), "zip_audit": ZIP_AUDIT,
            "engines": {"total": result["total_engine_modules"], "discovered": result["discovered"],
                        "live": 0, "failed": 0, "unqualified": result["unqualified"],
                        "activation_allowed": False, "complete_inventory": result["complete"],
                        "inventory_sha256": result["inventory_sha256"]}}
