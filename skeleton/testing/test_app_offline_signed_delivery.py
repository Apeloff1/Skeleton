"""End-to-end signed original source -> install -> playable private save."""
from __future__ import annotations

from hashlib import sha256
import json
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_archive_signature import source_archive_signature_message
from skeleton.app.offline_signed_delivery import (
    SignedOfflineDeliveryError, assure_signed_offline_delivery,
)
from skeleton.testing.test_app_offline_progress_migration import (
    _journey, _package, _save,
)


@pytest.fixture
def complete(tmp_path, capsys):
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
    private = Ed25519PrivateKey.generate()
    key_bytes = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key = tmp_path / "source-key.pub"
    key.write_bytes(key_bytes)
    key.chmod(0o600)
    signature = tmp_path / "source.sig"
    signature.write_bytes(private.sign(source_archive_signature_message(
        expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest,
    )))
    signature.chmod(0o600)
    return (
        installed, archive, save, key, signature, manifest, archive_pin,
        save_pin, sha256(key_bytes).hexdigest(), replay,
    )


def _call(bundle, **overrides):
    installed, archive, save, key, signature, manifest, archive_pin, save_pin, key_pin, _ = bundle
    args = {
        "installed_source": installed, "archive": archive,
        "private_save": save, "public_key_file": key,
        "signature_file": signature,
        "expected_manifest_sha256": manifest,
        "expected_archive_sha256": archive_pin,
        "expected_save_sha256": save_pin,
        "expected_public_key_sha256": key_pin,
        "authorized": True,
    }
    args.update(overrides)
    return assure_signed_offline_delivery(**args)


def _cli(bundle):
    installed, archive, save, key, signature, manifest, archive_pin, save_pin, key_pin, _ = bundle
    return [
        "signed-delivery-assurance",
        "--installed", str(installed), "--archive", str(archive),
        "--save", str(save), "--public-key", str(key),
        "--signature", str(signature),
        "--expected-manifest-sha256", manifest,
        "--expected-archive-sha256", archive_pin,
        "--expected-save-sha256", save_pin,
        "--expected-public-key-sha256", key_pin,
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_real_signed_delivery_and_replay_is_still_release_blocked(
    complete, capsys,
):
    installed, archive, save, key, signature, *_, replay = complete
    before = (
        (installed / "release.json").read_bytes(),
        archive.read_bytes(), save.read_bytes(),
        key.read_bytes(), signature.read_bytes(),
    )
    assert run_app_cli(_cli(complete)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["replay_digest"] == replay
    assert result["source_archive_signature_verified"] is True
    assert result["installed_source_archive_binding_verified"] is True
    assert result["private_save_world_binding_verified"] is True
    assert result["offline_gameplay_reexecuted"] is True
    assert result["native_executable_package_signed"] is False
    assert result["native_device_qualified"] is False
    assert result["publisher_identity_certified"] is False
    assert result["rights_certified"] is False
    assert result["release_certified"] is False
    assert before == (
        (installed / "release.json").read_bytes(),
        archive.read_bytes(), save.read_bytes(),
        key.read_bytes(), signature.read_bytes(),
    )


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("target", ["signature", "archive", "save"])
def test_tampering_blocks_combined_handoff(complete, capsys, target):
    path = {"signature": complete[4], "archive": complete[1],
            "save": complete[2]}[target]
    raw = path.read_bytes()
    path.write_bytes(bytes((raw[0] ^ 1,)) + raw[1:])
    assert run_app_cli(_cli(complete)) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_authority_is_required_before_any_custody_access(complete, monkeypatch):
    import skeleton.app.offline_signed_delivery as module

    def unexpected(*args, **kwargs):
        raise AssertionError("unauthorized custody read")

    monkeypatch.setattr(module, "_identities", unexpected)
    with pytest.raises(PermissionError):
        _call(complete, authorized=False)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_replaced_signature_inode_between_gates_is_rejected(
    complete, tmp_path, monkeypatch,
):
    import skeleton.app.offline_signed_delivery as module
    original = module.assure_offline_delivery
    signature = complete[4]

    def replace_during_replay(*args, **kwargs):
        result = original(*args, **kwargs)
        replacement = tmp_path / "replacement.sig"
        replacement.write_bytes(signature.read_bytes())
        replacement.chmod(0o600)
        os.replace(replacement, signature)
        return result

    monkeypatch.setattr(module, "assure_offline_delivery",
                        replace_during_replay)
    with pytest.raises(SignedOfflineDeliveryError):
        _call(complete)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_wrong_public_key_pin_is_rejected(complete):
    with pytest.raises(ValueError):
        _call(complete, expected_public_key_sha256="0" * 64)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_unacknowledged_cli_handoff_fails_closed(complete, capsys):
    command = _cli(complete)
    command.remove("--trusted-local-operator")
    assert run_app_cli(command) == 2
    assert json.loads(capsys.readouterr().err)["release_certified"] is False

@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("pin", ["archive", "manifest", "save", "public_key"])
def test_malformed_trust_pin_rejected_before_any_custody_read(
    complete, monkeypatch, pin,
):
    import skeleton.app.offline_signed_delivery as module

    def unexpected(*args, **kwargs):
        raise AssertionError("file read before external pin validation")

    monkeypatch.setattr(module, "_identities", unexpected)
    with pytest.raises(ValueError):
        _call(complete, **{"expected_" + pin + "_sha256": "not-a-pin"})
