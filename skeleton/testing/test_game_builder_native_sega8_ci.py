"""Executable, offline acceptance for the Sega Z80 build-evidence intake.

Synthetic ROMs test only structural evidence; they never attest SDCC runs.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
import json

import pytest

from scripts.game_builder.native_sega_8bit_ci import emit, verify


REVISION = "533ae572c897cf44f1da865013ebf690134301a3"  # actual pinned Git SHA-1


def _rom(target: str) -> bytes:
    """Intentionally synthetic 32KiB header fixture, not an actual playable game."""
    image = bytearray(32768)
    image[0:8] = b"TESTROM!"
    image[0x7FF0:0x7FF8] = b"TMR SEGA"
    image[0x7FFF] = 0x4c if target == "sega_master_system" else 0x7c
    image[0x7FFA:0x7FFC] = (sum(image[:0x7FF0]) & 0xFFFF).to_bytes(2, "little")
    return bytes(image)


@pytest.mark.parametrize("target,suffix",(
    ("sega_master_system","sms"),("sega_game_gear","gg"),
))
def test_compilation_receipt_does_not_forge_build_or_legal_approval(
    tmp_path, target, suffix,
):
    author=tmp_path/"author.txt"
    author.write_text("I independently authored these puzzle games.",encoding="utf-8")
    source=tmp_path/target
    emitted=emit(target,source,author)
    assert emitted["target"]==target
    assert emitted["native_binary_built"] is False
    rom=tmp_path/("game."+suffix)
    rom.write_bytes(_rom(target))
    evidence=verify(target,source,rom,toolchain_revision=REVISION)
    assert evidence["rom_sha256"]==sha256(rom.read_bytes()).hexdigest()
    assert evidence["native_rom_compiled"] is False
    assert evidence["real_rom_structure_verified"] is True
    assert evidence["emulator_playthrough_verified"] is False
    assert evidence["rights_independently_verified"] is False
    assert evidence["release_approved"] is False
    assert evidence["source_sha256"]==emitted["source_content_digest"]
    assert evidence["toolchain_revision_hash_algorithm"]=="git-sha1"
    assert evidence["toolchain_source_authenticated"] is False
    assert evidence["source_rights_evidence_sha256"]==emitted["rights_evidence_sha256"]
    assert evidence["source_rights_independently_proven"] is False


def test_wrong_hardware_manifest_or_forged_claim_fails_closed(tmp_path):
    author=tmp_path/"auth.txt"
    author.write_bytes(b"new artwork mine")
    source=tmp_path/"console"
    emit("sega_master_system",source,author)
    rom=tmp_path/"owned.sms"
    rom.write_bytes(_rom("sega_master_system"))
    with pytest.raises(ValueError,match="identity"):
        verify("sega_game_gear",source,rom,toolchain_revision=REVISION)
    with pytest.raises(ValueError,match="revision"):
        verify("sega_master_system",source,rom,toolchain_revision="master")
    manifest=source/"manifest.json"
    payload=json.loads(manifest.read_text())
    payload["release_approved"]=True
    manifest.write_text(json.dumps(payload),encoding="utf-8")
    with pytest.raises(ValueError,match="forged"):
        verify("sega_master_system",source,rom,toolchain_revision=REVISION)


def test_corrupt_rom_and_symlink_input_fail_even_with_matching_source(tmp_path):
    author=tmp_path/"auth.txt"
    author.write_bytes(b"original content and game project")
    source=tmp_path/"console"
    emit("sega_game_gear",source,author)
    path=tmp_path/"original.gg"
    path.write_bytes(_rom("sega_game_gear"))
    path.write_bytes(path.read_bytes()[:-1]+b"X")
    with pytest.raises(Exception):
        verify("sega_game_gear",source,path,toolchain_revision=REVISION)
    real=tmp_path/"good.gg"
    real.write_bytes(_rom("sega_game_gear"))
    link=tmp_path/"symlink.gg"
    link.symlink_to(real)
    with pytest.raises(Exception):
        verify("sega_game_gear",source,link,toolchain_revision=REVISION)



def test_supported_sha256_git_commit_identifier_does_not_assert_toolchain_authenticity(tmp_path):
    author=tmp_path/"author.txt"
    author.write_text("Newly authored interactive puzzles",encoding="utf-8")
    src=tmp_path/"src"
    emit("sega_master_system",src,author)
    rom=tmp_path/"source.sms"
    rom.write_bytes(_rom("sega_master_system"))
    receipt=verify(
        "sega_master_system",src,rom,
        toolchain_revision=sha256(b"synthetic Git SHA-256 revision identifier").hexdigest(),
    )
    assert receipt["toolchain_revision_hash_algorithm"]=="git-sha256"
    assert receipt["toolchain_source_authenticated"] is False


@pytest.mark.parametrize("bad",[
    "", "HEAD", "main", "5"*39, "5"*41, "5"*63, "5"*65,
    "G"*40, "0x"+"0"*40, " "+"a"*40,
])
def test_git_revision_cannot_be_ref_alias_or_partial_commit(tmp_path,bad):
    author=tmp_path/"author.txt"
    author.write_text("Original homebrew",encoding="utf-8")
    src=tmp_path/"src"
    emit("sega_master_system",src,author)
    rom=tmp_path/"original.sms"
    rom.write_bytes(_rom("sega_master_system"))
    with pytest.raises(ValueError,match="Git revision"):
        verify("sega_master_system",src,rom,toolchain_revision=bad)



@pytest.mark.parametrize("unreviewed",[
    "commercial-game.sms", "copied-sprites.png", "unlicensed-soundtrack.wav",
    "secret-license.key", ".hidden-rights.json", "wrong-binary.exe",
])
def test_sega_source_package_cannot_hide_unreviewed_assets(tmp_path,unreviewed):
    author=tmp_path/"authorship.txt"
    author.write_text("Original artwork, movement and puzzle mechanics",encoding="utf-8")
    source=tmp_path/"source"
    emit("sega_master_system",source,author)
    (source/unreviewed).write_bytes(b"independently-unreviewed-payload")
    rom=tmp_path/"native.sms"
    rom.write_bytes(_rom("sega_master_system"))
    with pytest.raises(ValueError,match="unreviewed"):
        verify("sega_master_system",source,rom,toolchain_revision=REVISION)


def test_real_build_directory_is_accepted_without_adding_false_source_integrity(tmp_path):
    author=tmp_path/"authorship.txt"
    author.write_text("Original handheld game story and tiles",encoding="utf-8")
    source=tmp_path/"source"
    evidence=emit("sega_master_system",source,author)
    (source/"build").mkdir()
    (source/"build"/"compiler.o").write_bytes(b"assembler-intermediate")
    rom=tmp_path/"native.sms"
    rom.write_bytes(_rom("sega_master_system"))
    receipt=verify(
        "sega_master_system",source,rom,toolchain_revision=REVISION,
        expected_source_sha256=evidence["source_content_digest"],
        expected_authorship_sha256=evidence["rights_evidence_sha256"],
    )
    assert receipt["source_digest_matches_expected"] is True
    assert receipt["source_digest_independently_attested"] is False
    assert receipt["source_authorship_hash_matches_expected"] is True
    assert receipt["source_rights_independently_proven"] is False
    assert receipt["source_sha256"]==evidence["source_content_digest"]
    assert receipt["native_rom_compiled"] is False


def test_source_digest_without_independent_pin_is_not_reported_as_authenticated(tmp_path):
    author=tmp_path/"authorship.txt"
    author.write_text("Original fantasy adventure",encoding="utf-8")
    source=tmp_path/"source"
    emit("sega_master_system",source,author)
    rom=tmp_path/"native.sms"
    rom.write_bytes(_rom("sega_master_system"))
    receipt=verify("sega_master_system",source,rom,toolchain_revision=REVISION)
    assert receipt["source_digest_matches_expected"] is False


def test_sega_source_mutation_invalidates_external_prebuild_hash(tmp_path):
    author=tmp_path/"authorship.txt"
    author.write_text("Original game author evidence",encoding="utf-8")
    source=tmp_path/"source"
    evidence=emit("sega_master_system",source,author)
    (source/"game.c").write_text((source/"game.c").read_text()+"\\n// unauthorized post-review edit",encoding="utf-8")
    rom=tmp_path/"native.sms"
    rom.write_bytes(_rom("sega_master_system"))
    with pytest.raises(ValueError,match="changed"):
        verify(
            "sega_master_system",source,rom,toolchain_revision=REVISION,
            expected_source_sha256=evidence["source_content_digest"],
        )


@pytest.mark.parametrize("malformed", ["master","f"*64,"E"*64])
def test_invalid_external_source_pin_does_not_qualify_original_game(tmp_path,malformed):
    author=tmp_path/"authorship.txt"
    author.write_text("my authored game",encoding="utf-8")
    source=tmp_path/"source"
    emit("sega_master_system",source,author)
    rom=tmp_path/"native.sms"
    rom.write_bytes(_rom("sega_master_system"))
    with pytest.raises(ValueError,match="digest|changed"):
        verify(
            "sega_master_system",source,rom,toolchain_revision=REVISION,
            expected_source_sha256=malformed,
        )


def test_sega_source_ancestor_symlink_cannot_redirect_code_to_unreviewed_disk(tmp_path):
    author=tmp_path/"authorship.txt"
    author.write_text("Original game assets",encoding="utf-8")
    source=tmp_path/"source"
    emit("sega_master_system",source,author)
    alias=tmp_path/"link"
    alias.symlink_to(source,target_is_directory=True)
    rom=tmp_path/"native.sms"
    rom.write_bytes(_rom("sega_master_system"))
    with pytest.raises(ValueError):
        verify("sega_master_system",alias,rom,toolchain_revision=REVISION)



def test_author_rights_receipt_invalidated_if_evidence_is_substituted(tmp_path):
    author=tmp_path/"authorship.txt"
    author.write_text("Independent original star-hero puzzles and music",encoding="utf-8")
    src=tmp_path/"source"
    claim=emit("sega_master_system",src,author)
    rom=tmp_path/"native.sms"
    rom.write_bytes(_rom("sega_master_system"))
    with pytest.raises(ValueError,match="authorship evidence changed"):
        verify(
            "sega_master_system",src,rom,toolchain_revision=REVISION,
            expected_authorship_sha256=sha256(b"another author rights packet").hexdigest(),
        )
    validated=verify(
        "sega_master_system",src,rom,toolchain_revision=REVISION,
        expected_authorship_sha256=claim["rights_evidence_sha256"],
    )
    assert validated["source_authorship_hash_matches_expected"] is True
    assert validated["source_rights_independently_proven"] is False


@pytest.mark.parametrize("not_a_hash",["short","-1"*32,"0000","F"*64])
def test_malformed_author_provenance_refused(tmp_path,not_a_hash):
    author=tmp_path/"authors.txt"
    author.write_text("new game ideas, expression and rights",encoding="utf-8")
    src=tmp_path/"source"
    emit("sega_master_system",src,author)
    rom=tmp_path/"native.sms"
    rom.write_bytes(_rom("sega_master_system"))
    with pytest.raises(ValueError,match="authorship evidence"):
        verify(
            "sega_master_system",src,rom,toolchain_revision=REVISION,
            expected_authorship_sha256=not_a_hash,
        )



@pytest.mark.parametrize("fixture",[
    "symlink-file", "symlink-ancestor", "hardlink", "empty", "sparse-oversize",
])
def test_original_authorship_evidence_refuses_unsafe_filesystem_sources(tmp_path,fixture):
    evidence=tmp_path/"authorship.txt"
    evidence.write_bytes(b"Independent authored original maze, story and sound.")
    chosen=evidence
    if fixture=="symlink-file":
        chosen=tmp_path/"linked.txt"
        chosen.symlink_to(evidence)
    elif fixture=="symlink-ancestor":
        anchor=tmp_path/"linked-ancestor"
        anchor.symlink_to(tmp_path,target_is_directory=True)
        chosen=anchor/"authorship.txt"
    elif fixture=="hardlink":
        chosen=tmp_path/"copied-inode.txt"
        os.link(evidence,chosen)
    elif fixture=="empty":
        evidence.write_bytes(b"")
    elif fixture=="sparse-oversize":
        with evidence.open("wb") as stream:
            stream.truncate(8*1024*1024+1)
    with pytest.raises(ValueError,match="original author evidence"):
        emit("sega_master_system",tmp_path/"not-created",chosen)
    assert not (tmp_path/"not-created").exists()
