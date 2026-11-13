"""Adversarial storage regression coverage for CodeQL alert root causes.

Tests use disposable directories only and never require live storage, a real
MongoDB instance, a GitHub token, or a network connection.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from gameforge.enterprise.compliance import _seal_compliance_export
from services import binary_builder


def test_encrypted_tenant_pack_has_no_plaintext_or_repeatable_nonce(monkeypatch):
    key = os.urandom(32)
    monkeypatch.setenv("GAMEFORGE_COMPLIANCE_EXPORT_KEY_B64", base64.b64encode(key).decode())
    tenant = "1" * 24
    secret = b'{"audit":{"api_key":"extremely-sensitive-canary"}}'
    first = _seal_compliance_export(secret, tenant)
    second = _seal_compliance_export(secret, tenant)
    assert first != second
    assert b"extremely-sensitive-canary" not in first
    assert b"extremely-sensitive-canary" not in second
    envelope = json.loads(first)
    assert envelope["format"] == "gameforge-compliance-aes256gcm-v1"
    assert envelope["tenant_sha256_prefix"] == tenant
    nonce = base64.b64decode(envelope["nonce_b64"], validate=True)
    ciphertext = base64.b64decode(envelope["ciphertext_b64"], validate=True)
    restored = AESGCM(key).decrypt(
        nonce, ciphertext, ("gameforge-compliance-v1:" + tenant).encode("ascii")
    )
    assert restored == secret
    with pytest.raises(Exception):
        AESGCM(key).decrypt(nonce, ciphertext, b"gameforge-compliance-v1:" + b"2" * 24)


@pytest.mark.parametrize("key", ["", "not-base64*", base64.b64encode(b"short").decode()])
def test_compliance_pack_fails_closed_without_valid_key(monkeypatch, key):
    monkeypatch.setenv("GAMEFORGE_COMPLIANCE_EXPORT_KEY_B64", key)
    with pytest.raises(ValueError):
        _seal_compliance_export(b"private", "f" * 24)


def test_compliance_pack_denies_oversized_plaintext(monkeypatch):
    monkeypatch.setenv(
        "GAMEFORGE_COMPLIANCE_EXPORT_KEY_B64", base64.b64encode(os.urandom(32)).decode()
    )
    with pytest.raises(ValueError, match="byte budget"):
        _seal_compliance_export(b"x" * (48 * 1024 * 1024 + 1), "f" * 24)


@pytest.mark.parametrize("bad", ["", ".", "..", "../steal", "a/b", "a\\b", "ö", "a" * 129])
def test_artifact_download_refuses_noncanonical_id(bad):
    assert binary_builder.open_artifact_for_download(bad, "zip") is None


def test_artifact_download_reads_private_regular_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(binary_builder, "ARTIFACTS_ROOT", tmp_path)
    (tmp_path / "safe.zip").write_bytes(b"trusted-data")
    with binary_builder.open_artifact_for_download("safe", "zip") as stream:
        assert stream.read() == b"trusted-data"
    assert binary_builder.open_artifact_for_download("safe", "exe") is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX openat path custody")
def test_artifact_download_rejects_symlink_and_hardlink(monkeypatch, tmp_path: Path):
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"private-data")
    (root / "evil.zip").symlink_to(outside)
    os.link(outside, root / "alias.zip")
    monkeypatch.setattr(binary_builder, "ARTIFACTS_ROOT", root)
    assert binary_builder.open_artifact_for_download("evil", "zip") is None
    assert binary_builder.open_artifact_for_download("alias", "zip") is None


@pytest.mark.skipif(os.name != "posix", reason="POSIX openat path custody")
def test_artifact_descriptor_stays_on_original_after_leaf_swap(monkeypatch, tmp_path: Path):
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "safe.apk").write_bytes(b"approved-content")
    monkeypatch.setattr(binary_builder, "ARTIFACTS_ROOT", root)
    opened = binary_builder.open_artifact_for_download("safe", "apk")
    assert opened is not None
    (root / "safe.apk").rename(root / "old.apk")
    (root / "safe.apk").write_bytes(b"attacker-content")
    with opened:
        assert opened.read() == b"approved-content"


@pytest.mark.skipif(os.name != "posix", reason="POSIX openat path custody")
def test_artifact_download_denies_symlinked_root(monkeypatch, tmp_path: Path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "safe.zip").write_bytes(b"secret")
    link = tmp_path / "alias"
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(binary_builder, "ARTIFACTS_ROOT", link)
    assert binary_builder.open_artifact_for_download("safe", "zip") is None
