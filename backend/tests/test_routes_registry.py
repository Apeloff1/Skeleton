"""
backend/tests/test_routes_registry.py — smoke test for the declarative
router registration helper. Validates:

  • KNOWN_ROUTES + KNOWN_ROUTES_WITH_PREFIX are non-empty.
  • Every entry's first element is a real module path resolvable via importlib.
  • Every entry's `attr` name resolves to something that looks like an APIRouter.
  • No duplicate (module, attr) pairs.

Run via:  python -m pytest backend/tests/test_routes_registry.py -q
"""
from __future__ import annotations
import importlib

import pytest
from fastapi import FastAPI

from core.routes_registry import KNOWN_ROUTES, KNOWN_ROUTES_WITH_PREFIX, register_routes
from routes import registry_health
from routes.registry_health import CRITICAL_BOOT_ROUTERS


def _flat_pairs():
    """Yield (module, attr, prefix-or-None) for every declared entry."""
    for e in KNOWN_ROUTES:
        if len(e) == 2:
            yield e[0], e[1], None
        else:
            yield e[0], e[1], e[2]
    for e in KNOWN_ROUTES_WITH_PREFIX:
        if len(e) == 2:
            yield e[0], e[1], None
        else:
            yield e[0], e[1], e[2]


def test_known_routes_nonempty():
    assert len(KNOWN_ROUTES) > 0
    assert len(KNOWN_ROUTES_WITH_PREFIX) > 0


def test_no_duplicate_entries():
    seen = set()
    for mod, attr, _ in _flat_pairs():
        key = (mod, attr)
        assert key not in seen, f"duplicate routes_registry entry: {key!r}"
        seen.add(key)


@pytest.mark.parametrize("module_path,attr,prefix", list(_flat_pairs()))
def test_each_module_importable(module_path: str, attr: str, prefix):
    """Every declared module must import without raising — the lazy SKIP
    fallback only catches *runtime* errors at register time; structural
    failures (typo'd module name) should surface here."""
    try:
        mod = importlib.import_module(module_path)
    except Exception as e:
        pytest.skip(f"optional router unavailable: {module_path} → {type(e).__name__}: {e}")
    assert hasattr(mod, attr), f"{module_path} missing attribute {attr!r}"


# Formerly silent boot regressions (#4133). These eight first-party routers are
# shipped with the application; an import failure must not be skipped as if the
# missing endpoint were an optional third-party plugin.

@pytest.mark.parametrize("module_path", CRITICAL_BOOT_ROUTERS)
def test_critical_product_router_is_mounted_and_never_silently_skipped(module_path: str) -> None:
    entries = [entry for entry in (*KNOWN_ROUTES, *KNOWN_ROUTES_WITH_PREFIX) if entry[0] == module_path]
    assert len(entries) == 1, f"critical product route unregistered or duplicated: {module_path}"
    app = FastAPI()
    report = register_routes(app, entries)
    assert report["skipped"] == 0, report["skipped_names"]
    assert report["ok"] == 1
    assert report["mounted_names"] == [module_path]
    assert len(app.routes) > 4, f"mounted {module_path} declares no reachable endpoints"


def test_critical_route_readiness_requires_real_registry_report(monkeypatch) -> None:
    monkeypatch.setattr(
        registry_health,
        "_LAST_REPORT",
        {"ok": 0, "skipped": 0, "skipped_names": [], "at": 0.0},
    )
    status = registry_health.critical_router_readiness()
    assert status["ok"] is False
    assert status["report_available"] is False


def test_critical_route_readiness_fails_closed_on_import_skip(monkeypatch) -> None:
    monkeypatch.setattr(
        registry_health,
        "_LAST_REPORT",
        {
            "ok": 200,
            "skipped": 1,
            "skipped_names": ["routes.lafs (import_failed RuntimeError: dependency unavailable)"],
            "mounted_names": sorted(CRITICAL_BOOT_ROUTERS - {"routes.lafs"}),
            "at": 1.0,
        },
    )
    status = registry_health.critical_router_readiness()
    assert status["ok"] is False
    assert status["report_available"] is True
    assert status["missing"] == ["routes.lafs"]
    assert "RuntimeError" not in str(status)


def test_critical_route_readiness_accepts_complete_report(monkeypatch) -> None:
    monkeypatch.setattr(
        registry_health,
        "_LAST_REPORT",
        {
            "ok": 200, "skipped": 0, "skipped_names": [],
            "mounted_names": sorted(CRITICAL_BOOT_ROUTERS), "at": 1.0,
        },
    )
    status = registry_health.critical_router_readiness()
    assert status == {"ok": True, "missing": [], "report_available": True}


def test_critical_route_readiness_rejects_missing_positive_mount_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        registry_health, "_LAST_REPORT",
        {"ok": 200, "skipped": 0, "skipped_names": [], "at": 1.0},
    )
    report = registry_health.critical_router_readiness()
    assert report["ok"] is False
    assert report["report_available"] is False
    assert set(report["missing"]) == CRITICAL_BOOT_ROUTERS


def test_critical_route_readiness_rejects_silent_absent_mount(monkeypatch) -> None:
    monkeypatch.setattr(
        registry_health, "_LAST_REPORT",
        {
            "ok": 200, "skipped": 0, "skipped_names": [],
            "mounted_names": sorted(CRITICAL_BOOT_ROUTERS - {"routes.marketplace"}),
            "at": 1.0,
        },
    )
    report = registry_health.critical_router_readiness()
    assert report == {
        "ok": False, "report_available": True, "missing": ["routes.marketplace"],
    }


def test_empty_router_does_not_report_successful_mount(monkeypatch) -> None:
    from fastapi import APIRouter
    from types import SimpleNamespace
    from core import routes_registry

    original_import = routes_registry.importlib.import_module
    def import_router(name: str):
        if name == "routes.fake_empty":
            return SimpleNamespace(router=APIRouter())
        return original_import(name)
    monkeypatch.setattr(routes_registry.importlib, "import_module", import_router)
    app = FastAPI()
    report = register_routes(app, [("routes.fake_empty", "router")])
    assert report["ok"] == 0
    assert report["skipped"] == 1
    assert report["mounted_names"] == []
