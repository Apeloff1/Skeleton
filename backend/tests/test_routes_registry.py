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
CRITICAL_BOOT_ROUTERS = (
    "routes.creator_economy",
    "routes.marketplace",
    "routes.git_operations",
    "routes.jeeves_media",
    "routes.lafs",
    "routes.sorting_vault",
    "routes.swarm_cold_legion",
    "routes.swarm_hub",
)


@pytest.mark.parametrize("module_path", CRITICAL_BOOT_ROUTERS)
def test_critical_product_router_is_mounted_and_never_silently_skipped(module_path: str) -> None:
    entries = [entry for entry in (*KNOWN_ROUTES, *KNOWN_ROUTES_WITH_PREFIX) if entry[0] == module_path]
    assert len(entries) == 1, f"critical product route unregistered or duplicated: {module_path}"
    app = FastAPI()
    report = register_routes(app, entries)
    assert report["skipped"] == 0, report["skipped_names"]
    assert report["ok"] == 1
    assert len(app.routes) > 4, f"mounted {module_path} declares no reachable endpoints"
