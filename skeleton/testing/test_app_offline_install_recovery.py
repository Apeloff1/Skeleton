"""Real source archive -> damaged install -> new no-clobber install -> replay."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_install_recovery import (
    OfflineInstallRecoveryError, recover_quarantined_offline_install,
)
from skeleton.testing.test_app_offline_archive_install import _archive


@pytest.fixture
def damaged(tmp_path, capsys):
    source, archive, archive_pin, manifest_pin = _archive(tmp_path, capsys)
    partial = tmp_path / "partial-install"
    partial.mkdir(mode=0o700)
    original = (source / "index.html").read_bytes()
    (partial / "index.html").write_bytes(
        bytes((original[0] ^ 1,)) + original[1:]
    )
    target = tmp_path / "fresh-install"
    return partial, archive, archive_pin, manifest_pin, target, source


def _call(bundle, **overrides):
    partial, archive, archive_pin, manifest_pin, target, _ = bundle
    args = {
        "quarantined_source": partial, "archive": archive,
        "fresh_destination": target,
        "expected_archive_sha256": archive_pin,
        "expected_manifest_sha256": manifest_pin, "authorized": True,
    }
    args.update(overrides)
    return recover_quarantined_offline_install(**args)


def _cli(bundle):
    partial, archive, archive_pin, manifest_pin, target, _ = bundle
    return [
        "recover-install", "--quarantined", str(partial),
        "--archive", str(archive), "--destination", str(target),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest_pin,
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_damaged_source_is_retained_and_fresh_source_replayed(
    damaged, tmp_path, capsys,
):
    partial, archive, archive_pin, manifest_pin, target, source = damaged
    before = (partial / "index.html").read_bytes()
    assert run_app_cli(_cli(damaged)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["schema"] == "skeleton.app.offline_install_fresh_recovery.v1"
    assert result["fresh_source_installation_verified"] is True
    assert result["offline_gameplay_reexecuted"] is True
    assert result["quarantined_mismatched_files"] == 1
    assert result["quarantined_missing_files"] > 0
    assert result["original_quarantine_retained"] is True
    assert result["original_quarantine_cleared"] is False
    assert result["automatic_rollback_performed"] is False
    assert result["native_device_qualified"] is False
    assert result["package_signed"] is False
    assert result["release_certified"] is False
    assert (partial / "index.html").read_bytes() == before
    assert (target / "index.html").read_bytes() == (source / "index.html").read_bytes()
    assert run_app_cli([
        "studio-journey", "--reconcile-install",
        "--output", str(target), "--archive", str(archive),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest_pin,
        "--trusted-local-operator",
    ]) == 0
    assert json.loads(capsys.readouterr().out)[
        "installed_source_archive_binding_verified"
    ] is True


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
@pytest.mark.parametrize("pin", ["archive", "manifest"])
def test_wrong_pins_never_reserve_destination(damaged, pin):
    target = damaged[4]
    with pytest.raises(ValueError):
        _call(damaged, **{"expected_" + pin + "_sha256": "0" * 64})
    assert not target.exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_authority_required_before_quarantine_read(damaged, monkeypatch):
    import skeleton.app.offline_install_recovery as module

    def unexpected(*args, **kwargs):
        raise AssertionError("read before authorization")

    monkeypatch.setattr(module, "_quarantine_identity", unexpected)
    with pytest.raises(PermissionError):
        _call(damaged, authorized=False)


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_existing_fresh_destination_is_never_overwritten(damaged):
    target = damaged[4]
    target.mkdir(mode=0o700)
    marker = target / "owner.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError):
        _call(damaged)
    assert marker.read_text(encoding="utf-8") == "preserve"


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
@pytest.mark.parametrize("relative", ["same", "child", "parent"])
def test_nested_or_same_quarantine_destination_is_rejected(
    damaged, relative,
):
    partial = damaged[0]
    if relative == "same":
        target = partial
    elif relative == "child":
        target = partial / "new"
    else:
        target = partial.parent
    with pytest.raises(OfflineInstallRecoveryError):
        _call(damaged, fresh_destination=target)
    assert not (partial / "new").exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_quarantine_symlink_root_is_rejected(damaged, tmp_path):
    partial = damaged[0]
    alias = tmp_path / "partial-alias"
    alias.symlink_to(partial, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        _call(damaged, quarantined_source=alias)
    assert not damaged[4].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_quarantine_mutation_before_install_is_rejected(
    damaged, monkeypatch,
):
    import skeleton.app.offline_install_recovery as module
    partial = damaged[0]
    original = module.preflight_offline_game_install

    def mutate_after_preflight(*args, **kwargs):
        result = original(*args, **kwargs)
        (partial / "index.html").write_bytes(b"unexpected mutation")
        return result

    monkeypatch.setattr(module, "preflight_offline_game_install",
                        mutate_after_preflight)
    with pytest.raises(OfflineInstallRecoveryError):
        _call(damaged)
    assert not damaged[4].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_quarantine_mutation_after_install_fails_closed_without_cleanup(
    damaged, monkeypatch,
):
    import skeleton.app.offline_install_recovery as module
    partial = damaged[0]
    original = module.install_offline_game_source

    def mutate_after_install(*args, **kwargs):
        result = original(*args, **kwargs)
        (partial / "index.html").write_bytes(b"unexpected mutation")
        return result

    monkeypatch.setattr(module, "install_offline_game_source",
                        mutate_after_install)
    with pytest.raises((OfflineInstallRecoveryError, ValueError)):
        _call(damaged)
    assert damaged[4].is_dir()
    assert (damaged[4] / "release.json").is_file()
    assert partial.is_dir()


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_archive_tamper_rejected_before_install(damaged, capsys):
    archive = damaged[1]
    archive.write_bytes(archive.read_bytes() + b"tamper")
    assert run_app_cli(_cli(damaged)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not damaged[4].exists()


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_cli_rejects_unacknowledged_recovery(damaged, capsys):
    command = _cli(damaged)
    command.remove("--trusted-local-operator")
    assert run_app_cli(command) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not damaged[4].exists()
