from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import repo_intel_artifacts as artifacts  # noqa: E402


def test_compose_build_contexts_parse_explicit_context_dockerfile_and_target() -> None:
    text = """
services:
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
      target: development
    image: ignored
  frontend:
    build:
      context: ./frontend
"""
    rows = artifacts._parse_compose_builds(text)
    assert rows == [
        {"service": "backend", "context": ".", "dockerfile": "backend/Dockerfile", "target": "development"},
        {"service": "frontend", "context": "./frontend", "dockerfile": None, "target": None},
    ]


def test_dockerfile_lineage_resolves_files_directories_and_stage_copies() -> None:
    text = """
FROM python:3.14 AS builder
COPY pyproject.toml README.md ./
COPY skeleton/ ./skeleton/
FROM python:3.14 AS production
COPY --from=builder /opt/venv /opt/venv
"""
    tracked = {"pyproject.toml", "README.md", "skeleton/a.py", "skeleton/b.py"}
    result = artifacts.parse_dockerfile(
        "Dockerfile",
        text,
        [{"service": "app", "context": ".", "dockerfile": "Dockerfile", "target": "production"}],
        tracked,
    )
    assert [stage["stage"] for stage in result["stages"]] == ["builder", "production"]
    selectors = [item.get("resolved", {}) for item in result["copies"] if item.get("source_kind") == "repository-selector"]
    assert {item.get("kind") for item in selectors} == {"file", "directory"}
    directory = next(item for item in selectors if item.get("kind") == "directory")
    assert directory["matched_count"] == 2
    stage_copy = next(item for item in result["copies"] if item.get("source_kind") == "stage")
    assert stage_copy["source_stage"].endswith(":builder")
    assert result["stages"][-1]["final"] is True


def test_dynamic_and_glob_selectors_are_not_fabricated() -> None:
    tracked = {"src/a.py"}
    dynamic = artifacts._resolve_selector(".", "$SOURCE", tracked)
    glob = artifacts._resolve_selector(".", "src/*.py", tracked)
    assert dynamic["kind"] == "dynamic" and dynamic["matched_count"] == 0
    assert glob["kind"] == "glob" and glob["matched_count"] == 0


def test_affected_artifacts_traverses_selector_stage_and_service() -> None:
    lineage = {
        "nodes": [
            {
                "id": "artifact-input-selector:Dockerfile:1:src/",
                "type": "artifact-input-selector",
                "selector": "src/",
            },
            {"id": "artifact:container-stage:Dockerfile:builder", "type": "artifact"},
            {"id": "artifact:container-stage:Dockerfile:production", "type": "artifact"},
            {"id": "artifact:compose-service:app", "type": "artifact", "kind": "compose-service"},
        ],
        "edges": [
            {
                "from": "artifact-input-selector:Dockerfile:1:src/",
                "to": "artifact:container-stage:Dockerfile:builder",
                "type": "artifact-input",
            },
            {
                "from": "artifact:container-stage:Dockerfile:builder",
                "to": "artifact:container-stage:Dockerfile:production",
                "type": "artifact-input",
            },
            {
                "from": "artifact:container-stage:Dockerfile:production",
                "to": "artifact:compose-service:app",
                "type": "packages-artifact",
            },
        ],
    }
    found = artifacts.affected_artifacts({"affected_files": ["src/a.py"]}, lineage)
    assert [item["artifact"] for item in found] == [
        "artifact:container-stage:Dockerfile:builder",
        "artifact:container-stage:Dockerfile:production",
        "artifact:compose-service:app",
    ]


def test_artifact_lineage_contract_is_fail_closed() -> None:
    artifacts.check_contracts()
