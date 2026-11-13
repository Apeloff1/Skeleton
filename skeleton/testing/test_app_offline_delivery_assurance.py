"""Integrated original-game source -> archive -> install -> saved replay assurance."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_delivery_assurance import (
    OfflineDeliveryAssuranceError, assure_offline_delivery,
)
from skeleton.testing.test_app_offline_progress_migration import (
    _journey, _package, _save,
)


@pytest.fixture
def delivered(tmp_path, capsys):
    source, manifest = _journey(tmp_path, capsys)
    save, save_pin, replay = _save(tmp_path, capsys, source, manifest)
    archive, archive_pin = _package(tmp_path, capsys, source, manifest)
    installed = tmp_path / "installed"
    assert run_app_cli([
        "studio-journey", "--install-archive", "--archive", str(archive),
        "--output", str(installed), "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest, "--trusted-local-operator",
    ]) == 0
    capsys.readouterr()
    return installed, archive, save, manifest, archive_pin, save_pin, replay


def _call(bundle, **overrides):
    installed, archive, save, manifest, archive_pin, save_pin, _ = bundle
    args = {
        "installed_source": installed, "archive": archive, "private_save": save,
        "expected_manifest_sha256": manifest,
        "expected_archive_sha256": archive_pin,
        "expected_save_sha256": save_pin, "authorized": True,
    }
    args.update(overrides)
    return assure_offline_delivery(**args)


def _cli(bundle):
    installed, archive, save, manifest, archive_pin, save_pin, _ = bundle
    return [
        "delivery-assurance", "--installed", str(installed),
        "--archive", str(archive), "--save", str(save),
        "--expected-manifest-sha256", manifest,
        "--expected-archive-sha256", archive_pin,
        "--expected-save-sha256", save_pin,
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_end_to_end_delivery_assurance_is_read_only(delivered, tmp_path, capsys):
    installed, archive, save, manifest, archive_pin, save_pin, replay = delivered
    before = (
        (installed / "release.json").read_bytes(),
        archive.read_bytes(), save.read_bytes(),
        set(tmp_path.iterdir()),
    )
    assert run_app_cli(_cli(delivered)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["schema"] == "skeleton.app.offline_delivery_assurance.v1"
    assert receipt["replay_digest"] == replay
    assert receipt["manifest_sha256"] == manifest
    assert receipt["archive_sha256"] == archive_pin
    assert receipt["save_sha256"] == save_pin
    assert receipt["action_count"] == 3
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["private_save_world_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["read_only"] is True
    assert receipt["migration_atomicity_proven"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["package_signed"] is False
    assert receipt["rights_certified"] is False
    assert receipt["release_certified"] is False
    assert before == (
        (installed / "release.json").read_bytes(),
        archive.read_bytes(), save.read_bytes(),
        set(tmp_path.iterdir()),
    )


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
@pytest.mark.parametrize("pin", ["manifest", "archive", "save"])
def test_wrong_independent_pin_is_rejected(delivered, pin):
    kwargs = {"expected_" + pin + "_sha256": "0" * 64}
    with pytest.raises(ValueError):
        _call(delivered, **kwargs)


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
@pytest.mark.parametrize("pin", ["manifest", "archive", "save"])
def test_malformed_or_missing_pin_is_rejected_before_any_read(delivered, pin, monkeypatch):
    import skeleton.app.offline_delivery_assurance as module

    def should_not_read(*args, **kwargs):
        raise AssertionError("unsafe read before pin validation")

    monkeypatch.setattr(module, "_source_identity", should_not_read)
    with pytest.raises(OfflineDeliveryAssuranceError):
        _call(delivered, **{"expected_" + pin + "_sha256": "Z" * 64})


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_authority_rejected_before_source_read(delivered, monkeypatch):
    import skeleton.app.offline_delivery_assurance as module

    def should_not_read(*args, **kwargs):
        raise AssertionError("unauthorized source access")

    monkeypatch.setattr(module, "_source_identity", should_not_read)
    with pytest.raises(PermissionError):
        _call(delivered, authorized=False)


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
@pytest.mark.parametrize("target", ["archive", "save", "source"])
def test_tampering_fails_closed_without_success_receipt(delivered, target, capsys):
    installed, archive, save, *_ = delivered
    if target == "archive":
        archive.write_bytes(archive.read_bytes() + b"tamper")
    elif target == "save":
        save.write_bytes(save.read_bytes() + b" ")
    else:
        (installed / "index.html").write_bytes(b"tamper")
    assert run_app_cli(_cli(delivered)) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "blocked"
    assert error["release_certified"] is False


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
@pytest.mark.parametrize("target", ["archive", "save", "source"])
def test_symlink_substitution_is_rejected(delivered, tmp_path, target):
    installed, archive, save, *_ = delivered
    if target == "source":
        alias = tmp_path / "source-alias"
        alias.symlink_to(installed, target_is_directory=True)
        kwargs = {"installed_source": alias}
    else:
        original = archive if target == "archive" else save
        alias = tmp_path / ("archive-alias.zip" if target == "archive" else "save-alias.json")
        alias.symlink_to(original)
        kwargs = {"archive" if target == "archive" else "private_save": alias}
    with pytest.raises((ValueError, OSError)):
        _call(delivered, **kwargs)


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_cross_component_digest_mismatch_is_not_success(delivered, monkeypatch):
    import skeleton.app.offline_delivery_assurance as module
    original = module.reconcile_migrated_offline_progress

    def falsify(*args, **kwargs):
        result = original(*args, **kwargs)
        return {**result, "replay_digest": "0" * 64}

    monkeypatch.setattr(module, "reconcile_migrated_offline_progress", falsify)
    with pytest.raises(OfflineDeliveryAssuranceError):
        _call(delivered)


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_same_byte_archive_inode_swap_between_checks_is_rejected(
    delivered, tmp_path, monkeypatch,
):
    import skeleton.app.offline_delivery_assurance as module
    _, archive, *_ = delivered
    original = module.reconcile_migrated_offline_progress
    swapped = False

    def swap_after_cross_replay(*args, **kwargs):
        nonlocal swapped
        result = original(*args, **kwargs)
        replacement = tmp_path / "replacement.zip"
        replacement.write_bytes(archive.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, archive)
        swapped = True
        return result

    monkeypatch.setattr(module, "reconcile_migrated_offline_progress",
                        swap_after_cross_replay)
    with pytest.raises(OfflineDeliveryAssuranceError):
        _call(delivered)
    assert swapped


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_same_byte_save_inode_swap_between_checks_is_rejected(
    delivered, tmp_path, monkeypatch,
):
    import skeleton.app.offline_delivery_assurance as module
    _, _, save, *_ = delivered
    original = module.reconcile_migrated_offline_progress
    swapped = False

    def swap_after_cross_replay(*args, **kwargs):
        nonlocal swapped
        result = original(*args, **kwargs)
        replacement = tmp_path / "replacement.json"
        replacement.write_bytes(save.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, save)
        swapped = True
        return result

    monkeypatch.setattr(module, "reconcile_migrated_offline_progress",
                        swap_after_cross_replay)
    with pytest.raises(OfflineDeliveryAssuranceError):
        _call(delivered)
    assert swapped


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_cli_rejects_missing_operator_acknowledgement(delivered, capsys):
    command = _cli(delivered)
    command.remove("--trusted-local-operator")
    assert run_app_cli(command) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.skipif(os.name != "posix", reason="descriptor custody requires POSIX")
def test_cli_rejects_unsupported_extra_flags(delivered):
    with pytest.raises(SystemExit) as error:
        run_app_cli(_cli(delivered) + ["--release-certified"])
    assert error.value.code == 2
