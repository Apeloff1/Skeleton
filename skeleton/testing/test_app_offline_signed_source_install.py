"""Real detached signature -> no-clobber source install -> gameplay verification."""
from __future__ import annotations

import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_signed_source_install import (
    SignedOfflineSourceInstallError, install_signed_offline_game_source,
)
from skeleton.testing.test_app_offline_archive_signature import signed


@pytest.fixture
def package(signed, tmp_path):
    archive, archive_pin, manifest_pin, key, signature, key_pin = signed
    target = tmp_path / "signed-installed-game"
    return archive, archive_pin, manifest_pin, key, signature, key_pin, target


def _call(bundle, **overrides):
    archive, archive_pin, manifest_pin, key, signature, key_pin, target = bundle
    args = {
        "archive": archive, "destination": target,
        "public_key_file": key, "signature_file": signature,
        "expected_archive_sha256": archive_pin,
        "expected_manifest_sha256": manifest_pin,
        "expected_public_key_sha256": key_pin,
        "authorized": True,
    }
    args.update(overrides)
    return install_signed_offline_game_source(**args)


def _cli(bundle):
    archive, archive_pin, manifest_pin, key, signature, key_pin, target = bundle
    return [
        "install-signed-source", "--archive", str(archive),
        "--destination", str(target), "--public-key", str(key),
        "--signature", str(signature),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest_pin,
        "--expected-public-key-sha256", key_pin,
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_real_signed_source_install_and_playable_reconciliation(package, capsys):
    archive, archive_pin, manifest_pin, key, signature, _, target = package
    before = archive.read_bytes(), key.read_bytes(), signature.read_bytes()
    assert run_app_cli(_cli(package)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["installed_source_archive_binding_verified"] is True
    assert receipt["offline_gameplay_reexecuted"] is True
    assert receipt["fresh_destination_no_clobber"] is True
    assert receipt["automatic_rollback_performed"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["package_signed"] is False
    assert receipt["release_certified"] is False
    assert target.is_dir()
    assert (target / "release.json").is_file()
    assert run_app_cli([
        "studio-journey", "--play-existing", "--output", str(target),
        "--expected-manifest-sha256", manifest_pin,
        "--moves", "up,right", "--trusted-local-operator",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["offline_gameplay_reexecuted"] is True
    assert (archive.read_bytes(), key.read_bytes(), signature.read_bytes()) == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("target", ["signature", "archive", "key"])
def test_invalid_signature_inputs_never_reserve_installation(package, capsys, target):
    path = {"signature": package[4], "archive": package[0],
            "key": package[3]}[target]
    raw = path.read_bytes()
    path.write_bytes(bytes((raw[0] ^ 1,)) + raw[1:])
    assert run_app_cli(_cli(package)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert not package[6].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_occupied_destination_is_preserved(package):
    target = package[6]
    target.mkdir(mode=0o700)
    marker = target / "owner.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError):
        _call(package)
    assert marker.read_text(encoding="utf-8") == "preserve"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_invalid_public_key_pin_rejected_before_any_read(package, monkeypatch):
    import skeleton.app.offline_signed_source_install as module

    def unexpected(*args, **kwargs):
        raise AssertionError("read before pin validation")

    monkeypatch.setattr(module, "_signature_identities", unexpected)
    with pytest.raises(ValueError):
        _call(package, expected_public_key_sha256="not-a-pin")
    assert not package[6].exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_late_signature_swap_fails_closed_and_retains_new_install(
    package, tmp_path, monkeypatch,
):
    import skeleton.app.offline_signed_source_install as module
    original = module.install_offline_game_source
    signature = package[4]

    def replace_after_install(*args, **kwargs):
        receipt = original(*args, **kwargs)
        replacement = tmp_path / "replacement.sig"
        replacement.write_bytes(signature.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, signature)
        return receipt

    monkeypatch.setattr(module, "install_offline_game_source",
                        replace_after_install)
    with pytest.raises(SignedOfflineSourceInstallError):
        _call(package)
    assert package[6].is_dir()
    assert (package[6] / "release.json").is_file()


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_authority_required_before_any_custody_access(package, monkeypatch):
    import skeleton.app.offline_signed_source_install as module

    def unexpected(*args, **kwargs):
        raise AssertionError("unauthorized read")

    monkeypatch.setattr(module, "_signature_identities", unexpected)
    with pytest.raises(PermissionError):
        _call(package, authorized=False)
    assert not package[6].exists()
