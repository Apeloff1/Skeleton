from pathlib import Path

import pytest

from scripts.backend_route_policy_report import build_policy_report, main


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    backend = tmp_path / "backend"
    registry = backend / "core" / "routes_registry.py"
    routes = backend / "routes"
    write(
        registry,
        "KNOWN_ROUTES_WITH_PREFIX = []\n"
        "KNOWN_ROUTES = [('routes.sample', 'router')]\n",
    )
    write(
        routes / "sample.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter(prefix='/api')\n"
        "@router.get('/health')\n"
        "def health(): pass\n"
        "@router.post('/galaxy-studio/build')\n"
        "def build(): pass\n"
        "@router.get('/misc')\n"
        "def misc(): pass\n",
    )
    return registry, routes


def test_policy_report_combines_inventory_and_domain_coverage(tmp_path: Path):
    registry, routes = make_repo(tmp_path)
    report = build_policy_report(registry, routes)

    assert report["inventory"] == {
        "modules_declared": 1,
        "modules_scanned": 1,
        "route_registrations": 3,
        "unique_paths": 3,
        "duplicates": 0,
        "unresolved": 0,
        "complete": True,
        "method_counts": {"GET": 2, "POST": 1},
    }
    assert report["coverage"]["complete"] is True
    assert report["coverage"]["open_routes"] == 1
    assert report["domain_counts"] == {"legacy_api": 1, "studio": 1}
    assert report["legacy_api_paths"] == 1
    assert report["legacy_api_ratio"] == pytest.approx(0.5)
    assert report["enforcement_ready"] is True


def test_cli_can_gate_inventory_cleanliness_independently_from_legacy_migration(tmp_path: Path):
    registry, routes = make_repo(tmp_path)
    assert main(
        [
            "--registry",
            str(registry),
            "--routes-root",
            str(routes),
            "--require-inventory-clean",
        ]
    ) == 0

    assert main(
        [
            "--registry",
            str(registry),
            "--routes-root",
            str(routes),
            "--max-legacy-ratio",
            "0.4",
        ]
    ) == 1


def test_policy_report_refuses_invalid_legacy_ratio_argument(tmp_path: Path):
    registry, routes = make_repo(tmp_path)
    with pytest.raises(SystemExit):
        main(
            [
                "--registry",
                str(registry),
                "--routes-root",
                str(routes),
                "--max-legacy-ratio",
                "1.5",
            ]
        )
