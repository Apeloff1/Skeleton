from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_intel_deep as deep  # noqa: E402


def test_requirement_parser_keeps_name_and_constraint() -> None:
    assert deep._requirement_name("fastapi==0.141.1") == ("fastapi", "==0.141.1")
    assert deep._requirement_name("uvicorn[standard]>=0.52.4 ; python_version >= '3.11'") == (
        "uvicorn",
        ">=0.52.4",
    )
    assert deep._requirement_name("-r other.txt") is None
    assert deep._requirement_name("# comment") is None


def test_expo_route_normalises_groups_index_and_parameters() -> None:
    assert deep._expo_route("frontend/app/index.tsx") == "/"
    assert deep._expo_route("frontend/app/(tabs)/games/[id].tsx") == "/games/:id"
    assert deep._expo_route("frontend/app/docs/[...slug].tsx") == "/docs/*slug"
    assert deep._expo_route("frontend/components/card.tsx") is None


def test_dependency_inventory_reads_python_npm_docker_and_actions(monkeypatch) -> None:
    files = [
        {"path": "requirements.txt"},
        {"path": "frontend/package.json"},
        {"path": "backend/Dockerfile"},
        {"path": ".github/workflows/ci.yml"},
    ]
    texts = {
        "requirements.txt": "fastapi==0.141.1\nuvicorn[standard]>=0.52.4\n",
        "backend/Dockerfile": "FROM python:3.11-slim\n",
        ".github/workflows/ci.yml": "steps:\n  - uses: actions/checkout@v7\n",
    }
    monkeypatch.setattr(deep, "_read_text", lambda path: texts.get(path))
    monkeypatch.setattr(
        deep,
        "_json",
        lambda path: {
            "dependencies": {"react": "19.1.0"},
            "devDependencies": {"typescript": "~5.9.3"},
            "scripts": {"typecheck": "tsc --noEmit"},
        }
        if path == "frontend/package.json"
        else None,
    )
    data = deep.dependency_inventory({"files": files})
    packages = {(item["ecosystem"], item["name"]) for item in data["packages"]}
    assert ("pypi", "fastapi") in packages
    assert ("npm", "react") in packages
    assert ("docker", "python:3.11-slim") in packages
    assert ("github-actions", "actions/checkout") in packages
    assert data["package_scripts"] == [
        {
            "kind": "npm-script",
            "manifest": "frontend/package.json",
            "name": "typecheck",
            "command": "tsc --noEmit",
        }
    ]


def test_surface_inventory_never_emits_environment_values(monkeypatch) -> None:
    files = [
        {"path": "backend/api.py"},
        {"path": "frontend/app/games/[id].tsx"},
        {"path": ".env.example"},
    ]
    texts = {
        "backend/api.py": (
            "@router.get('/api/v1/games/{game_id}')\n"
            "def game():\n"
            "    token = os.getenv('GAME_TOKEN')\n"
            "    return token\n"
        ),
        "frontend/app/games/[id].tsx": "const api = process.env.EXPO_PUBLIC_API_URL;\n",
        ".env.example": "EXPO_PUBLIC_API_URL=https://example.invalid\nGAME_TOKEN=do-not-index-this\n",
    }
    monkeypatch.setattr(deep, "_read_text", lambda path: texts.get(path))
    data = deep.surface_inventory({"files": files})
    assert {item["route"] for item in data["routes"]} == {"/api/v1/games/{game_id}", "/games/:id"}
    env = {item["name"]: item for item in data["environment_variables"]}
    assert set(env) == {"GAME_TOKEN", "EXPO_PUBLIC_API_URL"}
    assert env["GAME_TOKEN"]["documented_in_example"] is True
    encoded = json.dumps(data)
    assert "do-not-index-this" not in encoded
    assert "https://example.invalid" not in encoded


def test_history_parser_is_bounded_and_deterministic() -> None:
    output = "@@200\na.py\nb.py\n\n@@100\na.py\n\n"
    commits, metrics = deep._parse_history(output, {"a.py", "b.py", "c.py"})
    assert commits == 2
    assert metrics["a.py"] == {"touches": 2, "last_changed_epoch": 200}
    assert metrics["b.py"] == {"touches": 1, "last_changed_epoch": 200}
    assert metrics["c.py"] == {"touches": 0, "last_changed_epoch": 0}


def test_build_relationships_connect_workflow_to_referenced_repo_files(monkeypatch) -> None:
    snapshot = {
        "files": [
            {
                "path": ".github/workflows/ci.yml",
                "flags": {"workflow": True},
            },
            {"path": "scripts/check.py", "flags": {"workflow": False}},
            {"path": "Makefile", "flags": {"workflow": False}},
        ]
    }
    texts = {
        ".github/workflows/ci.yml": "run: python scripts/check.py\n",
        "Makefile": "check:\n\tpython scripts/check.py\n",
    }
    monkeypatch.setattr(deep, "_read_text", lambda path: texts.get(path))
    data = deep.build_relationships(snapshot, {"packages": []})
    edge_keys = {(item["from"], item["to"], item["type"]) for item in data["edges"]}
    assert (
        "file:.github/workflows/ci.yml",
        "file:scripts/check.py",
        "workflow-uses",
    ) in edge_keys
    assert ("target:make:check", "file:scripts/check.py", "build-uses") in edge_keys


def test_batch_status_reports_evidence_presence_without_claiming_completion(monkeypatch) -> None:
    batches = {
        "batches": [
            {"id": "B001", "lane": "build", "depends_on": []},
            {"id": "B002", "lane": "build", "depends_on": ["B001"]},
        ]
    }
    monkeypatch.setattr(deep.base, "load_json", lambda name: batches if name == "batches.json" else {})
    monkeypatch.setattr(deep, "_read_text", lambda path: "B001 evidence" if path.endswith("note.md") else None)
    data = deep.batch_status({"files": [{"path": "repo-intel/notes/note.md"}]})
    by_id = {item["id"]: item for item in data["batches"]}
    assert by_id["B001"]["index_state"] == "evidence-noted"
    assert by_id["B002"]["index_state"] == "planned"
    assert by_id["B002"]["dependency_notes_present"] == ["B001"]
    assert "does not mean complete" in data["semantics"]


def test_search_ranks_path_and_symbol_hits() -> None:
    catalog = {
        "documents": [
            {
                "path": "backend/gameforge/engine.py",
                "subsystem": "gameforge",
                "symbols": ["GameEngine.build"],
                "imports": [],
                "routes": [],
                "environment_variables": [],
                "declared_packages": [],
                "hotspot_score": 30.0,
            },
            {
                "path": "docs/engine.md",
                "subsystem": "docs",
                "symbols": [],
                "imports": [],
                "routes": [],
                "environment_variables": [],
                "declared_packages": [],
                "hotspot_score": 0.0,
            },
        ]
    }
    results = deep.search(catalog, "GameEngine", limit=10)
    assert results[0]["path"] == "backend/gameforge/engine.py"
    assert results[0]["score"] > 0


def test_deep_index_contract_is_machine_valid() -> None:
    payload = json.loads((ROOT / "repo-intel" / "deep-index-contract.json").read_text(encoding="utf-8"))
    assert payload["history_window_commits"] == deep.HISTORY_COMMITS
    assert "dependencies.json" in payload["generated_outputs"]
    assert payload["surface_semantics"]["environment"].startswith("Only variable names")
