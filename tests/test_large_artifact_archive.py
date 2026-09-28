"""Regression tests for current-tree large-artifact archival."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_large_artifact_archive.py"
SPEC = importlib.util.spec_from_file_location("check_large_artifact_archive", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def _entry(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "path": "archive/large.bin",
        "blob_sha": "a" * 40,
        "size": checker.THRESHOLD_BYTES + 1,
        "classification": "branch-snapshot-archival-binary",
        "required_for_build": False,
        "recovery": "git-history",
        "replacement_reference": None,
    }
    value.update(overrides)
    return value


def _payload(*entries: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "baseline_git_sha": "b" * 40,
        "threshold_bytes": checker.THRESHOLD_BYTES,
        "policy": "docs/ARTIFACT_POLICY.md",
        "recovery": "recover from the pinned baseline commit using the recorded path",
        "entries": list(entries),
    }


def test_repository_archive_map_removes_all_current_oversized_blobs() -> None:
    entries = checker.validate_repository(root=ROOT)
    assert len(entries) == 10
    assert sum(entry["size"] for entry in entries) == 457_547_336
    assert checker.current_oversized_blobs(ROOT) == ()


def test_manifest_records_three_unique_historical_blob_objects() -> None:
    payload = checker.load_manifest()
    entries = checker.validate_payload(payload, root=ROOT)
    assert {entry["blob_sha"] for entry in entries} == {
        "0462da7140794edeaecc6f7582aa93048d37bc7b",
        "01ca1a298c794bd5ab677cbe439c39763768ded3",
        "70b3ac3f344aaf55dc55686690acd141c0e1979f",
    }


@pytest.mark.parametrize(
    "entry",
    [
        _entry(path="../escape.bin"),
        _entry(blob_sha="ABC"),
        _entry(size=checker.THRESHOLD_BYTES),
        _entry(required_for_build=True),
        _entry(classification="live-runtime"),
        _entry(recovery="network"),
    ],
)
def test_malformed_or_live_archive_entries_fail_closed(
    tmp_path: Path,
    entry: dict[str, object],
) -> None:
    with pytest.raises(checker.LargeArtifactArchiveError):
        checker.validate_payload(_payload(entry), root=tmp_path)


def test_duplicate_paths_fail_closed(tmp_path: Path) -> None:
    entry = _entry()
    with pytest.raises(checker.LargeArtifactArchiveError, match="duplicate"):
        checker.validate_payload(_payload(entry, dict(entry)), root=tmp_path)


def test_existing_archived_payload_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "archive" / "large.bin"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x")
    with pytest.raises(checker.LargeArtifactArchiveError, match="restored"):
        checker.validate_payload(_payload(_entry()), root=tmp_path)


def test_missing_replacement_reference_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(checker.LargeArtifactArchiveError, match="replacement reference"):
        checker.validate_payload(
            _payload(_entry(replacement_reference="missing.json")),
            root=tmp_path,
        )


def test_manifest_is_strict_json_object(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_payload(_entry())), encoding="utf-8")
    loaded = checker.load_manifest(path)
    assert loaded["schema_version"] == 1
