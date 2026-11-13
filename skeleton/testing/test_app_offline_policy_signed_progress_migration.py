"""Policy -> signed ZIP -> original playable source -> private replay migration."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_policy_signed_progress_migration import (
    migrate_policy_signed_progress, preflight_policy_signed_progress,
)
from skeleton.app.offline_source_trust_policy import SCHEMA
from skeleton.testing.test_app_offline_signed_progress_migration import migration
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)


@pytest.fixture
def policy_migration(migration, tmp_path):
    data = {k: v for k, v in migration.items() if k != "expected_replay"}
    policy = tmp_path / "migration-trust.json"
    payload = {
        "schema": SCHEMA,
        "epoch": 3,
        "archive_sha256": data["expected_archive_sha256"],
        "manifest_sha256": data["expected_manifest_sha256"],
        "authorized_key_sha256": [data["expected_public_key_sha256"]],
        "revoked_key_sha256": [],
    }
    policy.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    policy.chmod(0o600)
    data["policy_file"] = policy
    data["expected_policy_sha256"] = sha256(policy.read_bytes()).hexdigest()
    return data, payload


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_preflight_is_read_only(policy_migration):
    data, _ = policy_migration
    before = data["original_save"].read_bytes()
    receipt = preflight_policy_signed_progress(**data)
    assert receipt["destination_reserved"] is False
    assert receipt["migrated_save_published"] is False
    assert receipt["key_authorized_by_pinned_policy"] is True
    assert receipt["release_certified"] is False
    assert not data["destination"].exists()
    assert not data["migrated_save"].exists()
    assert data["original_save"].read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_signed_migration_real_playable_save(policy_migration):
    data, _ = policy_migration
    original = data["original_save"].read_bytes()
    receipt = migrate_policy_signed_progress(**data)
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["private_save_world_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["migration_atomic_across_destinations"] is False
    assert receipt["late_failure_requires_quarantine"] is True
    assert receipt["release_certified"] is False
    assert data["destination"].is_dir()
    assert data["migrated_save"].is_file()
    assert data["original_save"].read_bytes() == original
    with pytest.raises((ValueError, OSError, FileExistsError)):
        migrate_policy_signed_progress(**data)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_revoked_key_blocks_before_any_publication(policy_migration):
    data, payload = policy_migration
    payload["revoked_key_sha256"] = [data["expected_public_key_sha256"]]
    data["policy_file"].write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    data["policy_file"].chmod(0o600)
    data["expected_policy_sha256"] = sha256(data["policy_file"].read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        migrate_policy_signed_progress(**data)
    assert not data["destination"].exists()
    assert not data["migrated_save"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_wrong_policy_pin_blocks_before_install(policy_migration):
    data, _ = policy_migration
    with pytest.raises(ValueError):
        migrate_policy_signed_progress(
            **{**data, "expected_policy_sha256": "0" * 64},
        )
    assert not data["destination"].exists()
    assert not data["migrated_save"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_no_authority_before_policy_access(policy_migration, monkeypatch):
    import skeleton.app.offline_policy_signed_progress_migration as module
    data, _ = policy_migration

    def forbidden(*args, **kwargs):
        raise AssertionError("unauthorized policy access")

    monkeypatch.setattr(module, "_read_policy", forbidden)
    with pytest.raises(PermissionError):
        migrate_policy_signed_progress(**{**data, "authorized": False})
    assert not data["destination"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_inode_swap_after_migration_keeps_quarantine(
    policy_migration, tmp_path, monkeypatch,
):
    import skeleton.app.offline_policy_signed_progress_migration as module
    data, _ = policy_migration
    original = module.migrate_signed_offline_progress
    policy = data["policy_file"]

    def mutate_after_publication(*args, **kwargs):
        result = original(*args, **kwargs)
        replacement = tmp_path / "same-policy.json"
        replacement.write_bytes(policy.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, policy)
        return result

    monkeypatch.setattr(module, "migrate_signed_offline_progress",
                        mutate_after_publication)
    with pytest.raises(ValueError):
        migrate_policy_signed_progress(**data)
    assert data["destination"].is_dir()
    assert data["migrated_save"].is_file()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_policy_preflight_and_blocked_authority(policy_migration, capsys):
    data, _ = policy_migration
    args = ["migrate-policy-signed-progress"]
    for name, key in (
        ("archive", "archive"), ("destination", "destination"),
        ("original-save", "original_save"), ("migrated-save", "migrated_save"),
        ("public-key", "public_key_file"), ("signature", "signature_file"),
        ("policy", "policy_file"),
        ("expected-archive-sha256", "expected_archive_sha256"),
        ("expected-manifest-sha256", "expected_manifest_sha256"),
        ("expected-save-sha256", "expected_save_sha256"),
        ("expected-public-key-sha256", "expected_public_key_sha256"),
        ("expected-policy-sha256", "expected_policy_sha256"),
    ):
        args.extend(["--" + name, str(data[key])])
    assert run_app_cli(args + ["--preflight-only"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(args + ["--preflight-only", "--trusted-local-operator"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["destination_reserved"] is False
    assert receipt["release_certified"] is False
