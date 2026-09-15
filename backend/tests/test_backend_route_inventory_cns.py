from pathlib import Path

from scripts.backend_route_inventory import build_inventory


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_cns_runtime_manifest_expands_dynamic_child_routers_without_boot(tmp_path: Path):
    backend = tmp_path / "backend"
    registry = backend / "core" / "routes_registry.py"
    routes = backend / "routes"
    write(
        registry,
        "KNOWN_ROUTES_WITH_PREFIX = []\n"
        "KNOWN_ROUTES = [('routes.gameforge_cns', 'router')]\n",
    )
    write(
        routes / "gameforge_cns.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/gameforge')\n"
        "for module in []:\n"
        "    router.include_router(module.router)\n",
    )

    # Materialize the fixed in-repo CNS modules expected by the inventory
    # manifest. Each gets one unique path so the aggregate is easy to prove.
    modules = (
        "diaries",
        "scim",
        "personal_logs",
        "calendar_api",
        "neuro_api",
        "decade_logs_api",
        "coherence_api",
        "math_api",
        "exocortex_api",
        "security_api",
    )
    for name in modules:
        write(
            backend / "gameforge" / "api" / f"{name}.py",
            "from fastapi import APIRouter\n"
            f"router = APIRouter(prefix='/{name}')\n"
            "@router.get('/health')\n"
            "def health(): pass\n",
        )

    report = build_inventory(registry, routes)

    assert report.unresolved_count == 0
    assert report.route_count == len(modules)
    assert report.duplicate_route_count == 0
    assert {row.path for row in report.routes} == {
        f"/api/gameforge/{name}/health" for name in modules
    }
