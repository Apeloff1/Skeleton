from pathlib import Path

import pytest

from scripts.backend_route_policy_debt import build_debt_report, main


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
        "@router.get('/galaxy-studio/build')\n"
        "def studio(): pass\n"
        "@router.get('/legacy-a/one')\n"
        "def a1(): pass\n"
        "@router.post('/legacy-a/two')\n"
        "def a2(): pass\n"
        "@router.get('/legacy-b/one')\n"
        "def b1(): pass\n"
        "@router.post('/legacy-b/one')\n"
        "def b1post(): pass\n",
    )
    return registry, routes


def test_debt_report_counts_unique_paths_and_ranks_prefixes(tmp_path: Path):
    registry, routes = make_repo(tmp_path)
    report = build_debt_report(registry, routes, depth=2)

    assert report["legacy_path_count"] == 3
    assert report["group_count"] == 2
    assert report["groups"] == [
        {"prefix": "/api/legacy-a", "paths": 2},
        {"prefix": "/api/legacy-b", "paths": 1},
    ]


def test_debt_report_supports_deeper_prefix_grouping(tmp_path: Path):
    registry, routes = make_repo(tmp_path)
    report = build_debt_report(registry, routes, depth=3)
    assert report["groups"] == [
        {"prefix": "/api/legacy-a/one", "paths": 1},
        {"prefix": "/api/legacy-a/two", "paths": 1},
        {"prefix": "/api/legacy-b/one", "paths": 1},
    ]


def test_invalid_depth_fails_closed(tmp_path: Path):
    registry, routes = make_repo(tmp_path)
    with pytest.raises(ValueError, match="depth"):
        build_debt_report(registry, routes, depth=0)
    with pytest.raises(SystemExit):
        main(
            [
                "--registry",
                str(registry),
                "--routes-root",
                str(routes),
                "--depth",
                "7",
            ]
        )


def test_cli_prints_ranked_legacy_groups(tmp_path: Path, capsys):
    registry, routes = make_repo(tmp_path)
    assert main(
        [
            "--registry",
            str(registry),
            "--routes-root",
            str(routes),
            "--top",
            "1",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "paths=3 groups=2" in output
    assert "LEGACY    2 /api/legacy-a" in output
    assert "/api/legacy-b" not in output
