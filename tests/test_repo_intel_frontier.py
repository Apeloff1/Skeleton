from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_intel_frontier as frontier  # noqa: E402


def test_merge_relationships_deduplicates_and_rebuilds_reverse_graph() -> None:
    snapshot = {
        "graph": {
            "nodes": [{"id": "file:a.py", "type": "file"}],
            "edges": [
                {"from": "file:a.py", "to": "file:b.py", "type": "imports", "precision": "ast"}
            ],
            "reverse_edges": {},
        }
    }
    relationships = {
        "nodes": [
            {"id": "target:make:test", "type": "build-target", "name": "test"},
            {"id": "target:make:test", "type": "build-target", "name": "test"},
        ],
        "edges": [
            {"from": "target:make:test", "to": "file:a.py", "type": "build-uses", "precision": "lexical"},
            {"from": "target:make:test", "to": "file:a.py", "type": "build-uses", "precision": "lexical"},
        ],
    }
    frontier._merge_relationships(snapshot, relationships)
    assert [node["id"] for node in snapshot["graph"]["nodes"]] == ["file:a.py", "target:make:test"]
    assert len(snapshot["graph"]["edges"]) == 2
    assert snapshot["graph"]["reverse_edges"]["file:a.py"] == [
        {"from": "target:make:test", "type": "build-uses", "precision": "lexical"}
    ]
    assert snapshot["graph"]["reverse_edges"]["file:b.py"] == [
        {"from": "file:a.py", "type": "imports", "precision": "ast"}
    ]


def test_impact_payload_adds_external_dependencies_architecture_and_workflows(monkeypatch) -> None:
    snapshot = {
        "graph": {
            "edges": [
                {
                    "from": "file:pyproject.toml",
                    "to": "dependency:pypi:fastapi",
                    "type": "declares-dependency",
                    "precision": "manifest",
                }
            ],
            "architecture_boundary_violations": [
                {
                    "source": "backend/core.py",
                    "target": "frontend/app.tsx",
                    "rule": "backend-no-frontend",
                }
            ],
        }
    }
    monkeypatch.setattr(
        frontier.semantic,
        "_impact_from_paths",
        lambda _snapshot, _changed: {
            "affected_files": ["backend/core.py", "pyproject.toml", ".github/workflows/ci.yml"],
            "affected_file_count": 3,
            "subsystems": ["backend", "github", "root"],
            "candidate_tests": [],
        },
    )
    payload = frontier.impact_payload(snapshot, ["backend/core.py"])
    assert payload["external_dependencies_touched"] == ["dependency:pypi:fastapi"]
    assert payload["architecture_boundary_findings"][0]["rule"] == "backend-no-frontend"
    assert payload["workflow_files_touched"] == [".github/workflows/ci.yml"]


def test_frontier_contract_files_are_present() -> None:
    required = [
        ROOT / "repo-intel" / "deep-index-contract.json",
        ROOT / "scripts" / "repo_intel_deep.py",
        ROOT / "scripts" / "repo_intel_frontier.py",
    ]
    assert all(path.is_file() for path in required)
