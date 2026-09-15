from pathlib import Path

import pytest

from scripts.backend_route_inventory import (
    build_inventory,
    load_registered_modules,
    main,
    module_file,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def registry(tmp_path: Path, *, known: str, prefixed: str = "[]") -> Path:
    path = tmp_path / "core" / "routes_registry.py"
    write(
        path,
        "from typing import List\n"
        f"KNOWN_ROUTES = {known}\n"
        f"KNOWN_ROUTES_WITH_PREFIX = {prefixed}\n",
    )
    return path


def test_inventory_combines_mount_router_and_endpoint_paths(tmp_path: Path):
    registry_path = registry(
        tmp_path,
        known='[("routes.studio", "router")]',
        prefixed='[("routes.health", "router", "/api")]',
    )
    routes_root = tmp_path / "routes"
    write(
        routes_root / "health.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/health')\n"
        "@router.get('')\n"
        "def health(): pass\n"
        "@router.api_route('/probe', methods=['GET', 'HEAD'])\n"
        "def probe(): pass\n",
    )
    write(
        routes_root / "studio.py",
        "from fastapi import APIRouter\n"
        "PREFIX = '/api/studio'\n"
        "ITEMS = '/items'\n"
        "router = APIRouter(prefix=PREFIX)\n"
        "@router.post(ITEMS)\n"
        "def create(): pass\n"
        "@router.websocket('/live')\n"
        "async def live(): pass\n",
    )

    report = build_inventory(registry_path, routes_root)

    assert report.modules_declared == 2
    assert report.modules_scanned == 2
    assert report.unresolved_count == 0
    assert report.route_count == 5
    assert report.unique_path_count == 4
    assert {(row.method, row.path) for row in report.routes} == {
        ("GET", "/api/health"),
        ("GET", "/api/health/probe"),
        ("HEAD", "/api/health/probe"),
        ("POST", "/api/studio/items"),
        ("WEBSOCKET", "/api/studio/live"),
    }


def test_inventory_handles_imperative_add_api_route_and_literal_concatenation(tmp_path: Path):
    registry_path = registry(tmp_path, known='[("routes.ops", "router")]')
    routes_root = tmp_path / "routes"
    write(
        routes_root / "ops.py",
        "from fastapi import APIRouter\n"
        "ROOT = '/api'\n"
        "AREA = '/ops'\n"
        "PATH = '/restart'\n"
        "router = APIRouter(prefix=ROOT + AREA)\n"
        "def restart(): pass\n"
        "router.add_api_route(PATH, restart, methods=['POST'])\n",
    )

    report = build_inventory(registry_path, routes_root)

    assert report.complete is True
    assert [(row.method, row.path) for row in report.routes] == [
        ("POST", "/api/ops/restart")
    ]


def test_inventory_resolves_child_router_factory_composition_without_false_root_paths(tmp_path: Path):
    registry_path = registry(tmp_path, known='[("routes.constructs", "router")]')
    routes_root = tmp_path / "routes"
    write(
        routes_root / "constructs.py",
        "from fastapi import APIRouter\n"
        "construct_router = APIRouter(prefix='/api/constructs')\n"
        "material_router = APIRouter(prefix='/api/materials')\n"
        "def _make_router(router, kind):\n"
        "    @router.get('/capacity')\n"
        "    def capacity(): return kind\n"
        "    @router.post('/generate')\n"
        "    def generate(): return kind\n"
        "_make_router(construct_router, 'construct')\n"
        "_make_router(material_router, 'material')\n"
        "@construct_router.post('/compose')\n"
        "def compose(): pass\n"
        "router = APIRouter()\n"
        "router.include_router(construct_router)\n"
        "router.include_router(material_router)\n",
    )

    report = build_inventory(registry_path, routes_root)

    assert report.complete is True
    assert report.duplicate_route_count == 0
    assert {(row.method, row.path) for row in report.routes} == {
        ("GET", "/api/constructs/capacity"),
        ("POST", "/api/constructs/generate"),
        ("POST", "/api/constructs/compose"),
        ("GET", "/api/materials/capacity"),
        ("POST", "/api/materials/generate"),
    }
    assert not any(row.path == "/capacity" for row in report.routes)


def test_inventory_recursively_follows_directly_imported_child_routers(tmp_path: Path):
    registry_path = registry(tmp_path, known='[("routes.parent", "router")]')
    routes_root = tmp_path / "routes"
    write(
        routes_root / "leaf.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/leaf')\n"
        "@router.get('/ready')\n"
        "def ready(): pass\n",
    )
    write(
        routes_root / "child.py",
        "from fastapi import APIRouter\n"
        "from routes.leaf import router as leaf_router\n"
        "router = APIRouter(prefix='/child')\n"
        "@router.post('/run')\n"
        "def run(): pass\n"
        "router.include_router(leaf_router, prefix='/nested')\n",
    )
    write(
        routes_root / "parent.py",
        "from fastapi import APIRouter\n"
        "from routes.child import router as child_router\n"
        "router = APIRouter(prefix='/api/parent')\n"
        "@router.get('/status')\n"
        "def status(): pass\n"
        "router.include_router(child_router, prefix='/mounted')\n",
    )

    report = build_inventory(registry_path, routes_root)

    assert report.complete is True
    assert report.duplicate_route_count == 0
    assert {(row.method, row.path) for row in report.routes} == {
        ("GET", "/api/parent/status"),
        ("POST", "/api/parent/mounted/child/run"),
        ("GET", "/api/parent/mounted/child/nested/leaf/ready"),
    }


def test_inventory_reports_import_cycles_instead_of_recursing_forever(tmp_path: Path):
    registry_path = registry(tmp_path, known='[("routes.a", "router")]')
    routes_root = tmp_path / "routes"
    write(
        routes_root / "a.py",
        "from fastapi import APIRouter\n"
        "from routes.b import router as b_router\n"
        "router = APIRouter(prefix='/api/a')\n"
        "router.include_router(b_router)\n",
    )
    write(
        routes_root / "b.py",
        "from fastapi import APIRouter\n"
        "from routes.a import router as a_router\n"
        "router = APIRouter(prefix='/b')\n"
        "router.include_router(a_router)\n",
    )

    report = build_inventory(registry_path, routes_root)

    assert report.complete is False
    assert any("router include cycle" in row.reason for row in report.unresolved)


def test_inventory_preserves_dynamic_paths_as_explicit_unresolved_evidence(tmp_path: Path):
    registry_path = registry(tmp_path, known='[("routes.dynamic", "router")]')
    routes_root = tmp_path / "routes"
    write(
        routes_root / "dynamic.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/dynamic')\n"
        "def choose_path(): return '/runtime'\n"
        "@router.get(choose_path())\n"
        "def endpoint(): pass\n",
    )

    report = build_inventory(registry_path, routes_root)

    assert report.route_count == 0
    assert report.complete is False
    assert report.unresolved_count == 1
    assert report.unresolved[0].module == "routes.dynamic"
    assert "dynamic decorator path" in report.unresolved[0].reason


def test_inventory_reports_missing_module_and_unresolved_router_prefix(tmp_path: Path):
    registry_path = registry(
        tmp_path,
        known='[("routes.missing", "router"), ("routes.bad_prefix", "router")]',
    )
    routes_root = tmp_path / "routes"
    write(
        routes_root / "bad_prefix.py",
        "from fastapi import APIRouter\n"
        "def prefix(): return '/api/bad'\n"
        "router = APIRouter(prefix=prefix())\n",
    )

    report = build_inventory(registry_path, routes_root)

    assert report.modules_declared == 2
    assert report.modules_scanned == 1
    reasons = {row.module: row.reason for row in report.unresolved}
    assert "module file missing" in reasons["routes.missing"]
    assert any(
        row.module == "routes.bad_prefix" and "dynamic prefix" in row.reason
        for row in report.unresolved
    )


def test_duplicate_method_path_pairs_are_counted_without_hiding_sources(tmp_path: Path):
    registry_path = registry(tmp_path, known='[("routes.dupe", "router")]')
    routes_root = tmp_path / "routes"
    write(
        routes_root / "dupe.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/dupe')\n"
        "@router.get('/same')\n"
        "def first(): pass\n"
        "@router.get('/same')\n"
        "def second(): pass\n",
    )

    report = build_inventory(registry_path, routes_root)

    assert report.route_count == 2
    assert report.unique_path_count == 1
    assert report.duplicate_route_count == 1
    assert [row.source_line for row in report.routes] == [3, 5]


def test_registry_loader_rejects_nonliteral_or_malformed_declarations(tmp_path: Path):
    nonliteral = tmp_path / "nonliteral.py"
    write(
        nonliteral,
        "KNOWN_ROUTES_WITH_PREFIX = []\n"
        "def make(): return [('routes.x', 'router')]\n"
        "KNOWN_ROUTES = make()\n",
    )
    with pytest.raises(ValueError, match="not literal"):
        load_registered_modules(nonliteral)

    malformed = tmp_path / "malformed.py"
    write(
        malformed,
        "KNOWN_ROUTES_WITH_PREFIX = []\n"
        "KNOWN_ROUTES = [('routes.x',)]\n",
    )
    with pytest.raises(ValueError, match="2- or 3-tuple"):
        load_registered_modules(malformed)


def test_module_file_rejects_non_routes_namespace(tmp_path: Path):
    with pytest.raises(ValueError, match="unsupported registered module namespace"):
        module_file(tmp_path, "core.secret")


def test_strict_cli_fails_when_inventory_is_incomplete(tmp_path: Path, capsys):
    registry_path = registry(tmp_path, known='[("routes.missing", "router")]')
    exit_code = main(
        [
            "--registry",
            str(registry_path),
            "--routes-root",
            str(tmp_path / "routes"),
            "--strict",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "unresolved=1" in output
    assert "UNRESOLVED routes.missing" in output


def test_fail_on_duplicates_is_an_independent_enforcement_gate(tmp_path: Path):
    registry_path = registry(tmp_path, known='[("routes.dupe", "router")]')
    routes_root = tmp_path / "routes"
    write(
        routes_root / "dupe.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/dupe')\n"
        "@router.get('/same')\n"
        "def first(): pass\n"
        "@router.get('/same')\n"
        "def second(): pass\n",
    )
    assert main(
        [
            "--registry",
            str(registry_path),
            "--routes-root",
            str(routes_root),
            "--fail-on-duplicates",
        ]
    ) == 1


def test_json_cli_exposes_stable_machine_readable_inventory(tmp_path: Path, capsys):
    registry_path = registry(tmp_path, known='[("routes.health", "router")]')
    routes_root = tmp_path / "routes"
    write(
        routes_root / "health.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api/health')\n"
        "@router.get('/ready')\n"
        "def ready(): pass\n",
    )

    assert main(
        [
            "--registry",
            str(registry_path),
            "--routes-root",
            str(routes_root),
            "--json",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert '"complete": true' in output
    assert '"path": "/api/health/ready"' in output
