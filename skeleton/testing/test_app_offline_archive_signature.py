"""Actual detached Ed25519 source archive verification, never release certification."""
from __future__ import annotations

from hashlib import sha256
import json
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_archive_signature import (
    OfflineArchiveSignatureError, source_archive_signature_message,
    verify_offline_source_archive_signature,
)
from skeleton.testing.test_app_offline_archive_install import _archive


@pytest.fixture
def signed(tmp_path, capsys):
    _, archive, archive_pin, manifest_pin = _archive(tmp_path, capsys)
    private = Ed25519PrivateKey.generate()  # Ephemeral test key; never published.
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_file = tmp_path / "trusted-key.pub"
    key_file.write_bytes(public)
    key_file.chmod(0o600)
    message = source_archive_signature_message(
        expected_archive_sha256=archive_pin,
        expected_manifest_sha256=manifest_pin,
    )
    signature_file = tmp_path / "detached.sig"
    signature_file.write_bytes(private.sign(message))
    signature_file.chmod(0o600)
    return archive, archive_pin, manifest_pin, key_file, signature_file, sha256(public).hexdigest()


def _call(bundle, **overrides):
    archive, archive_pin, manifest_pin, key, signature, key_pin = bundle
    args = {
        "archive": archive, "public_key_file": key,
        "signature_file": signature,
        "expected_archive_sha256": archive_pin,
        "expected_manifest_sha256": manifest_pin,
        "expected_public_key_sha256": key_pin, "authorized": True,
    }
    args.update(overrides)
    return verify_offline_source_archive_signature(**args)


def _cli(bundle):
    archive, archive_pin, manifest_pin, key, signature, key_pin = bundle
    return [
        "verify-archive-signature", "--archive", str(archive),
        "--public-key", str(key), "--signature", str(signature),
        "--expected-archive-sha256", archive_pin,
        "--expected-manifest-sha256", manifest_pin,
        "--expected-public-key-sha256", key_pin,
        "--trusted-local-operator",
    ]


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_valid_detached_signature_is_not_consumer_release(signed, capsys):
    archive, _, _, key, signature, _ = signed
    before = archive.read_bytes(), key.read_bytes(), signature.read_bytes()
    assert run_app_cli(_cli(signed)) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source_archive_integrity_verified"] is True
    assert receipt["source_archive_signature_verified"] is True
    assert receipt["signature_algorithm"] == "Ed25519"
    assert receipt["private_signing_key_loaded"] is False
    assert receipt["native_executable_package_signed"] is False
    assert receipt["native_device_qualified"] is False
    assert receipt["publisher_identity_certified"] is False
    assert receipt["rights_certified"] is False
    assert receipt["package_signed"] is False
    assert receipt["release_certified"] is False
    assert (archive.read_bytes(), key.read_bytes(), signature.read_bytes()) == before


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("pin", ["archive", "manifest", "public_key"])
def test_wrong_independent_pin_rejected(signed, pin):
    with pytest.raises(ValueError):
        _call(signed, **{"expected_" + pin + "_sha256": "0" * 64})


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("target", ["archive", "signature", "key"])
def test_mutated_archive_signature_or_key_rejected(signed, target, capsys):
    archive, _, _, key, signature, _ = signed
    path = {"archive": archive, "signature": signature, "key": key}[target]
    raw = path.read_bytes()
    path.write_bytes(bytes((raw[0] ^ 1,)) + raw[1:])
    assert run_app_cli(_cli(signed)) == 2
    receipt = json.loads(capsys.readouterr().err)
    assert receipt["status"] == "blocked"
    assert receipt["release_certified"] is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("target", ["signature", "key"])
def test_symlinked_detached_material_is_rejected(signed, tmp_path, target):
    _, _, _, key, signature, _ = signed
    original = key if target == "key" else signature
    alias = tmp_path / ("alias.pub" if target == "key" else "alias.sig")
    alias.symlink_to(original)
    kwargs = {"public_key_file" if target == "key" else "signature_file": alias}
    with pytest.raises((ValueError, OSError)):
        _call(signed, **kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_wrong_signing_key_is_not_accepted(signed, tmp_path):
    key = tmp_path / "unrelated.pub"
    public = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key.write_bytes(public)
    key.chmod(0o600)
    with pytest.raises(OfflineArchiveSignatureError):
        _call(signed, public_key_file=key,
              expected_public_key_sha256=sha256(public).hexdigest())


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("target", ["signature", "key"])
def test_same_bytes_inode_swap_during_signature_verification_is_rejected(
    signed, tmp_path, monkeypatch, target,
):
    import skeleton.app.offline_archive_signature as module
    _, _, _, key, signature, _ = signed
    path = key if target == "key" else signature
    original = module.inspect_offline_game_archive
    calls = 0

    def replace_on_second_inspection(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            replacement = tmp_path / ("replacement.pub" if target == "key" else "replacement.sig")
            replacement.write_bytes(path.read_bytes())
            replacement.chmod(0o600)
            os.replace(replacement, path)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "inspect_offline_game_archive",
                        replace_on_second_inspection)
    with pytest.raises(OfflineArchiveSignatureError):
        _call(signed)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_authority_checked_before_material_access(signed, monkeypatch):
    import skeleton.app.offline_archive_signature as module

    def unexpected(*args, **kwargs):
        raise AssertionError("read without operator acknowledgement")

    monkeypatch.setattr(module, "_archive_identity", unexpected)
    with pytest.raises(PermissionError):
        _call(signed, authorized=False)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_oversized_signature_rejected(signed):
    signature = signed[4]
    signature.write_bytes(signature.read_bytes() + b"extra")
    with pytest.raises(OfflineArchiveSignatureError):
        _call(signed)


def test_signature_message_is_domain_separated_and_deterministic():
    a = source_archive_signature_message(
        expected_archive_sha256="a" * 64,
        expected_manifest_sha256="b" * 64,
    )
    b = source_archive_signature_message(
        expected_archive_sha256="a" * 64,
        expected_manifest_sha256="b" * 64,
    )
    c = source_archive_signature_message(
        expected_archive_sha256="b" * 64,
        expected_manifest_sha256="a" * 64,
    )
    assert a == b
    assert a != c
    assert a.startswith(b"Skeleton offline original source archive signature v1\x00")


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_cli_rejects_unacknowledged_verification(signed, capsys):
    command = _cli(signed)
    command.remove("--trusted-local-operator")
    assert run_app_cli(command) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"

@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
@pytest.mark.parametrize("kind", ["key", "signature"])
def test_detached_material_must_have_correct_bounded_extension(signed, tmp_path, kind):
    _, _, _, key, signature, _ = signed
    original = key if kind == "key" else signature
    wrong = tmp_path / ("key.json" if kind == "key" else "signature.json")
    wrong.write_bytes(original.read_bytes())
    wrong.chmod(0o600)
    kwargs = {"public_key_file" if kind == "key" else "signature_file": wrong}
    with pytest.raises(OfflineArchiveSignatureError):
        _call(signed, **kwargs)


@pytest.mark.skipif(os.name != "posix", reason="POSIX descriptor custody")
def test_world_writable_detached_material_is_rejected(signed):
    key = signed[3]
    key.chmod(0o666)
    with pytest.raises(OfflineArchiveSignatureError):
        _call(signed)
