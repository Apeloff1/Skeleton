"""Signed original game -> replay save -> migrate -> independent delivery acceptance."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_signed_progress_migration import (
    SignedOfflineProgressMigrationError, migrate_signed_offline_progress,
    preflight_signed_offline_progress,
)
from skeleton.testing.test_app_offline_archive_signature import signed


@pytest.fixture
def migration(signed, tmp_path, capsys):
    archive, archive_pin, manifest_pin, key, signature, key_pin = signed
    source = tmp_path / "source-game"
    old_save = tmp_path / "original-save.json"
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(source),
        "--expected-manifest-sha256", manifest_pin, "--moves", "up,right,down",
        "--save", str(old_save), "--trusted-local-operator",
    ]) == 0
    played = json.loads(capsys.readouterr().out)
    return {
        "archive": archive, "destination": tmp_path / "installed-game",
        "original_save": old_save, "migrated_save": tmp_path / "new-save.json",
        "public_key_file": key, "signature_file": signature,
        "expected_archive_sha256": archive_pin,
        "expected_manifest_sha256": manifest_pin,
        "expected_save_sha256": played["independent_save_sha256"],
        "expected_public_key_sha256": key_pin,
        "authorized": True,
        "expected_replay": played["replay_digest"],
    }


def _call(data, **changes):
    values = {k: v for k, v in data.items() if k != "expected_replay"}
    values.update(changes)
    return migrate_signed_offline_progress(**values)


def _cli(data):
    return [
        "migrate-signed-progress", "--archive", str(data["archive"]),
        "--destination", str(data["destination"]),
        "--original-save", str(data["original_save"]),
        "--migrated-save", str(data["migrated_save"]),
        "--public-key", str(data["public_key_file"]),
        "--signature", str(data["signature_file"]),
        "--expected-archive-sha256", data["expected_archive_sha256"],
        "--expected-manifest-sha256", data["expected_manifest_sha256"],
        "--expected-save-sha256", data["expected_save_sha256"],
        "--expected-public-key-sha256", data["expected_public_key_sha256"],
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
def test_signed_migration_real_game_save_and_cli(migration, capsys):
    before = migration["original_save"].read_bytes()
    assert run_app_cli(_cli(migration)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == "skeleton.app.signed_offline_progress_migration.v1"
    assert receipt["replay_digest"] == migration["expected_replay"]
    assert receipt["action_count"] == 3
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["private_save_world_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["migration_atomic_across_destinations"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["package_signed"] is False
    assert receipt["release_certified"] is False
    assert migration["migrated_save"].read_bytes() == before
    assert migration["original_save"].read_bytes() == before
    assert (migration["destination"] / "release.json").is_file()
    assert run_app_cli([
        "signed-delivery-assurance",
        "--installed", str(migration["destination"]),
        "--archive", str(migration["archive"]),
        "--save", str(migration["migrated_save"]),
        "--public-key", str(migration["public_key_file"]),
        "--signature", str(migration["signature_file"]),
        "--expected-archive-sha256", migration["expected_archive_sha256"],
        "--expected-manifest-sha256", migration["expected_manifest_sha256"],
        "--expected-save-sha256", receipt["migrated_save_sha256"],
        "--expected-public-key-sha256", migration["expected_public_key_sha256"],
        "--trusted-local-operator",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["release_certified"] is False


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
@pytest.mark.parametrize("pin", [
    "expected_archive_sha256", "expected_manifest_sha256",
    "expected_save_sha256", "expected_public_key_sha256",
])
def test_wrong_pin_never_publishes(migration, pin):
    with pytest.raises(ValueError):
        _call(migration, **{pin: "0" * 64})
    assert not migration["destination"].exists()
    assert not migration["migrated_save"].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
def test_authority_denied_before_any_file_access(migration, monkeypatch):
    import skeleton.app.offline_signed_progress_migration as module

    def forbidden(*args, **kwargs):
        raise AssertionError("read without authorization")

    monkeypatch.setattr(module, "_input_identities", forbidden)
    with pytest.raises(PermissionError):
        _call(migration, authorized=False)
    assert not migration["destination"].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
@pytest.mark.parametrize("collision", ["destination", "migrated_save"])
def test_no_clobber_preflight_preserves_existing_owner_data(migration, collision):
    target = migration[collision]
    if collision == "destination":
        target.mkdir()
        marker = target / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
    else:
        target.write_text("keep", encoding="utf-8")
    with pytest.raises((OSError, ValueError)):
        _call(migration)
    if collision == "destination":
        assert marker.read_text(encoding="utf-8") == "keep"
    else:
        assert target.read_text(encoding="utf-8") == "keep"
    assert not migration["migrated_save" if collision == "destination" else "destination"].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
def test_signature_swap_after_publication_fails_and_retains_quarantine(
    migration, tmp_path, monkeypatch,
):
    import skeleton.app.offline_signed_progress_migration as module

    original = module.migrate_offline_game_progress

    def swap_after(*args, **kwargs):
        result = original(*args, **kwargs)
        path = migration["signature_file"]
        replacement = tmp_path / "replacement.sig"
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, path)
        return result

    monkeypatch.setattr(module, "migrate_offline_game_progress", swap_after)
    with pytest.raises((SignedOfflineProgressMigrationError, ValueError)):
        _call(migration)
    assert migration["destination"].is_dir()
    assert migration["migrated_save"].is_file()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
def test_invalid_detached_signature_fails_before_install(migration):
    path = migration["signature_file"]
    raw = path.read_bytes()
    path.write_bytes(bytes((raw[0] ^ 1,)) + raw[1:])
    with pytest.raises(ValueError):
        _call(migration)
    assert not migration["destination"].exists()
    assert not migration["migrated_save"].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
def test_symlinked_original_save_fails_before_install(migration, tmp_path):
    alias = tmp_path / "alias-save.json"
    alias.symlink_to(migration["original_save"])
    with pytest.raises((OSError, ValueError)):
        _call(migration, original_save=alias)
    assert not migration["destination"].exists()
    assert not migration["migrated_save"].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
def test_signed_read_only_preflight_no_destination_reservation(migration, capsys):
    args = _cli(migration) + ["--preflight-only"]
    assert run_app_cli(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == "skeleton.app.signed_offline_progress_preflight.v1"
    assert receipt["replay_digest"] == migration["expected_replay"]
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["save_world_binding_verified"] is True
    assert receipt["destination_reserved"] is False
    assert receipt["read_only"] is True
    assert receipt["release_certified"] is False
    assert not migration["destination"].exists()
    assert not migration["migrated_save"].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor-safe custody")
def test_preflight_wrong_pin_does_not_publish(migration):
    with pytest.raises(ValueError):
        preflight_signed_offline_progress(
            **{**{k: v for k, v in migration.items() if k != "expected_replay"},
               "expected_public_key_sha256": "0" * 64}
        )
    assert not migration["destination"].exists()
    assert not migration["migrated_save"].exists()
