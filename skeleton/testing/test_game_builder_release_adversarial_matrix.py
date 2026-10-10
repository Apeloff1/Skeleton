"""Adversarial file-system and receipt parsing tests for original game release.

All payloads are synthetic. They ensure copied/commercial content cannot be
smuggled alongside hash-checked generated homebrew without explicit review.
"""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import stat

import pytest

from skeleton.ai.game_builder.native_release_intake import (
    NativeIntakeError, _json, _read_bounded, verify_native_release_intake,
)
from skeleton.testing.test_game_builder_native_release_intake import _setup


@pytest.mark.parametrize("extra",[
    "rom.bin", "commercial_game.exe", "game_original.sav", ".env", ".gitignore",
    ".git", "CMakeCache.txt", "assets", "patch.ips", "override.dll",
    "startup.sh", "installer.exe", "external_license.key", "__pycache__",
    "EXTRA_IMAGE.JPG", "hidden_sound.wav", "game.c.bak", "alternate_story.txt",
])
def test_unreviewed_root_payload_rejected_even_if_ten_expected_hashes_match(tmp_path, extra):
    args = _setup(tmp_path)
    target = args["source_directory"] / extra
    if "." not in extra or extra == ".git":
        target.mkdir()
    else:
        target.write_bytes(b"unreviewed proprietary asset candidate")
    with pytest.raises(NativeIntakeError,match="unreviewed extra"):
        verify_native_release_intake(**args)


@pytest.mark.parametrize("extra",[
    "other-license.txt", ".extra", "keyfile.key", "rom.bin",
    "assets.json", "hidden.json", "notices.old", "soundtrack.wav",
])
def test_unreviewed_rights_extra_rejected_even_with_correct_credits(tmp_path, extra):
    args = _setup(tmp_path)
    (args["source_directory"] / "rights" / extra).write_bytes(b"unreviewed")
    with pytest.raises(NativeIntakeError,match="unreviewed extra"):
        verify_native_release_intake(**args)


def test_missing_optional_root_entries_is_not_treated_as_empty_success(tmp_path):
    args = _setup(tmp_path)
    (args["source_directory"] / "legal_review.json").unlink()
    with pytest.raises(NativeIntakeError,match="unreviewed extra"):
        verify_native_release_intake(**args)


@pytest.mark.parametrize("filename",[
    "game.c", "CMakeLists.txt", "manifest.json", "legal_review.json",
])
def test_hardlinked_source_file_cannot_import_unreviewed_external_inode(tmp_path,filename):
    args = _setup(tmp_path)
    source = args["source_directory"] / filename
    os.link(source,tmp_path / (filename + ".other-copy"))
    with pytest.raises(NativeIntakeError,match="private bounded"):
        verify_native_release_intake(**args)


@pytest.mark.parametrize("field",["compiled_binary","build_evidence","gameplay_evidence"])
def test_hardlinked_external_native_evidence_cannot_bypass_single_file_attestation(tmp_path,field):
    args = _setup(tmp_path)
    source = args[field]
    os.link(source,tmp_path / (field+".hardlink"))
    with pytest.raises(NativeIntakeError,match="private bounded"):
        verify_native_release_intake(**args)


def test_fifo_evidence_refused_without_blocking_native_release(tmp_path):
    if not hasattr(os,"mkfifo"):
        pytest.skip("POSIX named pipes required")
    args=_setup(tmp_path)
    fifo=tmp_path/"no-producer-fifo"
    os.mkfifo(fifo)
    args["compiled_binary"]=fifo
    with pytest.raises(NativeIntakeError,match="private bounded"):
        verify_native_release_intake(**args)


def test_missing_reviewed_rights_is_refused_if_rights_directory_is_symlink(tmp_path):
    args = _setup(tmp_path)
    rights = args["source_directory"] / "rights"
    original = tmp_path/"actual-rights"
    rights.rename(original)
    rights.symlink_to(original,target_is_directory=True)
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**args)


def test_directory_replacing_regular_binary_cannot_block_file_open_indefinitely(tmp_path):
    args=_setup(tmp_path)
    path=args["compiled_binary"]
    path.unlink()
    path.mkdir()
    with pytest.raises(NativeIntakeError):
        verify_native_release_intake(**args)


@pytest.mark.parametrize("invalid",[
    b'{"rights":true,"rights":false}',b'{"nested":{"legal":true,"legal":false}}',
    b'{"value":NaN}',b'{"value":Infinity}',b'{"value":-Infinity}',
    b'{"value":1e1000000}',b'{"value":1e9999}',b'[]',b'null',
    b'"string"',b'{"open":',b'not-json',b'\xff\xfe',
])
def test_ambiguous_malformed_or_nonfinite_native_legal_json_fails_closed(invalid):
    with pytest.raises(NativeIntakeError):
        _json(invalid,"legal rights")


def test_valid_duplicate_free_json_is_decoded_without_modifying_content():
    assert _json(b'{"schema":"original-homebrew","nested":{"x":1}}',"legal") == {
        "schema":"original-homebrew","nested":{"x":1},
    }


def test_mid_read_evidence_change_is_detected_by_descriptor_stat(tmp_path,monkeypatch):
    input_file=tmp_path/"build-proof.json"
    input_file.write_bytes(b'{"data":"' + b"x"*512 + b'"}')
    original_read=os.read
    bumped=[False]

    def mutate_after_first_read(fd,length):
        content=original_read(fd,length)
        if not bumped[0]:
            bumped[0]=True
            before=input_file.stat()
            os.utime(input_file,ns=(before.st_atime_ns,before.st_mtime_ns+2_000_000_000))
        return content

    monkeypatch.setattr(os,"read",mutate_after_first_read)
    with pytest.raises(NativeIntakeError,match="changed while being read"):
        _read_bounded(input_file,max_bytes=4096)
    assert bumped[0]


@pytest.mark.parametrize("n", [0, 1, 512, 512*1024])
def test_oversized_bounded_io_is_rejected_without_unbounded_read(tmp_path,n):
    file=tmp_path/"huge-rights.txt"
    file.write_bytes(b"A"*n)
    if n==0 or n>256:
        with pytest.raises(NativeIntakeError):
            _read_bounded(file,max_bytes=256)
    else:
        assert _read_bounded(file,max_bytes=256)==b"A"*n


def test_no_follow_path_refuses_symlinks_to_device_or_untracked_external_dir(tmp_path):
    from skeleton.ai.game_builder.native_release_intake import _open_directory
    actual=tmp_path/"actual"
    actual.mkdir()
    external=tmp_path/"link"
    external.symlink_to(actual,target_is_directory=True)
    with pytest.raises(NativeIntakeError):
        _open_directory(external)


def test_release_bytes_cannot_claim_strong_executable_structure_validation(tmp_path):
    result=verify_native_release_intake(**_setup(tmp_path))
    assert result.executable_structure_validated is False
    assert result.exhaustive_payload_inventory_verified is True
    with pytest.raises(NativeIntakeError):
        replace(result,executable_structure_validated=True)
    with pytest.raises(NativeIntakeError):
        replace(result,exhaustive_payload_inventory_verified=False)
    with pytest.raises(NativeIntakeError):
        replace(result,byte_verified_files=("compiled_binary",))
