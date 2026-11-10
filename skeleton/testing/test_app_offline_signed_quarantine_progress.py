"""Damaged game + pinned signature/save -> fresh playable game and replay."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_signed_quarantine_progress import (
    SignedQuarantineProgressRecoveryError, recover_signed_quarantine_progress,
)
from skeleton.testing.test_app_offline_signed_progress_migration import migration
from skeleton.testing.test_app_offline_signed_progress_migration import signed  # noqa: F401  (transitive fixture)


@pytest.fixture
def damaged(migration, tmp_path):
    partial = tmp_path / "quarantined-game"
    partial.mkdir(mode=0o700)
    (partial / "index.html").write_bytes(b"untrusted broken game")
    (partial / "index.html").chmod(0o600)
    return {"quarantined_source": partial, **{
        key: value for key, value in migration.items() if key != "expected_replay"
    }, "expected_replay": migration["expected_replay"]}


def _call(bundle, **changes):
    kwargs = {k: v for k, v in bundle.items() if k != "expected_replay"}
    kwargs["fresh_destination"] = kwargs.pop("destination")
    kwargs.update(changes)
    return recover_signed_quarantine_progress(**kwargs)


def _cli(bundle):
    return [
        "recover-signed-progress",
        "--quarantined", str(bundle["quarantined_source"]),
        "--archive", str(bundle["archive"]),
        "--destination", str(bundle["destination"]),
        "--original-save", str(bundle["original_save"]),
        "--migrated-save", str(bundle["migrated_save"]),
        "--public-key", str(bundle["public_key_file"]),
        "--signature", str(bundle["signature_file"]),
        "--expected-archive-sha256", bundle["expected_archive_sha256"],
        "--expected-manifest-sha256", bundle["expected_manifest_sha256"],
        "--expected-save-sha256", bundle["expected_save_sha256"],
        "--expected-public-key-sha256", bundle["expected_public_key_sha256"],
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_signed_game_and_progress_recovered_without_touching_damaged_source(
    damaged, capsys,
):
    partial = damaged["quarantined_source"]
    original_partial = (partial / "index.html").read_bytes()
    original_save = damaged["original_save"].read_bytes()
    assert run_app_cli(_cli(damaged)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "skeleton.app.signed_quarantine_progress_recovery.v1"
    assert result["replay_digest"] == damaged["expected_replay"]
    assert result["action_count"] == 3
    assert result["source_archive_signature_verified"] is True
    assert result["installed_source_archive_binding_verified"] is True
    assert result["private_save_world_binding_verified"] is True
    assert result["offline_gameplay_reexecuted"] is True
    assert result["original_quarantine_retained"] is True
    assert result["original_quarantine_cleared"] is False
    assert result["migration_atomic_across_destinations"] is False
    assert result["native_device_qualified"] is False
    assert result["release_certified"] is False
    assert damaged["migrated_save"].read_bytes() == original_save
    assert damaged["original_save"].read_bytes() == original_save
    assert (partial / "index.html").read_bytes() == original_partial
    assert (damaged["destination"] / "release.json").is_file()
    assert run_app_cli([
        "signed-delivery-assurance",
        "--installed", str(damaged["destination"]),
        "--archive", str(damaged["archive"]),
        "--save", str(damaged["migrated_save"]),
        "--public-key", str(damaged["public_key_file"]),
        "--signature", str(damaged["signature_file"]),
        "--expected-archive-sha256", damaged["expected_archive_sha256"],
        "--expected-manifest-sha256", damaged["expected_manifest_sha256"],
        "--expected-save-sha256", result["migrated_save_sha256"],
        "--expected-public-key-sha256", damaged["expected_public_key_sha256"],
        "--trusted-local-operator",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["release_certified"] is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("pin", [
    "expected_archive_sha256", "expected_manifest_sha256",
    "expected_save_sha256", "expected_public_key_sha256",
])
def test_wrong_pins_rejected_before_both_publications(damaged, pin):
    with pytest.raises(ValueError):
        _call(damaged, **{pin: "0" * 64})
    assert not damaged["destination"].exists()
    assert not damaged["migrated_save"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("collision", ["destination", "migrated_save"])
def test_occupied_destinations_are_never_clobbered(damaged, collision):
    path = damaged[collision]
    if collision == "destination":
        path.mkdir(mode=0o700)
        marker = path / "keep.txt"
        marker.write_text("owner", encoding="utf-8")
    else:
        path.write_text("owner", encoding="utf-8")
    with pytest.raises((OSError, ValueError)):
        _call(damaged)
    assert (marker.read_text(encoding="utf-8") if collision == "destination"
            else path.read_text(encoding="utf-8")) == "owner"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("placement", ["inside_quarantine", "inside_new_game"])
def test_new_save_cannot_mutate_quarantine_or_installed_source(damaged, placement):
    if placement == "inside_quarantine":
        target = damaged["quarantined_source"] / "save.json"
    else:
        target = damaged["destination"] / "save.json"
    with pytest.raises(SignedQuarantineProgressRecoveryError):
        _call(damaged, migrated_save=target)
    assert not damaged["destination"].exists()
    assert not target.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_quarantine_symlink_is_rejected(damaged, tmp_path):
    alias = tmp_path / "quarantine-alias"
    alias.symlink_to(damaged["quarantined_source"], target_is_directory=True)
    with pytest.raises((OSError, ValueError)):
        _call(damaged, quarantined_source=alias)
    assert not damaged["destination"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_quarantine_mutation_after_publication_fails_closed(damaged, monkeypatch):
    import skeleton.app.offline_signed_quarantine_progress as module
    original = module.migrate_signed_offline_progress

    def mutate(*args, **kwargs):
        receipt = original(*args, **kwargs)
        (damaged["quarantined_source"] / "index.html").write_bytes(b"swapped")
        return receipt

    monkeypatch.setattr(module, "migrate_signed_offline_progress", mutate)
    with pytest.raises((SignedQuarantineProgressRecoveryError, ValueError)):
        _call(damaged)
    assert damaged["destination"].is_dir()
    assert damaged["migrated_save"].is_file()
    assert damaged["quarantined_source"].is_dir()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_operator_acknowledgement_required_before_reads(damaged, monkeypatch):
    import skeleton.app.offline_signed_quarantine_progress as module

    def unexpected(*args, **kwargs):
        raise AssertionError("unauthorized read")

    monkeypatch.setattr(module, "_quarantine_identity", unexpected)
    with pytest.raises(PermissionError):
        _call(damaged, authorized=False)
    assert not damaged["destination"].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_denies_missing_authority_without_publication(damaged, capsys):
    args = _cli(damaged)
    args.remove("--trusted-local-operator")
    assert run_app_cli(args) == 2
    result = json.loads(capsys.readouterr().err)
    assert result["status"] == "blocked"
    assert result["release_certified"] is False
    assert not damaged["destination"].exists()
    assert not damaged["migrated_save"].exists()

@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_signed_progress_quarantine_preflight_is_read_only(damaged, capsys):
    args = _cli(damaged) + ["--preflight-only"]
    old_save = damaged["original_save"].read_bytes()
    partial = (damaged["quarantined_source"] / "index.html").read_bytes()
    assert run_app_cli(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "skeleton.app.signed_quarantine_progress_preflight.v1"
    assert result["source_archive_signature_verified"] is True
    assert result["private_save_world_binding_verified"] is True
    assert result["replay_digest"] == damaged["expected_replay"]
    assert result["destination_reserved"] is False
    assert result["migrated_save_published"] is False
    assert result["read_only"] is True
    assert result["release_certified"] is False
    assert not damaged["destination"].exists()
    assert not damaged["migrated_save"].exists()
    assert damaged["original_save"].read_bytes() == old_save
    assert (damaged["quarantined_source"] / "index.html").read_bytes() == partial


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_preflight_wrong_save_pin_never_publishes(damaged, capsys):
    args = _cli(damaged) + ["--preflight-only"]
    pos = args.index("--expected-save-sha256") + 1
    args[pos] = "0" * 64
    assert run_app_cli(args) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not damaged["destination"].exists()
    assert not damaged["migrated_save"].exists()
