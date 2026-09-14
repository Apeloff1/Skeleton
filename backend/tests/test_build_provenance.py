from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_build_provenance import build_provenance, sha256_file


def test_sha256_file_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"skeleton-security")
    assert sha256_file(path) == sha256_file(path)
    assert len(sha256_file(path)) == 64


def test_provenance_records_source_commit_and_repository(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    monkeypatch.setenv("GITHUB_REPOSITORY", "Apeloff1/Skeleton")
    monkeypatch.setenv("GITHUB_RUN_ID", "123456")

    payload = build_provenance()

    assert payload["schema"] == "skeleton.build-provenance/v1"
    assert payload["repository"] == "Apeloff1/Skeleton"
    assert payload["source"]["commit"] == "b" * 40
    assert payload["builder"]["run_id"] == "123456"


def test_provenance_materials_are_sorted_and_hashed() -> None:
    payload = build_provenance()
    paths = [material["path"] for material in payload["materials"]]

    assert paths == sorted(paths)
    assert "backend/requirements.txt" in paths
    assert "frontend/package.json" in paths
    assert ".github/workflows/backend-quality.yml" in paths
    for material in payload["materials"]:
        assert len(material["sha256"]) == 64


def test_provenance_is_json_serializable_and_deterministic(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    first = build_provenance()
    second = build_provenance()

    assert first == second
    json.dumps(first, sort_keys=True)
