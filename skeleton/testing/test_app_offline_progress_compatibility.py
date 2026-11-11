"""Archive/save compatibility is proved before installation reservation."""
from __future__ import annotations

import json
import os
import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_progress_compatibility import (
    OfflineArchiveSaveCompatibilityError, verify_archived_progress_binding,
)
from skeleton.testing.test_app_offline_progress_migration import (
    _journey, _save, _package, _migrate,
)


def _prepared(tmp_path, capsys):
    source, manifest_pin = _journey(tmp_path, capsys)
    save, save_pin, digest = _save(tmp_path, capsys, source, manifest_pin)
    archive, archive_pin = _package(tmp_path, capsys, source, manifest_pin)
    return archive, archive_pin, manifest_pin, save, save_pin, digest


def _verify(archive, archive_pin, manifest_pin, save, save_pin, *, authorized=True):
    return verify_archived_progress_binding(
        archive, save.read_bytes(), expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin,
        expected_save_sha256=save_pin, authorized=authorized,
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_read_only_preflight_replays_canonical_private_save(tmp_path, capsys):
    archive, archive_pin, manifest_pin, save, save_pin, digest = _prepared(
        tmp_path, capsys,
    )
    original_archive, original_save = archive.read_bytes(), save.read_bytes()
    inventory_before = set(tmp_path.iterdir())
    receipt = _verify(archive, archive_pin, manifest_pin, save, save_pin)
    assert receipt["replay_digest"] == digest
    assert receipt["action_count"] == 3
    assert receipt["save_world_binding_verified"] is True
    assert receipt["private_save_replayed"] is True
    assert receipt["read_only"] is True
    assert receipt["source_installation_verified"] is False
    assert receipt["destination_reserved"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["release_certified"] is False
    assert archive.read_bytes() == original_archive
    assert save.read_bytes() == original_save
    assert set(tmp_path.iterdir()) == inventory_before


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_foreign_progress_rejected_before_install_reservation(tmp_path, capsys):
    archive, archive_pin, manifest_pin, _, _, _ = _prepared(tmp_path, capsys)
    foreign_source, foreign_manifest = _journey(
        tmp_path, capsys, "foreign-world", 987,
    )
    # A second original save must not overwrite the prepared source's
    # create-only progress receipt; keep both worlds independent.
    foreign_save_dir = tmp_path / "foreign-progress"
    foreign_save_dir.mkdir(mode=0o700)
    foreign_save, foreign_pin, _ = _save(
        foreign_save_dir, capsys, foreign_source, foreign_manifest,
    )
    destination = tmp_path / "never-reserved"
    migrated = tmp_path / "never-published.json"
    assert run_app_cli(_migrate(
        archive, archive_pin, manifest_pin, foreign_save, foreign_pin,
        destination, migrated,
    )) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not destination.exists()
    assert not migrated.exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
@pytest.mark.parametrize("pin", ["archive", "manifest", "save"])
def test_independent_pin_mismatch_rejected(tmp_path, capsys, pin):
    archive, archive_pin, manifest_pin, save, save_pin, _ = _prepared(
        tmp_path, capsys,
    )
    pins = {"archive": archive_pin, "manifest": manifest_pin, "save": save_pin}
    pins[pin] = "0" * 64
    with pytest.raises(ValueError):
        _verify(archive, pins["archive"], pins["manifest"],
                save, pins["save"])


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_unauthorized_and_tampered_save_rejected(tmp_path, capsys):
    archive, archive_pin, manifest_pin, save, save_pin, _ = _prepared(
        tmp_path, capsys,
    )
    with pytest.raises(PermissionError):
        _verify(archive, archive_pin, manifest_pin, save, save_pin,
                authorized=False)
    with pytest.raises(OfflineArchiveSaveCompatibilityError):
        verify_archived_progress_binding(
            archive, save.read_bytes() + b" ",
            expected_archive_sha256=archive_pin,
            expected_manifest_sha256=manifest_pin,
            expected_save_sha256=save_pin, authorized=True,
        )


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_same_bytes_archive_in_place_replacement_is_not_accepted(
    tmp_path, capsys, monkeypatch,
):
    archive, archive_pin, manifest_pin, save, save_pin, _ = _prepared(
        tmp_path, capsys,
    )
    import skeleton.app.offline_progress_compatibility as module
    original_read = module._read_private_archive
    swapped = False

    def replace_after_inventory(path):
        nonlocal swapped
        if not swapped:
            replacement = tmp_path / "new-inode.zip"
            replacement.write_bytes(archive.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, archive)
            swapped = True
        return original_read(path)

    monkeypatch.setattr(module, "_read_private_archive", replace_after_inventory)
    with pytest.raises(OfflineArchiveSaveCompatibilityError):
        _verify(archive, archive_pin, manifest_pin, save, save_pin)
    assert swapped is True


@pytest.mark.skipif(os.name != "posix", reason="POSIX nofollow custody")
def test_symlinked_archive_rejected(tmp_path, capsys):
    archive, archive_pin, manifest_pin, save, save_pin, _ = _prepared(
        tmp_path, capsys,
    )
    alias = tmp_path / "alias.zip"
    alias.symlink_to(archive)
    with pytest.raises(ValueError):
        _verify(alias, archive_pin, manifest_pin, save, save_pin)
