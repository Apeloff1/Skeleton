"""Adversarial reproducible Sega cartridge evidence, one CI-approved game at a time.

Uses original generated C/native SDCC inputs and synthetic header-only ROMs.
Two file inputs prove distinct, matching *bytes*, not compiler execution or
legal ownership. Real SDCC clean builds are performed separately by CI.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

import pytest

from scripts.game_builder.native_sega_8bit_ci import emit, verify
from scripts.game_builder.sega_reproducibility_ci import emit_receipt
from skeleton.ai.game_builder.sega_reproducibility import (
    SegaBuildEvidenceError, verify_rebuilt_sega_cartridge,
    verify_separate_authoring_runs,
)
from skeleton.testing.test_game_builder_native_sega8_ci import _rom, REVISION


def prepared(tmp_path: Path, target: str = "sega_master_system") -> dict[str, object]:
    author = tmp_path / "original-author-statement.txt"
    author.write_text(
        "All original line art, characters, world designs and chimes are newly authored.",
        encoding="utf-8",
    )
    root = tmp_path / "generated-game"
    source = emit(target, root, author)
    (root / "build").mkdir()
    suffix = "sms" if target == "sega_master_system" else "gg"
    first, second = (tmp_path / ("first." + suffix), tmp_path / ("rebuilt." + suffix))
    first.write_bytes(_rom(target))
    second.write_bytes(_rom(target))
    original_intake = verify(
        target, root, first, toolchain_revision=REVISION,
        expected_source_sha256=source["source_content_digest"],
        expected_authorship_sha256=source["rights_evidence_sha256"],
    )
    return {
        "target": target, "source_directory": root,
        "first_cartridge": first, "rebuilt_cartridge": second,
        "first_build_evidence": original_intake,
        "expected_source_sha256": source["source_content_digest"],
        "expected_author_declaration_sha256": source["rights_evidence_sha256"],
        "toolchain_git_revision": REVISION,
    }


@pytest.mark.parametrize("target", ["sega_master_system", "sega_game_gear"])
def test_native_rebuild_matches_actual_cartridge_source_world_and_author(tmp_path, target):
    args=prepared(tmp_path,target)
    receipt=verify_rebuilt_sega_cartridge(**args)
    assert receipt.target==target
    assert receipt.cartridge_sha256==sha256(_rom(target)).hexdigest()
    assert receipt.cartridge_bytes==32768
    assert receipt.source_sha256==args["expected_source_sha256"]
    assert receipt.author_declaration_sha256==args["expected_author_declaration_sha256"]
    assert receipt.checked_two_distinct_artifact_paths is True
    assert receipt.exact_rom_bytes_match is True
    assert receipt.source_and_authorship_digests_match is True
    assert receipt.two_compiler_executions_independently_verified is False
    assert receipt.gameplay_execution_verified is False
    assert receipt.source_rights_independently_verified is False
    assert receipt.publication_licensed is False
    assert receipt == verify_rebuilt_sega_cartridge(**args)
    assert len(receipt.public_receipt()["comparison_sha256"])==64
    assert receipt.public_receipt()["publication_licensed"] is False


@pytest.mark.parametrize("target", ["sega_master_system", "sega_game_gear"])
def test_changes_with_same_sega_additive_checksum_are_detected(tmp_path,target):
    args=prepared(tmp_path,target)
    candidate=bytearray(args["rebuilt_cartridge"].read_bytes())
    candidate[0],candidate[1]=candidate[1],candidate[0]
    # The header sum still matches; SHA-256 comparison must fail.
    args["rebuilt_cartridge"].write_bytes(candidate)
    with pytest.raises(SegaBuildEvidenceError,match="differ"):
        verify_rebuilt_sega_cartridge(**args)


@pytest.mark.parametrize("name", ["game.c","Makefile","manifest.json"])
def test_silent_original_game_source_mutation_refuses_second_build(tmp_path,name):
    args=prepared(tmp_path)
    path=args["source_directory"]/name
    path.write_bytes(path.read_bytes()+b"\nUNREVIEWED")
    with pytest.raises(SegaBuildEvidenceError,match="source changed"):
        verify_rebuilt_sega_cartridge(**args)


@pytest.mark.parametrize("extra",[
    "copied-commercial-game.sms","secret-developer-key.pem",".unlicensed-sprite",
    "third-party-song.wav","old-rom-backup.gg","unreviewed-game.c",
])
def test_original_source_tree_ignores_no_hidden_unreviewed_payloads(tmp_path,extra):
    args=prepared(tmp_path)
    (args["source_directory"]/extra).write_bytes(b"unreviewed")
    with pytest.raises(SegaBuildEvidenceError,match="unreviewed"):
        verify_rebuilt_sega_cartridge(**args)


@pytest.mark.parametrize("key,value", [
    ("rom_sha256","a"*64),
    ("source_sha256","b"*64),
    ("target","sega_game_gear"),
    ("toolchain_revision","f"*40),
    ("original_world_digest","0"*64),
    ("reference_safe_replay_digest","1"*64),
    ("source_rights_evidence_sha256","2"*64),
    ("real_rom_structure_verified",False),
    ("rom_header_checksum_verified",False),
    ("source_digest_matches_expected",False),
    ("source_authorship_hash_matches_expected",False),
    ("emulator_playthrough_verified",True),
    ("native_rom_compiled",True),
    ("release_approved",True),
    ("source_rights_independently_proven",True),
    ("toolchain_source_authenticated",True),
    ("source_digest_independently_attested",True),
    ("physical_hardware_verified",True),
    ("distribution_licensed",True),
])
def test_prebuild_evidence_substitution_or_fake_clearance_fails_closed(tmp_path,key,value):
    args=prepared(tmp_path)
    first=dict(args["first_build_evidence"])
    first[key]=value
    args["first_build_evidence"]=first
    with pytest.raises(SegaBuildEvidenceError):
        verify_rebuilt_sega_cartridge(**args)


@pytest.mark.parametrize("field,replacement",[
    ("expected_source_sha256","f"*64),
    ("expected_author_declaration_sha256","a"*64),
    ("toolchain_git_revision","e"*40),
    ("toolchain_git_revision","main"),
    ("target","sega_game_gear"),
])
def test_wrong_external_context_never_reuses_native_ROM_clearance(tmp_path,field,replacement):
    args=prepared(tmp_path)
    args[field]=replacement
    with pytest.raises((SegaBuildEvidenceError,ValueError)):
        verify_rebuilt_sega_cartridge(**args)


def test_same_file_twice_is_not_two_separate_build_artifacts(tmp_path):
    args=prepared(tmp_path)
    args["rebuilt_cartridge"]=args["first_cartridge"]
    with pytest.raises(SegaBuildEvidenceError,match="distinct"):
        verify_rebuilt_sega_cartridge(**args)


@pytest.mark.parametrize("file_attr",["first_cartridge","rebuilt_cartridge"])
def test_symlinked_compiled_game_is_not_valid_rebuild_evidence(tmp_path,file_attr):
    args=prepared(tmp_path)
    source=args[file_attr]
    link=tmp_path/(file_attr+".sms")
    link.symlink_to(source)
    args[file_attr]=link
    with pytest.raises(ValueError):
        verify_rebuilt_sega_cartridge(**args)


def test_second_build_root_is_not_allowed_to_be_symlinked(tmp_path):
    args=prepared(tmp_path)
    build=args["source_directory"]/"build"
    build.rmdir()
    build.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(SegaBuildEvidenceError,match="build folder"):
        verify_rebuilt_sega_cartridge(**args)


def test_same_game_artifact_with_wrong_ROM_extension_is_rejected(tmp_path):
    args=prepared(tmp_path)
    other=tmp_path/"rebuilt.nes"
    other.write_bytes(args["rebuilt_cartridge"].read_bytes())
    args["rebuilt_cartridge"]=other
    with pytest.raises(SegaBuildEvidenceError,match="extension"):
        verify_rebuilt_sega_cartridge(**args)


@pytest.mark.parametrize("claim",[
    "two_compiler_executions_independently_verified",
    "source_rights_independently_verified","gameplay_execution_verified",
    "real_console_hardware_verified","developer_toolchain_authenticity_proven",
    "publication_licensed",
])
def test_hash_matching_cannot_be_mutated_into_hardware_or_legal_certification(tmp_path,claim):
    receipt=verify_rebuilt_sega_cartridge(**prepared(tmp_path))
    with pytest.raises(SegaBuildEvidenceError):
        replace(receipt,**{claim:True})


def test_reproducibility_receipt_cannot_forge_its_content_digest(tmp_path):
    receipt=verify_rebuilt_sega_cartridge(**prepared(tmp_path))
    with pytest.raises(SegaBuildEvidenceError,match="content-bound"):
        replace(receipt,comparison_sha256="f"*64)
    with pytest.raises(SegaBuildEvidenceError):
        replace(receipt,world_sha256="f"*64)


def test_exclusive_local_receipt_write_is_atomic_and_does_not_overwrite(tmp_path):
    destination=tmp_path/"rebuild-proof.json"
    proof=verify_rebuilt_sega_cartridge(**prepared(tmp_path)).public_receipt()
    emit_receipt(destination,proof)
    assert json.loads(destination.read_text())==proof
    assert stat.S_IMODE(destination.stat().st_mode)==0o600
    with pytest.raises(FileExistsError):
        emit_receipt(destination,{"attacker":"overwritten"})
    assert json.loads(destination.read_text())==proof


def test_existing_symlink_receipt_never_removed_or_overwritten(tmp_path):
    existing=tmp_path/"trusted-report.json"
    existing.write_text('{"signed":"keep-me"}',encoding="utf-8")
    alias=tmp_path/"untrusted-link.json"
    alias.symlink_to(existing)
    with pytest.raises(OSError):
        emit_receipt(alias,{"attacker":True})
    assert json.loads(existing.read_text())=={"signed":"keep-me"}
    assert alias.is_symlink()


def test_partial_invalid_receipt_is_cleaned_up(tmp_path):
    destination=tmp_path/"partial-report.json"
    with pytest.raises(TypeError):
        emit_receipt(destination,{"not_json_serializable":object()})
    assert not destination.exists()


def test_output_to_symlinked_parent_directory_fails_closed(tmp_path):
    actual=tmp_path/"real"
    actual.mkdir()
    alias=tmp_path/"link"
    alias.symlink_to(actual,target_is_directory=True)
    with pytest.raises(ValueError):
        emit_receipt(alias/"out.json",{"incomplete":"untrusted"})
    assert list(actual.iterdir())==[]



@pytest.mark.parametrize("target",["sega_master_system","sega_game_gear"])
def test_independent_original_game_source_regeneration_matches_every_file(tmp_path,target):
    args=prepared(tmp_path,target)
    original=tmp_path/"second-authorship.txt"
    original.write_text(
        "All original line art, characters, world designs and chimes are newly authored.",
        encoding="utf-8",
    )
    second=tmp_path/"regenerated"
    proof=emit(target,second,original)
    receipt=verify_separate_authoring_runs(
        args["source_directory"],second,target=target,
        expected_source_sha256=args["expected_source_sha256"],
    )
    assert proof["source_content_digest"]==args["expected_source_sha256"]
    assert receipt["identical_source_bytes"] is True
    assert receipt["generator_invocations_independently_attested"] is False
    assert receipt["author_copyright_title_independently_proven"] is False
    assert receipt["release_authorized"] is False


@pytest.mark.parametrize("file",["game.c","Makefile","manifest.json"])
def test_source_regeneration_flags_modified_homebrew_logic_and_metadata(tmp_path,file):
    args=prepared(tmp_path)
    second=tmp_path/"second"
    author=tmp_path/"second-rights.txt"
    author.write_text(
        "All original line art, characters, world designs and chimes are newly authored.",
        encoding="utf-8",
    )
    emit(args["target"],second,author)
    path=second/file
    path.write_bytes(path.read_bytes()+b"UNREVIEWED")
    with pytest.raises(SegaBuildEvidenceError,match="differ"):
        verify_separate_authoring_runs(
            args["source_directory"],second,target=args["target"],
            expected_source_sha256=args["expected_source_sha256"],
        )


def test_source_regeneration_cannot_hide_unreviewed_file_in_second_run(tmp_path):
    args=prepared(tmp_path)
    second=tmp_path/"regenerated"
    author=tmp_path/"second-rights.txt"
    author.write_text(
        "All original line art, characters, world designs and chimes are newly authored.",
        encoding="utf-8",
    )
    emit(args["target"],second,author)
    (second/".hidden-proprietary-sprites").write_bytes(b"unreviewed")
    with pytest.raises(SegaBuildEvidenceError,match="unreviewed"):
        verify_separate_authoring_runs(
            args["source_directory"],second,target=args["target"],
            expected_source_sha256=args["expected_source_sha256"],
        )


def test_source_regeneration_does_not_compare_one_tree_against_itself(tmp_path):
    args=prepared(tmp_path)
    with pytest.raises(SegaBuildEvidenceError,match="same source"):
        verify_separate_authoring_runs(
            args["source_directory"],args["source_directory"],
            target=args["target"],expected_source_sha256=args["expected_source_sha256"],
        )
