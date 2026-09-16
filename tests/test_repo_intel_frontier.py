from __future__ import annotations

import json
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


def test_merge_relationships_preserves_metadata_variants() -> None:
    runtime = {
        "from": "file:pyproject.toml",
        "to": "dependency:pypi:fastapi",
        "type": "declares-dependency",
        "precision": "manifest",
        "scope": "runtime",
        "spec": ">=0.141",
    }
    dev = {**runtime, "scope": "development", "spec": ">=0.140"}
    snapshot = {
        "graph": {
            "nodes": [],
            "edges": [runtime, dev, dict(runtime)],
            "reverse_edges": {},
        }
    }
    frontier._merge_relationships(snapshot, {"nodes": [], "edges": []})
    assert len(snapshot["graph"]["edges"]) == 2
    incoming = snapshot["graph"]["reverse_edges"]["dependency:pypi:fastapi"]
    assert {item["scope"] for item in incoming} == {"runtime", "development"}
    assert {item["spec"] for item in incoming} == {">=0.141", ">=0.140"}
    assert frontier._relationship_variant_count(snapshot["graph"]["edges"]) == 1


def test_snapshot_freshness_requires_fingerprint_and_companion_outputs(tmp_path, monkeypatch) -> None:
    current = {"schema": 5, "workspace_fingerprint": "same"}
    monkeypatch.setattr(frontier, "_workspace_fingerprint", lambda: "same")
    assert not frontier._snapshot_is_fresh(current, tmp_path)

    for name in frontier.REQUIRED_SNAPSHOT_OUTPUTS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    assert frontier._snapshot_is_fresh(current, tmp_path)

    monkeypatch.setattr(frontier, "_workspace_fingerprint", lambda: "changed")
    assert not frontier._snapshot_is_fresh(current, tmp_path)


def test_load_or_build_regenerates_stale_schema5_snapshot(tmp_path, monkeypatch) -> None:
    for name in frontier.REQUIRED_SNAPSHOT_OUTPUTS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    (tmp_path / "index.json").write_text(
        json.dumps({"schema": 5, "workspace_fingerprint": "old"}), encoding="utf-8"
    )
    monkeypatch.setattr(frontier, "_workspace_fingerprint", lambda: "new")
    rebuilt = {"schema": 5, "workspace_fingerprint": "new", "marker": "rebuilt"}
    calls: list[tuple[Path, str]] = []

    def fake_snapshot(out: Path, base_ref: str) -> dict:
        calls.append((out, base_ref))
        return rebuilt

    monkeypatch.setattr(frontier, "snapshot_command", fake_snapshot)
    assert frontier.load_or_build(tmp_path, "base-sha") == rebuilt
    assert calls == [(tmp_path, "base-sha")]


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
