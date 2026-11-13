"""Real signed original-game migration under bounded signer history."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_policy_chain_progress import (
    PolicyChainSignedProgressError, migrate_policy_chain_signed_progress,
    preflight_policy_chain_signed_progress,
)
from skeleton.app.offline_source_trust_policy import SCHEMA as POLICY_SCHEMA
from skeleton.testing.test_app_offline_policy_signed_progress_migration import policy_migration
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")


@pytest.fixture
def chain_progress(policy_migration, tmp_path):
    data, _ = policy_migration
    old = tmp_path / "old-progress-policy.json"
    old.write_text(json.dumps({
        "schema": POLICY_SCHEMA, "epoch": 2,
        "archive_sha256": data["expected_archive_sha256"],
        "manifest_sha256": data["expected_manifest_sha256"],
        "authorized_key_sha256": ["f" * 64],
        "revoked_key_sha256": [],
    }, sort_keys=True), encoding="utf-8")
    old.chmod(0o600)
    return {
        "archive": data["archive"], "destination": data["destination"],
        "original_save": data["original_save"],
        "migrated_save": data["migrated_save"],
        "public_key_file": data["public_key_file"],
        "signature_file": data["signature_file"],
        "policies": [old, data["policy_file"]],
        "expected_policy_sha256": [
            sha256(old.read_bytes()).hexdigest(), data["expected_policy_sha256"],
        ],
        "expected_archive_sha256": data["expected_archive_sha256"],
        "expected_manifest_sha256": data["expected_manifest_sha256"],
        "expected_save_sha256": data["expected_save_sha256"],
        "expected_public_key_sha256": data["expected_public_key_sha256"],
        "authorized": True,
    }


def test_read_only_preflight_does_not_reserve_or_migrate(chain_progress):
    original = chain_progress["original_save"].read_bytes()
    receipt = preflight_policy_chain_signed_progress(**chain_progress)
    assert receipt["policy_epoch_chain"] == [2, 3]
    assert receipt["destination_reserved"] is False
    assert receipt["migrated_save_published"] is False
    assert receipt["read_only"] is True
    assert receipt["release_certified"] is False
    assert not chain_progress["destination"].exists()
    assert not chain_progress["migrated_save"].exists()
    assert chain_progress["original_save"].read_bytes() == original


def test_real_game_install_and_private_save_replay_migration(chain_progress):
    original = chain_progress["original_save"].read_bytes()
    receipt = migrate_policy_chain_signed_progress(**chain_progress)
    assert receipt["policy_epoch_chain"] == [2, 3]
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["private_save_world_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["migration_atomic_across_destinations"] is False
    assert receipt["automatic_rollback_performed"] is False
    assert receipt["release_certified"] is False
    assert chain_progress["destination"].is_dir()
    assert chain_progress["migrated_save"].is_file()
    assert chain_progress["original_save"].read_bytes() == original


def test_wrong_save_pin_denied_without_publication(chain_progress):
    with pytest.raises(ValueError):
        migrate_policy_chain_signed_progress(**{
            **chain_progress, "expected_save_sha256": "0" * 64,
        })
    assert not chain_progress["destination"].exists()
    assert not chain_progress["migrated_save"].exists()


def test_final_policy_revokes_signer_before_reservation(chain_progress):
    final = chain_progress["policies"][-1]
    payload = json.loads(final.read_text(encoding="utf-8"))
    payload["authorized_key_sha256"] = ["e" * 64]
    final.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    final.chmod(0o600)
    with pytest.raises(PolicyChainSignedProgressError, match="not active"):
        migrate_policy_chain_signed_progress(**{
            **chain_progress,
            "expected_policy_sha256": [
                chain_progress["expected_policy_sha256"][0],
                sha256(final.read_bytes()).hexdigest(),
            ],
        })
    assert not chain_progress["destination"].exists()


def test_old_snapshot_swap_during_migration_requires_quarantine(
    chain_progress, tmp_path, monkeypatch,
):
    import skeleton.app.offline_policy_chain_progress as module
    original = module.migrate_policy_signed_progress
    old = chain_progress["policies"][0]

    def replace(*args, **kwargs):
        receipt = original(*args, **kwargs)
        replacement = tmp_path / "replacement-policy.json"
        replacement.write_bytes(old.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, old)
        return receipt

    monkeypatch.setattr(module, "migrate_policy_signed_progress", replace)
    with pytest.raises(PolicyChainSignedProgressError, match="changed"):
        migrate_policy_chain_signed_progress(**chain_progress)
    assert chain_progress["destination"].exists()
    assert chain_progress["migrated_save"].exists()


def test_operator_denial_precedes_policy_read(chain_progress, monkeypatch):
    import skeleton.app.offline_policy_chain_progress as module
    monkeypatch.setattr(
        module, "inspect_offline_trust_policy_chain",
        lambda *_a, **_k: pytest.fail("unauthorized policy read"),
    )
    with pytest.raises(PermissionError):
        migrate_policy_chain_signed_progress(**{
            **chain_progress, "authorized": False,
        })


def test_cli_preflight_and_actual_private_replay(chain_progress, capsys):
    argv = ["migrate-policy-chain-signed-progress"]
    for name, key in (
        ("archive", "archive"), ("destination", "destination"),
        ("original-save", "original_save"), ("migrated-save", "migrated_save"),
        ("public-key", "public_key_file"), ("signature", "signature_file"),
        ("expected-archive-sha256", "expected_archive_sha256"),
        ("expected-manifest-sha256", "expected_manifest_sha256"),
        ("expected-save-sha256", "expected_save_sha256"),
        ("expected-public-key-sha256", "expected_public_key_sha256"),
    ):
        argv += ["--" + name, str(chain_progress[key])]
    for path, pin in zip(
        chain_progress["policies"], chain_progress["expected_policy_sha256"],
    ):
        argv += ["--policy", str(path), "--expected-policy-sha256", pin]
    assert run_app_cli(argv) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(argv + ["--trusted-local-operator", "--preflight-only"]) == 0
    assert json.loads(capsys.readouterr().out)["read_only"] is True
    assert run_app_cli(argv + ["--trusted-local-operator"]) == 0
    assert json.loads(capsys.readouterr().out)["offline_gameplay_reexecuted"] is True
