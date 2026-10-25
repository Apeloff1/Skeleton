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
from routes.registry_health import CRITICAL_BOOT_ROUTERS, CRITICAL_ROUTE_PATHS


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
    assert CRITICAL_ROUTE_PATHS[module_path] in report["mounted_paths"][module_path]
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
            "mounted_paths": {
                name: [path] for name, path in CRITICAL_ROUTE_PATHS.items()
                if name != "routes.lafs"
            },
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
            "mounted_names": sorted(CRITICAL_BOOT_ROUTERS),
            "mounted_paths": {
                name: [path] for name, path in CRITICAL_ROUTE_PATHS.items()
            },
            "at": 1.0,
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
            "mounted_paths": {
                name: [path] for name, path in CRITICAL_ROUTE_PATHS.items()
                if name != "routes.marketplace"
            },
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


def test_partial_router_mount_is_rolled_back_and_later_router_can_mount(monkeypatch) -> None:
    """A router failure must not leave privileged or misleading partial routes."""
    from types import SimpleNamespace
    from fastapi import APIRouter
    from core import routes_registry

    router = APIRouter()
    @router.get("/registered")
    def registered() -> dict[str, bool]:
        return {"ok": True}

    actual_import = routes_registry.importlib.import_module

    def fake_import(name: str):
        if name in {"routes.partial_mount", "routes.working_mount"}:
            return SimpleNamespace(router=router)
        return actual_import(name)

    monkeypatch.setattr(routes_registry.importlib, "import_module", fake_import)
    app = FastAPI()
    actual_include = app.include_router
    calls = 0

    def include_once_then_fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        actual_include(*args, **kwargs)
        if calls == 1:
            raise RuntimeError("simulated partial mount failure")

    monkeypatch.setattr(app, "include_router", include_once_then_fail)
    report = register_routes(
        app,
        [("routes.partial_mount", "router"), ("routes.working_mount", "router")],
    )
    assert report["ok"] == 1
    assert report["skipped"] == 1
    assert report["mounted_names"] == ["routes.working_mount"]
    assert "routes.partial_mount (import_failed RuntimeError)" in report["skipped_names"]
    # FastAPI may preserve the router as an included wrapper with no .path.
    # Verify the registered endpoint from the authenticated registry report.
    assert report["mounted_paths"]["routes.working_mount"].count("/registered") == 1
    assert len(app.routes) == 5

def test_critical_router_with_wrong_path_is_not_marked_ready(monkeypatch) -> None:
    mounted_paths = {
        name: [path] for name, path in CRITICAL_ROUTE_PATHS.items()
    }
    mounted_paths["routes.marketplace"] = ["/api/unrelated"]
    monkeypatch.setattr(
        registry_health, "_LAST_REPORT",
        {
            "ok": 200, "skipped": 0, "skipped_names": [],
            "mounted_names": sorted(CRITICAL_BOOT_ROUTERS),
            "mounted_paths": mounted_paths, "at": 1.0,
        },
    )
    status = registry_health.critical_router_readiness()
    assert status["report_available"] is True
    assert status["ok"] is False
    assert status["missing"] == ["routes.marketplace"]


def test_expected_critical_paths_are_unique_and_canonical() -> None:
    assert frozenset(CRITICAL_ROUTE_PATHS) == CRITICAL_BOOT_ROUTERS
    assert len(set(CRITICAL_ROUTE_PATHS.values())) == len(CRITICAL_BOOT_ROUTERS)
    assert all(path.startswith("/api/") for path in CRITICAL_ROUTE_PATHS.values())



def test_nested_fastapi_router_mount_reports_real_leaf_paths(monkeypatch) -> None:
    """Modern FastAPI mounts router wrappers rather than flattening routes."""
    from fastapi import APIRouter
    from types import SimpleNamespace
    from core import routes_registry

    leaf = APIRouter(prefix="/api/leaf")

    @leaf.get("/status")
    def status():
        return {"ok": True}

    original_import = routes_registry.importlib.import_module

    def import_leaf(name: str):
        if name == "routes.synthetic_leaf":
            return SimpleNamespace(router=leaf)
        return original_import(name)

    monkeypatch.setattr(routes_registry.importlib, "import_module", import_leaf)
    app = FastAPI()

    def nested_include(router, *, prefix=""):
        app.router.routes.append(
            SimpleNamespace(original_router=router, prefix=prefix)
        )

    monkeypatch.setattr(app, "include_router", nested_include)
    report = register_routes(app, [("routes.synthetic_leaf", "router", "/nested")])
    assert report["ok"] == 1, report
    assert report["skipped"] == 0
    assert report["mounted_paths"]["routes.synthetic_leaf"] == [
        "/nested/api/leaf/status"
    ]


def test_noop_router_inclusion_never_claims_a_capability(monkeypatch) -> None:
    """Declaring endpoints is not proof that FastAPI mounted anything."""
    from fastapi import APIRouter
    from types import SimpleNamespace
    from core import routes_registry

    leaf = APIRouter(prefix="/api/leaf")

    @leaf.get("/status")
    def status():
        return {"ok": True}

    original_import = routes_registry.importlib.import_module

    def import_leaf(name: str):
        if name == "routes.unmounted_leaf":
            return SimpleNamespace(router=leaf)
        return original_import(name)

    monkeypatch.setattr(routes_registry.importlib, "import_module", import_leaf)
    app = FastAPI()
    monkeypatch.setattr(app, "include_router", lambda *_args, **_kwargs: None)
    report = register_routes(app, [("routes.unmounted_leaf", "router")])
    assert report["ok"] == 0
    assert report["skipped"] == 1
    assert report["mounted_names"] == []
    assert "routes.unmounted_leaf (empty_router)" in report["skipped_names"]
    assert not any(getattr(item, "original_router", None) is leaf for item in app.routes)



