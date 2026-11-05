"""External-signing bridge: verified ZIP -> exact message -> real Ed25519 check."""
from __future__ import annotations

from hashlib import sha256
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_source_signing_request import (
    OfflineSourceSigningRequestError, prepare_offline_source_signing_request,
)
from skeleton.app.offline_archive_signature import source_archive_signature_message
from skeleton.testing.test_app_offline_archive_signature import signed


def _call(bundle, **changes):
    archive, archive_pin, manifest_pin, _, _, _ = bundle
    kwargs = {
        "archive": archive,
        "expected_archive_sha256": archive_pin,
        "expected_manifest_sha256": manifest_pin,
        "authorized": True,
    }
    kwargs.update(changes)
    return prepare_offline_source_signing_request(**kwargs)


def _cli(bundle):
    return [
        "source-signing-request",
        "--archive", str(bundle[0]),
        "--expected-archive-sha256", bundle[1],
        "--expected-manifest-sha256", bundle[2],
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_real_signing_request_matches_detached_ed25519_signature(signed, capsys):
    archive, archive_pin, manifest_pin, key, signature, _ = signed
    before = archive.read_bytes()
    assert run_app_cli(_cli(signed)) == 0
    receipt = json.loads(capsys.readouterr().out)
    message = bytes.fromhex(receipt["signature_message_hex"])
    expected = source_archive_signature_message(
        expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin,
    )
    assert message == expected
    assert receipt["signature_message_sha256"] == sha256(message).hexdigest()
    Ed25519PublicKey.from_public_bytes(key.read_bytes()).verify(
        signature.read_bytes(), message,
    )
    assert receipt["source_archive_integrity_verified"] is True
    assert receipt["signature_issued"] is False
    assert receipt["private_signing_key_loaded"] is False
    assert receipt["package_signed"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["release_certified"] is False
    assert receipt["read_only"] is True
    assert archive.read_bytes() == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("pin", ["expected_archive_sha256", "expected_manifest_sha256"])
def test_independent_pins_required_before_signing_request(signed, pin):
    with pytest.raises(ValueError):
        _call(signed, **{pin: "0" * 64})


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_archive_tamper_rejected(signed):
    archive = signed[0]
    archive.write_bytes(archive.read_bytes() + b"tamper")
    with pytest.raises(ValueError):
        _call(signed)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_same_byte_archive_inode_replacement_during_inspection_rejected(
    signed, tmp_path, monkeypatch,
):
    import skeleton.app.offline_source_signing_request as module

    archive = signed[0]
    original = module.inspect_offline_game_archive
    calls = 0

    def swap_on_second_inspection(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            replacement = tmp_path / "same-byte-archive.zip"
            replacement.write_bytes(archive.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, archive)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "inspect_offline_game_archive",
                        swap_on_second_inspection)
    with pytest.raises(OfflineSourceSigningRequestError):
        _call(signed)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_operator_authorization_before_archive_access(signed, monkeypatch):
    import skeleton.app.offline_source_signing_request as module

    def unexpected(*args, **kwargs):
        raise AssertionError("unauthorized read")

    monkeypatch.setattr(module, "_archive_identity", unexpected)
    with pytest.raises(PermissionError):
        _call(signed, authorized=False)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_denies_unsigned_authority(signed, capsys):
    args = _cli(signed)
    args.remove("--trusted-local-operator")
    assert run_app_cli(args) == 2
    receipt = json.loads(capsys.readouterr().err)
    assert receipt["status"] == "blocked"
    assert receipt["release_certified"] is False
