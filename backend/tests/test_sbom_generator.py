from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_sbom import build_sbom, frontend_components, python_components


def test_python_components_capture_exact_and_range_constraints(tmp_path: Path) -> None:
    manifest = tmp_path / "requirements.txt"
    manifest.write_text("fastapi==1.2.3\ncryptography>=46,<47\n", encoding="utf-8")

    components = python_components(manifest)

    exact = next(item for item in components if item["name"] == "fastapi")
    ranged = next(item for item in components if item["name"] == "cryptography")
    assert exact["version"] == "1.2.3"
    assert exact["purl"] == "pkg:pypi/fastapi@1.2.3"
    assert "version" not in ranged
    assert any(prop["value"] == ">=46,<47" for prop in ranged["properties"])


def test_frontend_components_capture_runtime_and_dev_scope(tmp_path: Path) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps({"dependencies": {"react": "19.1.0"}, "devDependencies": {"typescript": "~5.9.3"}}),
        encoding="utf-8",
    )

    components = frontend_components(package)

    react = next(item for item in components if item["name"] == "react")
    typescript = next(item for item in components if item["name"] == "typescript")
    assert any(prop == {"name": "skeleton:dependency-scope", "value": "runtime"} for prop in react["properties"])
    assert any(prop == {"name": "skeleton:dependency-scope", "value": "dev"} for prop in typescript["properties"])


def test_sbom_is_deterministic_for_same_repository_state(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    first = build_sbom()
    second = build_sbom()

    assert first == second
    assert first["bomFormat"] == "CycloneDX"
    assert first["specVersion"] == "1.6"
    assert first["serialNumber"].startswith("urn:uuid:")
    assert first["components"]


def test_sbom_records_source_commit_when_available(monkeypatch) -> None:
    commit = "a" * 40
    monkeypatch.setenv("GITHUB_SHA", commit)

    payload = build_sbom()

    assert {"name": "skeleton:source-commit", "value": commit} in payload["metadata"]["properties"]


def test_sbom_records_manifest_hashes() -> None:
    payload = build_sbom()
    names = {prop["name"] for prop in payload["metadata"]["properties"]}

    assert "skeleton:manifest-sha256:backend/requirements.txt" in names
    assert "skeleton:manifest-sha256:frontend/package.json" in names