def test_nested_include_context_preserves_each_parent_prefix(monkeypatch) -> None:
    """Every preserved FastAPI include_context prefix composes into the URL."""
    from fastapi import APIRouter
    from types import SimpleNamespace
    from core import routes_registry

    leaf = APIRouter(prefix="/api/leaf")

    @leaf.get("/status")
    def status():
        return {"ok": True}

    middle = SimpleNamespace(routes=[
        SimpleNamespace(
            original_router=leaf,
            include_context=SimpleNamespace(prefix="/middle"),
        ),
    ])
    original_import = routes_registry.importlib.import_module

    def import_nested(name: str):
        if name == "routes.synthetic_nested":
            return SimpleNamespace(router=middle)
        return original_import(name)

    monkeypatch.setattr(routes_registry.importlib, "import_module", import_nested)
    app = FastAPI()

    def nested_include(router, *, prefix=""):
        app.router.routes.append(
            SimpleNamespace(original_router=router, include_context=SimpleNamespace(prefix=prefix))
        )

    monkeypatch.setattr(app, "include_router", nested_include)
    report = register_routes(app, [("routes.synthetic_nested", "router", "/outer")])
    assert report["ok"] == 1
    assert report["mounted_paths"]["routes.synthetic_nested"] == [
        "/outer/middle/api/leaf/status"
    ]


def test_unrelated_mount_cannot_fabricate_registered_capability(monkeypatch) -> None:
    """Appending a different router does not prove the requested router mounted."""
    from fastapi import APIRouter
    from types import SimpleNamespace
    from core import routes_registry

    requested = APIRouter(prefix="/api/real")

    @requested.get("/ready")
    def ready():
        return {"ok": True}

    unrelated = APIRouter(prefix="/api/unrelated")
    original_import = routes_registry.importlib.import_module

    def import_requested(name: str):
        if name == "routes.requested_only":
            return SimpleNamespace(router=requested)
        return original_import(name)

    monkeypatch.setattr(routes_registry.importlib, "import_module", import_requested)
    app = FastAPI()
    monkeypatch.setattr(
        app, "include_router",
        lambda *_args, **_kwargs: app.router.routes.append(SimpleNamespace(original_router=unrelated)),
    )
    report = register_routes(app, [("routes.requested_only", "router")])
    assert report["ok"] == 0
    assert report["skipped"] == 1
    assert report["mounted_names"] == []
    assert not any(getattr(item, "original_router", None) is unrelated for item in app.routes)


def test_unrelated_flattened_route_cannot_claim_requested_mount(monkeypatch) -> None:
    """Direct-route additions must belong to the requested API capability."""
    from fastapi import APIRouter
    from types import SimpleNamespace
    from core import routes_registry

    requested = APIRouter(prefix="/api/requested")

    @requested.get("/ready")
    def ready():
        return {"ready": True}

    foreign = APIRouter(prefix="/api/foreign")

    @foreign.get("/ready")
    def foreign_ready():
        return {"ready": False}

    original_import = routes_registry.importlib.import_module

    def import_requested(name: str):
        if name == "routes.requested_direct":
            return SimpleNamespace(router=requested)
        return original_import(name)

    monkeypatch.setattr(routes_registry.importlib, "import_module", import_requested)
    app = FastAPI()

    def substitute_foreign(_router, *, prefix=""):
        # Exercises old FastAPI's flattened route tree, not a nested wrapper.
        app.router.routes.extend(foreign.routes)

    monkeypatch.setattr(app, "include_router", substitute_foreign)
    report = register_routes(app, [("routes.requested_direct", "router")])
    assert report["ok"] == 0
    assert report["skipped"] == 1
    assert report["mounted_names"] == []
    assert "routes.requested_direct (empty_router)" in report["skipped_names"]
    assert all(route.path != "/api/foreign/ready" for route in app.routes)


def test_flattened_foreign_route_with_same_path_cannot_claim_target(monkeypatch) -> None:
    """The same URL must not attest a different router's endpoint."""
    from fastapi import APIRouter
    from types import SimpleNamespace
    from core import routes_registry

    wanted = APIRouter(prefix="/api/studio")

    @wanted.get("/ready")
    def wanted_ready():
        return {"ready": True}

    foreign = APIRouter(prefix="/api/studio")

    @foreign.get("/ready")
    def foreign_ready():
        return {"ready": False}

    initial_import = routes_registry.importlib.import_module

    def fake_import(name: str):
        if name == "routes.requested_identity":
            return SimpleNamespace(router=wanted)
        return initial_import(name)

    monkeypatch.setattr(routes_registry.importlib, "import_module", fake_import)
    app = FastAPI()
    monkeypatch.setattr(
        app, "include_router",
        lambda _router, **_kwargs: app.router.routes.extend(foreign.routes),
    )

    report = register_routes(app, [("routes.requested_identity", "router")])
    assert report["ok"] == 0
    assert report["skipped_names"] == ["routes.requested_identity (empty_router)"]
    assert all(route.path != "/api/studio/ready" for route in app.routes)
