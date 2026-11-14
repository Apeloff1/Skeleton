"""Fail-closed portable artifact packaging and exact staged-byte ownership.

Source-only adversarial tests; no Android SDK and no live network required.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from services import binary_builder as binary
from core.vault_secure_fs import VaultPathError


@pytest.mark.parametrize("bad", [
    "con", "CON.txt", "aux", "assets/COM1.dll",
    "x/LPT9", "assets/name. ", "x/trailing.", "x/trailing ",
    "MANIFEST.JSON", "manifest.json",
])
def test_portable_names_reject_windows_device_and_reserved_aliases(bad):
    with pytest.raises(ValueError):
        binary._sanitize_path(bad)


def test_utf8_budget_rejects_unpaired_surrogate_without_replacement():
    with pytest.raises(ValueError):
        binary._bounded_asset_bytes("broken-\ud800")
    assert binary._bounded_asset_bytes("é") == "é".encode("utf-8")


def test_both_byte_cap_names_remain_enforced(monkeypatch):
    monkeypatch.setattr(binary, "_MAX_ASSET_BYTES", 100)
    monkeypatch.setattr(binary, "_MAX_PACKAGE_FILE_BYTES", 4)
    with pytest.raises(ValueError, match="byte budget"):
        binary._bounded_asset_bytes("12345")
    monkeypatch.setattr(binary, "_MAX_ASSET_BYTES", 3)
    monkeypatch.setattr(binary, "_MAX_PACKAGE_FILE_BYTES", 100)
    with pytest.raises(ValueError, match="byte budget"):
        binary._bounded_asset_bytes("1234")


@pytest.fixture
def published(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(binary, "ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(binary, "_ensure_artifacts_root", lambda: tmp_path)
    monkeypatch.setattr(binary, "require_execution_allowed", lambda *_: True)
    return tmp_path


def test_archive_rejects_case_insensitive_collision_without_replacing_prior_bytes(published):
    existing = published / "game.zip"
    existing.write_bytes(b"valid-prior-publish")
    with pytest.raises(ValueError, match="duplicate"):
        binary.build_zip({
            "build_id": "game",
            "files": {"assets/Sprite.PNG": "one", "assets/sprite.png": "two"},
        })
    assert existing.read_bytes() == b"valid-prior-publish"


def test_original_aggregate_cap_cannot_be_widened_by_new_alias(published, monkeypatch):
    monkeypatch.setattr(binary, "_MAX_PACKAGE_RAW_BYTES", 5)
    monkeypatch.setattr(binary, "_MAX_SOURCE_BYTES", 100)
    with pytest.raises(ValueError, match="total"):
        binary.build_zip({"build_id": "small", "files": {"x.txt": "123456"}})
    assert not (published / "small.zip").exists()


@pytest.mark.parametrize("tamper", ["wrong-digest", "foreign-path"])
def test_untrusted_apk_staging_metadata_never_replaces_existing_publish(
    published, monkeypatch, tamper,
):
    old = published / "safe.apk"
    old.write_bytes(b"prior-complete-artifact")

    def fake_stage(_build, output: Path):
        body = b"candidate-complete-artifact"
        output.write_bytes(body)
        if tamper == "wrong-digest":
            return {
                "kind": "apk", "path": str(output), "size_bytes": len(body),
                "sha256": hashlib.sha256(b"wrong").hexdigest(),
            }
        return {
            "kind": "apk", "path": str(output.parent / "../foreign.apk"),
            "size_bytes": len(body),
        }

    monkeypatch.setattr(binary, "_build_apk_staged", fake_stage)
    with pytest.raises((ValueError, VaultPathError)):
        binary.build_apk({"build_id": "safe"})
    assert old.read_bytes() == b"prior-complete-artifact"
