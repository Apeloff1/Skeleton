"""Regression coverage for archived dependency-surface quarantine."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_archived_dependency_surface.py"
SPEC = importlib.util.spec_from_file_location("check_archived_dependency_surface", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_detects_common_installable_manifests(tmp_path: Path) -> None:
    archive = tmp_path / "snapshots"
    bad = [
        archive / "a" / "frontend" / "package.json",
        archive / "a" / "frontend" / "yarn.lock",
        archive / "b" / "backend" / "pyproject.toml",
        archive / "b" / "requirements-dev.txt",
        archive / "c" / "Cargo.lock",
        archive / "d" / "build.gradle.kts",
    ]
    for path in bad:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("historical evidence\n", encoding="utf-8")

    findings = MODULE.find_installable_manifests(archive)
    assert [item.relative_to(archive).as_posix() for item in findings] == [
        "a/frontend/package.json",
        "a/frontend/yarn.lock",
        "b/backend/pyproject.toml",
        "b/requirements-dev.txt",
        "c/Cargo.lock",
        "d/build.gradle.kts",
    ]


def test_snapshot_evidence_names_are_not_dependency_surfaces(tmp_path: Path) -> None:
    archive = tmp_path / "snapshots"
    safe = [
        archive / "frontend" / "package.snapshot.json",
        archive / "frontend" / "yarn.snapshot.lock",
        archive / "backend" / "pyproject.snapshot.toml",
        archive / "backend" / "requirements.snapshot",
        archive / "setup.snapshot.cfg",
        archive / "README.md",
    ]
    for path in safe:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("historical evidence\n", encoding="utf-8")

    assert MODULE.find_installable_manifests(archive) == []


def test_missing_archive_root_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    try:
        MODULE.find_installable_manifests(missing)
    except FileNotFoundError as exc:
        assert "archival snapshot root is missing" in str(exc)
    else:
        raise AssertionError("missing archive root must fail closed")


def test_requirements_name_matching_is_bounded() -> None:
    assert MODULE.is_installable_manifest_name("requirements.txt")
    assert MODULE.is_installable_manifest_name("requirements-dev.txt")
    assert MODULE.is_installable_manifest_name("requirements.frontier.txt")
    assert not MODULE.is_installable_manifest_name("requirements.snapshot")
    assert not MODULE.is_installable_manifest_name("requirements-notes.md")


def _write_map(tmp_path: Path, *, archive_name: str = "package.snapshot.json", size: int = 4) -> Path:
    archive_path = (
        tmp_path
        / "satellites"
        / "branch-snapshots"
        / "sample"
        / "vendor"
        / "dependency-manifests"
        / archive_name
    )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(b"data")
    map_path = tmp_path / "satellites" / "branch-snapshots" / "DEPENDENCY_ARCHIVE_MAP.json"
    payload = {
        "schema_version": 1,
        "entries": [
            {
                "source_path": "satellites/branch-snapshots/sample/package.json",
                "archive_path": (
                    "satellites/branch-snapshots/sample/vendor/"
                    f"dependency-manifests/{archive_name}"
                ),
                "blob_sha": "a" * 40,
                "size": size,
            }
        ],
    }
    map_path.write_text(json.dumps(payload), encoding="utf-8")
    return map_path


def test_archive_map_accepts_quarantined_evidence(tmp_path: Path) -> None:
    map_path = _write_map(tmp_path)
    assert MODULE.validate_archive_map(map_path, repo_root=tmp_path) == []


def test_archive_map_rejects_installable_archive_name(tmp_path: Path) -> None:
    map_path = _write_map(tmp_path, archive_name="package.json")
    errors = MODULE.validate_archive_map(map_path, repo_root=tmp_path)
    assert any("archive_path still has an installable manifest name" in error for error in errors)


def test_archive_map_rejects_size_drift(tmp_path: Path) -> None:
    map_path = _write_map(tmp_path, size=999)
    errors = MODULE.validate_archive_map(map_path, repo_root=tmp_path)
    assert any("archive size mismatch" in error for error in errors)


def test_archive_map_rejects_restored_source_manifest(tmp_path: Path) -> None:
    map_path = _write_map(tmp_path)
    source = tmp_path / "satellites" / "branch-snapshots" / "sample" / "package.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("{}", encoding="utf-8")
    errors = MODULE.validate_archive_map(map_path, repo_root=tmp_path)
    assert any("source_path still exists" in error for error in errors)


def test_repository_archive_map_matches_working_tree() -> None:
    map_path = REPO_ROOT / "satellites" / "branch-snapshots" / "DEPENDENCY_ARCHIVE_MAP.json"
    assert MODULE.validate_archive_map(map_path, repo_root=REPO_ROOT) == []


def test_broken_symlink_manifest_name_is_still_detected(tmp_path: Path) -> None:
    archive = tmp_path / "snapshots"
    archive.mkdir()
    link = archive / "package.json"
    link.symlink_to(tmp_path / "missing-target")
    findings = MODULE.find_installable_manifests(archive)
    assert findings == [link]


def test_archive_map_rejects_symlinked_evidence(tmp_path: Path) -> None:
    map_path = _write_map(tmp_path)
    payload = json.loads(map_path.read_text(encoding="utf-8"))
    archive_path = tmp_path / payload["entries"][0]["archive_path"]
    archive_path.unlink()
    target = tmp_path / "evidence-bytes"
    target.write_bytes(b"data")
    archive_path.symlink_to(target)
    errors = MODULE.validate_archive_map(map_path, repo_root=tmp_path)
    assert any("archive_path must not be a symlink" in error for error in errors)


def test_archive_map_rejects_unmapped_vendor_evidence(tmp_path: Path) -> None:
    map_path = _write_map(tmp_path)
    extra = (
        tmp_path
        / "satellites"
        / "branch-snapshots"
        / "sample"
        / "vendor"
        / "dependency-manifests"
        / "extra.snapshot.lock"
    )
    extra.write_text("extra", encoding="utf-8")
    errors = MODULE.validate_archive_map(map_path, repo_root=tmp_path)
    assert any("unmapped quarantined dependency evidence" in error for error in errors)
