"""Local Godot ZIP/executable custody validation without real engine or network."""
from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from pathlib import Path

import pytest

from scripts.qualify_gameforge_godot_native import verify_engine_archive


def _archive(path: Path, members: dict[str, bytes]) -> str:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name, value in members.items():
            out.writestr(name, value)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pinned_zip_must_contain_exact_executable_bytes(tmp_path):
    exe = tmp_path / "godot"
    exe.write_bytes(b"original godot test executable bytes")
    dist = tmp_path / "godot-release.zip"
    digest = _archive(dist, {
        "Godot_v4.3-stable_linux.x86_64": exe.read_bytes(),
        "README.txt": b"Test-only metadata",
    })
    evidence = verify_engine_archive(exe, dist, digest)
    assert evidence["archive_sha256"] == digest
    assert evidence["godot_binary_sha256"] == hashlib.sha256(exe.read_bytes()).hexdigest()
    assert evidence["archive_member"] == "Godot_v4.3-stable_linux.x86_64"
    assert evidence["binary_matches_archive"] == "true"


def test_digest_shape_is_not_sufficient_provenance(tmp_path):
    exe = tmp_path / "godot"
    exe.write_bytes(b"release A")
    dist = tmp_path / "godot-release.zip"
    digest = _archive(dist, {"Godot_v4.3-stable_linux.x86_64": b"release B"})
    with pytest.raises(ValueError, match="does not match exactly one"):
        verify_engine_archive(exe, dist, digest)
    with pytest.raises(ValueError, match="does not match expected"):
        verify_engine_archive(exe, dist, "a" * 64)
    with pytest.raises(ValueError, match="lowercase trusted digest"):
        verify_engine_archive(exe, dist, digest.upper())


@pytest.mark.parametrize("member", [
    "../escape/Godot", "/absolute/Godot", "a\\Godot",
])
def test_unsafe_archive_names_are_rejected(tmp_path, member):
    exe = tmp_path / "godot"
    exe.write_bytes(b"safe binary")
    dist = tmp_path / "godot-release.zip"
    digest = _archive(dist, {member: exe.read_bytes()})
    with pytest.raises(ValueError, match="unsafe or duplicate"):
        verify_engine_archive(exe, dist, digest)


def test_duplicate_case_insensitive_archive_paths_are_rejected(tmp_path):
    exe = tmp_path / "godot"
    exe.write_bytes(b"test binary")
    dist = tmp_path / "godot-release.zip"
    digest = _archive(dist, {
        "Godot_Binary": exe.read_bytes(),
        "godot_binary": exe.read_bytes(),
    })
    with pytest.raises(ValueError, match="unsafe or duplicate"):
        verify_engine_archive(exe, dist, digest)


def test_symlink_archive_entries_fail_closed(tmp_path):
    exe = tmp_path / "godot"
    exe.write_bytes(b"test binary")
    dist = tmp_path / "godot-release.zip"
    item = zipfile.ZipInfo("Godot_test")
    item.create_system = 3
    item.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(dist, "w") as out:
        out.writestr(item, b"link_target")
    digest = hashlib.sha256(dist.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="symbolic link"):
        verify_engine_archive(exe, dist, digest)


@pytest.mark.parametrize("invalid", [
    "3.5.stable.official.aaaa", "4.3", "Godot 4.3", "", "4.3.stable.official.x\nSCRIPT ERROR",
    "4.3.stable.official.x\r", "5.0.stable.official.abc",
    " 4.3.stable.official.x", "4.3.stable.official.x ",
    "4.3.stable.official.x\n\n", "4.3.stable.official.x\x00",
    "4.3.stable.official.x\r\nnoise",
])
def test_only_explicit_single_line_godot_four_versions_are_admitted(invalid):
    from scripts.qualify_gameforge_godot_native import parse_godot_major_four
    with pytest.raises(ValueError):
        parse_godot_major_four(invalid)


@pytest.mark.parametrize("valid", [
    "4.3.stable.official.77dcf97d8",
    "4.4.1.stable.official.aabbccdd",
    "4.6.stable.official.aabbccdd",
])
def test_actual_godot_four_version_shapes(valid):
    from scripts.qualify_gameforge_godot_native import parse_godot_major_four
    assert parse_godot_major_four(valid) == valid
    assert parse_godot_major_four(valid + "\n") == valid
    assert parse_godot_major_four(valid + "\r\n") == valid


def test_noncanonical_zip_alias_is_not_accepted_as_official_distribution(tmp_path):
    exe = tmp_path / "godot"
    exe.write_bytes(b"safe engine")
    dist = tmp_path / "godot-release.zip"
    digest = _archive(dist, {"pkg//Godot_4": exe.read_bytes()})
    with pytest.raises(ValueError, match="unsafe or duplicate"):
        verify_engine_archive(exe, dist, digest)


def test_version_probe_preserves_raw_control_and_rejects_truncated_record(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from scripts import qualify_gameforge_godot_native as qualification
    def launch(stdout):
        monkeypatch.setattr(qualification.subprocess, "run", lambda *args, **kwargs:
            SimpleNamespace(stdout=stdout, stderr=b"", returncode=0))
        return qualification._launch(tmp_path / "godot", ["--version"], tmp_path, timeout=1)
    record = launch(b"4.3.stable.official.x\r")
    assert record["version_stdout"] == "4.3.stable.official.x\r"
    with pytest.raises(ValueError):
        qualification.parse_godot_major_four(record["version_stdout"])
    assert launch(b"4.3.stable.official.x" + b"a" * 500)["version_stdout"] is None
