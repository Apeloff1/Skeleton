from __future__ import annotations

from pathlib import Path

from core.route_islands import build_route_island_report


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_route_island_audit_classifies_registered_embedded_and_orphan(tmp_path: Path):
    _write(
        tmp_path / "routes" / "registered.py",
        "from fastapi import APIRouter\nrouter = APIRouter(prefix='/api/a')\n",
    )
    _write(
        tmp_path / "routes" / "embedded.py",
        "from fastapi import APIRouter\nrouter = APIRouter(prefix='/child')\n",
    )
    _write(
        tmp_path / "routes" / "orphan.py",
        "from fastapi import APIRouter\nrouter = APIRouter(prefix='/api/orphan')\n",
    )
    _write(
        tmp_path / "routes" / "helper.py",
        "def helper():\n    return 1\n",
    )
    _write(
        tmp_path / "core" / "routes_registry.py",
        "KNOWN_ROUTES = [('routes.registered', 'router')]\n"
        "KNOWN_ROUTES_WITH_PREFIX = []\n",
    )
    _write(
        tmp_path / "owner.py",
        "from fastapi import APIRouter\n"
        "from routes.embedded import router as child_router\n"
        "router = APIRouter()\n"
        "router.include_router(child_router)\n",
    )

    report = build_route_island_report(backend_root=tmp_path)

    assert report["routers"] == (
        "routes.embedded",
        "routes.orphan",
        "routes.registered",
    )
    assert report["registered"] == ("routes.registered",)
    assert report["embedded"] == ("routes.embedded",)
    assert report["islands"] == ("routes.orphan",)


def test_route_island_audit_understands_module_router_includes(tmp_path: Path):
    _write(
        tmp_path / "routes" / "child.py",
        "from fastapi import APIRouter\nrouter = APIRouter()\n",
    )
    _write(
        tmp_path / "core" / "routes_registry.py",
        "KNOWN_ROUTES = []\nKNOWN_ROUTES_WITH_PREFIX = []\n",
    )
    _write(
        tmp_path / "owner.py",
        "from fastapi import APIRouter\n"
        "import routes.child as child\n"
        "router = APIRouter()\n"
        "router.include_router(child.router)\n",
    )

    report = build_route_island_report(backend_root=tmp_path)
    assert report["embedded"] == ("routes.child",)
    assert report["islands"] == ()


def test_repository_has_no_unintegrated_route_islands():
    report = build_route_island_report()
    assert report["islands"] == (), (
        "FastAPI route modules exist without canonical ownership. Register them in "
        "core.routes_registry, embed them through include_router, or absorb/retire "
        f"the duplicate implementation. Islands: {', '.join(report['islands'])}"
    )
