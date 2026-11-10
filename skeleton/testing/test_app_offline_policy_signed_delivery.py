"""Real migrated replay + signed source + pinned policy delivery acceptance."""
from __future__ import annotations

from hashlib import sha256
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_policy_signed_delivery import (
    assure_policy_signed_offline_delivery,
)
from skeleton.app.offline_policy_signed_progress_migration import (
    migrate_policy_signed_progress,
)
from skeleton.testing.test_app_offline_policy_signed_progress_migration import policy_migration
from skeleton.testing.test_app_offline_policy_signed_progress_migration import migration  # noqa: F401  (transitive fixture)
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)


@pytest.fixture
def delivered(policy_migration):
    data, policy = policy_migration
    migration = migrate_policy_signed_progress(**data)
    kwargs = {
        "installed_source": data["destination"],
        "archive": data["archive"],
        "private_save": data["migrated_save"],
        "public_key_file": data["public_key_file"],
        "signature_file": data["signature_file"],
        "policy_file": data["policy_file"],
        "expected_archive_sha256": data["expected_archive_sha256"],
        "expected_manifest_sha256": data["expected_manifest_sha256"],
        "expected_save_sha256": migration["migrated_save_sha256"],
        "expected_public_key_sha256": data["expected_public_key_sha256"],
        "expected_policy_sha256": data["expected_policy_sha256"],
        "authorized": True,
    }
    return kwargs, policy, migration


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_signed_installed_game_replay_assurance_read_only(delivered):
    kwargs, _, migrated = delivered
    before = kwargs["private_save"].read_bytes()
    receipt = assure_policy_signed_offline_delivery(**kwargs)
    assert receipt["world_digest"] == migrated["world_digest"]
    assert receipt["replay_digest"] == migrated["replay_digest"]
    assert receipt["key_authorized_by_pinned_policy"] is True
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["private_save_world_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["read_only"] is True
    assert receipt["policy_freshness_independently_proven"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["release_certified"] is False
    assert kwargs["private_save"].read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_policy_revocation_after_migration_denies_delivery(delivered):
    kwargs, payload, _ = delivered
    payload["revoked_key_sha256"] = [kwargs["expected_public_key_sha256"]]
    policy = kwargs["policy_file"]
    policy.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    policy.chmod(0o600)
    kwargs["expected_policy_sha256"] = sha256(policy.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        assure_policy_signed_offline_delivery(**kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_wrong_save_pin_blocks_assurance(delivered):
    kwargs, _, _ = delivered
    with pytest.raises(ValueError):
        assure_policy_signed_offline_delivery(
            **{**kwargs, "expected_save_sha256": "0" * 64},
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_same_byte_policy_swap_during_delivery_denied(
    delivered, tmp_path, monkeypatch,
):
    import skeleton.app.offline_policy_signed_delivery as module
    kwargs, _, _ = delivered
    original = module.assure_signed_offline_delivery
    policy = kwargs["policy_file"]

    def swap(*args, **inner):
        result = original(*args, **inner)
        replacement = tmp_path / "replacement.json"
        replacement.write_bytes(policy.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, policy)
        return result

    monkeypatch.setattr(module, "assure_signed_offline_delivery", swap)
    with pytest.raises(ValueError):
        assure_policy_signed_offline_delivery(**kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_authority_precedes_policy_io(delivered, monkeypatch):
    import skeleton.app.offline_policy_signed_delivery as module
    kwargs, _, _ = delivered

    def forbidden(*args, **inner):
        raise AssertionError("unauthorized trust policy read")

    monkeypatch.setattr(module, "_read_policy", forbidden)
    with pytest.raises(PermissionError):
        assure_policy_signed_offline_delivery(**{**kwargs, "authorized": False})


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_read_only_acceptance_and_authority_denial(delivered, capsys):
    kwargs, _, _ = delivered
    args = ["policy-signed-delivery-assurance"]
    for name, key in (
        ("installed", "installed_source"), ("archive", "archive"),
        ("save", "private_save"), ("public-key", "public_key_file"),
        ("signature", "signature_file"), ("policy", "policy_file"),
        ("expected-archive-sha256", "expected_archive_sha256"),
        ("expected-manifest-sha256", "expected_manifest_sha256"),
        ("expected-save-sha256", "expected_save_sha256"),
        ("expected-public-key-sha256", "expected_public_key_sha256"),
        ("expected-policy-sha256", "expected_policy_sha256"),
    ):
        args.extend(["--" + name, str(kwargs[key])])
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert run_app_cli(args + ["--trusted-local-operator"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["read_only"] is True
    assert receipt["release_certified"] is False
