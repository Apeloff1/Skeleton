"""ROM inventory, explicit rights and fail-closed batch learning regression tests.

No native core, third-party game, AI checkpoint, ROM download or model provider
is required for the no-authorization and source-identity cases.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from skeleton.ai.training.rom_study import (
    APPROVAL_SCHEMA, RomStudyError, _load_approvals, _stream_identity,
    inventory_page, train_page,
)


def _original(root: Path, name: str, content: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _rights(rom: Path, *, approved: bool = True) -> dict:
    content = rom.read_bytes()
    return {
        "sha256": sha256(content).hexdigest(),
        "content_size_bytes": len(content),
        "target_id": "game_boy", "core_id": "gambatte",
        "rights": {
            "rights_holder": "Original author",
            "rights_basis": "original:owned-game-source",
            "review_id": "verified-human-rights",
            "training_permitted": approved,
            "human_reviewed": approved,
        },
    }


def _approval_file(path: Path, records: list[dict]) -> Path:
    path.write_text(json.dumps({"schema_version": APPROVAL_SCHEMA, "roms": records}),
                    encoding="utf-8")
    return path


def test_inventory_hashes_files_without_running_an_emulator(tmp_path):
    roms = tmp_path / "roms"
    roms.mkdir()
    first = _original(roms, "homebrew.gb", b"x" * 32768)
    _original(roms, "sub/title.nes", b"y" * 32768)
    _original(roms, "not_a_rom.jpg", b"z")
    result = inventory_page(roms, limit=10)
    assert result["total_candidate_files"] == 2
    assert result["finished"] is True
    assert all(not row["authorized_for_training"] for row in result["rows"])
    assert all(not row["emulator_execution_checked"] for row in result["rows"])
    assert result["rows"][0]["file_sha256"] == sha256(first.read_bytes()).hexdigest()
    assert result["rom_bytes_exported"] is False


def test_cursor_always_moves_forward_and_resumes(tmp_path):
    roms = tmp_path / "roms"
    roms.mkdir()
    for name in ("zeta.gb", "alpha.gb", "deeper/mid.nes"):
        _original(roms, name, (name * 1024).encode())
    first = inventory_page(roms, limit=1)
    assert first["next_cursor"] is not None
    second = inventory_page(roms, cursor=first["next_cursor"], limit=1)
    third = inventory_page(roms, cursor=second["next_cursor"], limit=1)
    paths = [first["rows"][0]["relative_path"],
             second["rows"][0]["relative_path"],
             third["rows"][0]["relative_path"]]
    assert paths == sorted(set(paths))
    assert third["finished"] is True


def test_symlink_never_read_or_entered(tmp_path):
    roms = tmp_path / "roms"
    roms.mkdir()
    outside = tmp_path / "outside.gb"
    outside.write_bytes(b"private game data")
    (roms / "bad.gb").symlink_to(outside)
    (roms / "folder").symlink_to(tmp_path, target_is_directory=True)
    assert inventory_page(roms)["total_candidate_files"] == 0
    with pytest.raises(RomStudyError, match="symlink"):
        inventory_page(roms / "folder")


def test_rights_registry_blocks_unreviewed_and_duplicate_images(tmp_path):
    rom = _original(tmp_path, "homebrew.gb", b"licensed by author")
    rights_path = tmp_path / "rights.json"
    grant = _rights(rom, approved=False)
    _approval_file(rights_path, [grant])
    with pytest.raises(RomStudyError, match="unapproved"):
        _load_approvals(rights_path)
    grant = _rights(rom, approved=True)
    _approval_file(rights_path, [grant, grant])
    with pytest.raises(RomStudyError, match="duplicated"):
        _load_approvals(rights_path)
    _approval_file(rights_path, [grant])
    admitted, digest = _load_approvals(rights_path)
    assert grant["sha256"] in admitted
    assert len(digest) == 64


def test_hash_change_fails_closed(tmp_path):
    image = _original(tmp_path, "candidate.gb", b"x" * 32768)
    before, size, _ = _stream_identity(image)
    assert size == 32768
    image.write_bytes(b"y" * 32768)
    with pytest.raises(RomStudyError, match="differs"):
        _stream_identity(image, expected=before)


def test_absent_approvals_must_never_attempt_policy_training(tmp_path, monkeypatch):
    roms = tmp_path / "roms"
    roms.mkdir()
    _original(roms, "homebrew.gb", b"not a bootable cartridge")
    approvals = _approval_file(tmp_path / "rights.json", [])
    output = tmp_path / "receipts"
    output.mkdir(mode=0o700)
    from skeleton.jeeves import game_emulator_training_lab
    def prohibited(*args, **kwargs):
        raise AssertionError("Q trainer invoked without explicit rights")
    monkeypatch.setattr(game_emulator_training_lab, "run_emulator_training_lab", prohibited)
    result = train_page(roms, approvals, output, runs=1, steps=1)
    assert result["q_policy_training_completed"] == 0
    assert result["page_results"][0]["state"] == "no_training_rights_review"
    assert not list(output.iterdir())
    assert result["production_weights_modified"] is False


def test_missing_native_core_keeps_approved_rom_blocked(tmp_path, monkeypatch):
    roms = tmp_path / "roms"
    roms.mkdir()
    rom = _original(roms, "candidate.gb", b"original homebrew bytes")
    approvals = _approval_file(tmp_path / "rights.json", [_rights(rom)])
    receipts = tmp_path / "receipts"
    receipts.mkdir(mode=0o700)
    monkeypatch.delenv("SKL_GAME_EMULATOR_REGISTRY", raising=False)
    result = train_page(roms, approvals, receipts, limit=1)
    assert result["page_results"][0]["state"] == "emulator_training_blocked"
    assert result["q_policy_training_completed"] == 0
    assert not list(receipts.iterdir())


def test_private_receipt_directory_is_mandatory(tmp_path):
    roms = tmp_path / "roms"
    roms.mkdir()
    _original(roms, "candidate.gb", b"original homebrew bytes")
    approvals = _approval_file(tmp_path / "rights.json", [])
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    os.chmod(public, 0o755)
    with pytest.raises(RomStudyError, match="0700"):
        train_page(roms, approvals, public)


def test_multifile_descriptor_is_never_silently_trained(tmp_path):
    roms = tmp_path / "roms"
    roms.mkdir()
    rom = _original(roms, "scene.cue", b'FILE "track.bin" BINARY\n  TRACK 01 MODE1/2352\n')
    approvals = _approval_file(tmp_path / "rights.json", [_rights(rom)])
    out = tmp_path / "receipts"
    out.mkdir(mode=0o700)
    result = train_page(roms, approvals, out)
    assert result["q_policy_training_completed"] == 0
    assert result["page_results"][0]["state"] == "explicit_multifile_bundle_required"
    assert result["production_weights_modified"] is False


def test_neural_candidate_rejects_forged_or_missing_q_evidence(tmp_path):
    from skeleton.ai.training.rom_study import train_neural_candidate
    out = tmp_path / "private"
    out.mkdir(mode=0o700)
    fake = out / "rom-fake.json"
    fake.write_text('{"schema_version":"skeleton.jeeves.rom_training_batch.v1"}')
    with pytest.raises(RomStudyError, match="genuine source Q"):
        train_neural_candidate(fake, out)


def test_unapproved_neural_flag_cannot_update_weights(tmp_path, monkeypatch):
    roms = tmp_path / "roms"
    roms.mkdir()
    _original(roms, "game.gb", b"operator-homebrew")
    approvals = _approval_file(tmp_path / "rights.json", [])
    receipts = tmp_path / "receipts"
    receipts.mkdir(mode=0o700)
    from skeleton.jeeves import game_emulator_neural_world
    def forbidden(*args, **kwargs):
        raise AssertionError("neural optimizer must never run for an unapproved ROM")
    monkeypatch.setattr(game_emulator_neural_world, "train_neural_world_from_evidence", forbidden)
    result = train_page(roms, approvals, receipts, train_neural=True)
    assert result["q_policy_training_completed"] == 0
    assert result["shadow_neural_candidates_trained"] == 0
    assert result["production_weights_modified"] is False
