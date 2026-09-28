"""Regression tests for legacy large-artifact extraction (#807 B006)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "materialize_large_artifact.py"
SPEC = importlib.util.spec_from_file_location("materialize_large_artifact", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
materializer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(materializer)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _build_fixture(tmp_path: Path, *, executable: bool = False):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "Skeleton Test")
    _git(repo, "config", "user.email", "skeleton@example.invalid")

    source = repo / "legacy" / "payload.bin"
    source.parent.mkdir(parents=True)
    payload = b"legacy-payload-v1\n" * 64
    source.write_bytes(payload)
    if executable:
        source.chmod(0o755)
    _git(repo, "add", "legacy/payload.bin")
    _git(repo, "commit", "-m", "add legacy payload")

    source_commit = _git(repo, "rev-parse", "HEAD")
    blob_oid = _git(repo, "rev-parse", f"{source_commit}:legacy/payload.bin")
    sha256 = hashlib.sha256(payload).hexdigest()

    source.unlink()
    _git(repo, "add", "-u")
    _git(repo, "commit", "-m", "extract legacy payload")

    catalog = {
        "schema": 1,
        "repository": "Apeloff1/Skeleton",
        "source_commit": source_commit,
        "git_object_format": "sha1",
        "integrity_algorithm": "sha256",
        "fetch_strategy": "immutable-git-history",
        "artifacts": [
            {
                "id": "fixture-payload",
                "source_path": "legacy/payload.bin",
                "git_blob_oid": blob_oid,
                "sha256": sha256,
                "size_bytes": len(payload),
                "media_type": "application/octet-stream",
                "license": "NOASSERTION",
                "redistribution_status": "test-only",
                "provenance_note": "Temporary deterministic regression fixture.",
                "destinations": ["legacy/payload.bin"],
                "mode": "0755" if executable else "0644",
            }
        ],
    }
    catalog_path = repo / "catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    return repo, catalog_path, payload, catalog


def test_repository_catalog_is_valid_and_covers_all_audited_destinations() -> None:
    catalog = materializer.load_catalog(materializer.DEFAULT_CATALOG)

    assert catalog["source_commit"] == "8aa947f24a4a11b8c91fa52214d45fe5a8c18043"
    assert len(catalog["artifacts"]) == 4
    assert sum(len(item["destinations"]) for item in catalog["artifacts"]) == 13

    expected = {
        "godot-snapshot-binary": "8b8d7c6089d8b4238e6ec872f027ef1a4bfc5241ddb5f8aec452b058368d255b",
        "ember-vanguard-presskit-trailer": "cffc7dbbd26fe7b0dd6914120ced914821f875f31e651ad89d818789027adeab",
        "ember-vanguard-presskit-showcase": "5f895609c8e37948fafbbf7b05726e413a5b913b6850a84182ad8741b2b4263f",
        "interactive-quizzes-mongo-fixture": "4630940970532b4b0e0cfe8964b5fc93333fa2057376e41d37a2ee7c0e4aaf13",
    }
    assert {item["id"]: item["sha256"] for item in catalog["artifacts"]} == expected


def test_materialize_restores_exact_bytes_and_mode_without_network(tmp_path: Path) -> None:
    repo, catalog_path, payload, _catalog = _build_fixture(
        tmp_path,
        executable=True,
    )

    restored = materializer.materialize(
        "fixture-payload",
        "legacy/payload.bin",
        repo_root=repo,
        catalog_path=catalog_path,
    )

    assert restored.read_bytes() == payload
    assert stat.S_IMODE(restored.stat().st_mode) == 0o755


def test_materialize_refuses_undeclared_destination(tmp_path: Path) -> None:
    repo, catalog_path, _payload, _catalog = _build_fixture(tmp_path)

    with pytest.raises(
        materializer.LargeArtifactError,
        match="not declared",
    ):
        materializer.materialize(
            "fixture-payload",
            "other/payload.bin",
            repo_root=repo,
            catalog_path=catalog_path,
        )


def test_materialize_refuses_existing_destination_without_overwrite(
    tmp_path: Path,
) -> None:
    repo, catalog_path, _payload, _catalog = _build_fixture(tmp_path)
    destination = repo / "legacy" / "payload.bin"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"local-data")

    with pytest.raises(
        materializer.LargeArtifactError,
        match="already exists",
    ):
        materializer.materialize(
            "fixture-payload",
            "legacy/payload.bin",
            repo_root=repo,
            catalog_path=catalog_path,
        )

    assert destination.read_bytes() == b"local-data"


def test_tampered_sha256_fails_without_publishing_partial_output(
    tmp_path: Path,
) -> None:
    repo, catalog_path, _payload, catalog = _build_fixture(tmp_path)
    catalog["artifacts"][0]["sha256"] = "0" * 64
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(materializer.LargeArtifactError, match="SHA-256 mismatch"):
        materializer.materialize(
            "fixture-payload",
            "legacy/payload.bin",
            repo_root=repo,
            catalog_path=catalog_path,
        )

    assert not (repo / "legacy" / "payload.bin").exists()
    assert not list((repo / "legacy").glob("*.partial"))


def test_source_path_blob_mismatch_fails_closed(tmp_path: Path) -> None:
    repo, catalog_path, _payload, catalog = _build_fixture(tmp_path)
    catalog["artifacts"][0]["git_blob_oid"] = "0" * 40
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(materializer.LargeArtifactError):
        materializer.materialize(
            "fixture-payload",
            "legacy/payload.bin",
            repo_root=repo,
            catalog_path=catalog_path,
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update({"schema": 2}),
        lambda payload: payload["artifacts"][0].update({"sha256": "ABC"}),
        lambda payload: payload["artifacts"][0].update(
            {"destinations": ["../escape.bin"]}
        ),
        lambda payload: payload["artifacts"][0].update(
            {"redistribution_status": ""}
        ),
        lambda payload: payload["artifacts"][0].update({"mode": "0999"}),
    ],
)
def test_malformed_catalog_fails_closed(tmp_path: Path, mutator) -> None:
    _repo, catalog_path, _payload, catalog = _build_fixture(tmp_path)
    mutator(catalog)
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(materializer.LargeArtifactError):
        materializer.load_catalog(catalog_path)


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(
        '{"schema":1,"schema":1,"repository":"Apeloff1/Skeleton"}',
        encoding="utf-8",
    )

    with pytest.raises(materializer.LargeArtifactError, match="duplicate JSON key"):
        materializer.load_catalog(path)


def test_repository_catalog_destinations_are_not_tracked_after_extraction() -> None:
    catalog = materializer.load_catalog(materializer.DEFAULT_CATALOG)

    for artifact in catalog["artifacts"]:
        for destination in artifact["destinations"]:
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", destination],
                cwd=ROOT,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert result.returncode != 0, destination
