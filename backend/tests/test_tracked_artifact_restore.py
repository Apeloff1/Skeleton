"""Regression tests for verified fetch-on-demand tracked artifacts (#807 B006)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore_tracked_artifact.py"
SPEC = importlib.util.spec_from_file_location("restore_tracked_artifact", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
restore = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(restore)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, Path, str, str, bytes]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Artifact Test")

    payload = b"verified artifact payload\n"
    target = repo / "deep" / "nested" / "artifact.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed artifact")
    source_commit = _git(repo, "rev-parse", "HEAD")
    blob_oid = _git(repo, "rev-parse", "HEAD:deep/nested/artifact.bin")

    target.unlink()
    manifest = target.with_name(target.name + ".artifact.json")
    manifest.write_text(
        json.dumps(
            {
                "schema": 1,
                "path": "deep/nested/artifact.bin",
                "source_commit": source_commit,
                "blob_oid": blob_oid,
                "size_bytes": len(payload),
                "kind": "test-fixture",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return repo, manifest, source_commit, blob_oid, payload


def test_restore_round_trip_verifies_git_oid_and_size(tmp_path: Path) -> None:
    repo, manifest, _commit, blob_oid, payload = _repo(tmp_path)

    restored = restore.restore_artifact(manifest)

    assert restored == repo / "deep" / "nested" / "artifact.bin"
    assert restored.read_bytes() == payload
    assert _git(repo, "hash-object", str(restored)) == blob_oid


def test_deep_manifest_discovers_repository_root(tmp_path: Path) -> None:
    repo, manifest, _commit, _oid, _payload = _repo(tmp_path)

    assert restore._discover_repo_root(manifest) == repo


def test_existing_destination_requires_explicit_overwrite(tmp_path: Path) -> None:
    repo, manifest, _commit, _oid, payload = _repo(tmp_path)
    destination = repo / "deep" / "nested" / "artifact.bin"
    destination.write_bytes(b"local modification")

    with pytest.raises(restore.ArtifactRestoreError, match="already exists"):
        restore.restore_artifact(manifest)

    restored = restore.restore_artifact(manifest, overwrite=True)
    assert restored.read_bytes() == payload


@pytest.mark.parametrize(
    "path",
    [
        "../escape.bin",
        "/absolute.bin",
        "deep/../escape.bin",
        "deep\\escape.bin",
        "deep/artifact.bin\nother",
    ],
)
def test_manifest_path_must_be_repository_relative_and_normalized(path: str) -> None:
    with pytest.raises(restore.ArtifactRestoreError):
        restore.validate_manifest(
            {
                "schema": 1,
                "path": path,
                "source_commit": "a" * 40,
                "blob_oid": "b" * 40,
                "size_bytes": 1,
                "kind": "fixture",
            }
        )


def test_manifest_rejects_wrong_oid_and_size_shapes() -> None:
    base = {
        "schema": 1,
        "path": "artifact.bin",
        "source_commit": "a" * 40,
        "blob_oid": "b" * 40,
        "size_bytes": 1,
        "kind": "fixture",
    }

    with pytest.raises(restore.ArtifactRestoreError, match="blob_oid"):
        restore.validate_manifest({**base, "blob_oid": "ABC"})

    with pytest.raises(restore.ArtifactRestoreError, match="size_bytes"):
        restore.validate_manifest({**base, "size_bytes": -1})


def test_wrong_manifest_size_fails_before_destination_replace(tmp_path: Path) -> None:
    repo, manifest, _commit, _oid, _payload = _repo(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["size_bytes"] += 1
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(restore.ArtifactRestoreError, match="size mismatch"):
        restore.restore_artifact(manifest)

    assert not (repo / "deep" / "nested" / "artifact.bin").exists()


def test_unknown_manifest_fields_fail_closed(tmp_path: Path) -> None:
    _repo_root, manifest, _commit, _oid, _payload = _repo(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["url"] = "https://example.invalid/untrusted"

    with pytest.raises(restore.ArtifactRestoreError, match="keys mismatch"):
        restore.validate_manifest(payload)


def test_cli_reports_failure_without_materializing_invalid_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, manifest, _commit, _oid, _payload = _repo(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["blob_oid"] = "0" * 40
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = restore.main(
        [str(manifest), "--repo-root", str(repo), "--remote", "no-such-remote"]
    )

    assert result == 1
    assert "artifact restore failed" in capsys.readouterr().out
    assert not (repo / "deep" / "nested" / "artifact.bin").exists()
