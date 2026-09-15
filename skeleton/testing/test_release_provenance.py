from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release_provenance.py"
SPEC = importlib.util.spec_from_file_location("release_provenance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
release_provenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_provenance)

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def test_emit_provenance_is_deterministic_and_hashes_release_inputs(tmp_path: Path) -> None:
    artifacts = tmp_path / "dist"
    artifacts.mkdir()
    wheel = artifacts / "skeleton-16.0.0-py3-none-any.whl"
    wheel.write_bytes(b"deterministic-wheel")
    sbom = artifacts / "release-sbom.cdx.json"
    sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    build_lock = tmp_path / "requirements-build.txt"
    build_lock.write_text("build==1.3.0\n", encoding="utf-8")

    first = tmp_path / "first.json"
    first_sums = tmp_path / "first.sha256"
    args = argparse.Namespace(
        artifacts_dir=str(artifacts),
        output=str(first),
        checksums=str(first_sums),
        source_commit=COMMIT,
        source_date_epoch="1700000000",
        input=[str(build_lock)],
        sbom_ref=[str(sbom)],
    )
    assert release_provenance.emit_provenance(args) == 0

    second = tmp_path / "second.json"
    second_sums = tmp_path / "second.sha256"
    args.output = str(second)
    args.checksums = str(second_sums)
    assert release_provenance.emit_provenance(args) == 0

    assert first.read_bytes() == second.read_bytes()
    assert first_sums.read_bytes() == second_sums.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["source"] == {"commit": COMMIT, "source_date_epoch": 1700000000}
    assert [item["name"] for item in payload["artifacts"]] == [
        "release-sbom.cdx.json",
        "skeleton-16.0.0-py3-none-any.whl",
    ]
    assert payload["inputs"][0]["sha256"] == release_provenance._sha256(build_lock)
    assert payload["sbom_refs"][0]["name"] == "release-sbom.cdx.json"


def test_compare_provenance_fails_when_artifact_digest_changes(tmp_path: Path) -> None:
    base = {
        "source": {"commit": COMMIT, "source_date_epoch": 1},
        "toolchain": {"python": "3.11.11"},
        "inputs": [],
        "sbom_refs": [],
        "artifacts": [{"name": "x.whl", "sha256": "a", "size": 1}],
    }
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(base), encoding="utf-8")
    changed = dict(base)
    changed["artifacts"] = [{"name": "x.whl", "sha256": "b", "size": 1}]
    right.write_text(json.dumps(changed), encoding="utf-8")

    args = argparse.Namespace(left=str(left), right=str(right))
    assert release_provenance.compare_provenance(args) == 1


def test_sbom_is_deterministic_and_tracks_declared_runtime_requirements(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "example"
version = "1.2.3"
dependencies = ["uvicorn[standard]>=0.23.0", "fastapi>=0.100.0"]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    output = tmp_path / "sbom.json"
    args = argparse.Namespace(pyproject=str(pyproject), output=str(output), source_commit=COMMIT)

    assert release_provenance.write_sbom(args) == 0
    first = output.read_bytes()
    assert release_provenance.write_sbom(args) == 0
    assert output.read_bytes() == first

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["bomFormat"] == "CycloneDX"
    assert payload["specVersion"] == "1.6"
    assert [component["name"] for component in payload["components"]] == ["fastapi", "uvicorn"]


def test_invalid_source_identity_fails_closed() -> None:
    with pytest.raises(ValueError):
        release_provenance._validate_commit("main")
    with pytest.raises(ValueError):
        release_provenance._validate_epoch("-1")
