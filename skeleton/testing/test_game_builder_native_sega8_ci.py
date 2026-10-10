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



@pytest.mark.parametrize("target", ("sega_master_system","sega_game_gear"))
def test_real_extended_eight_stage_native_campaign_source_is_solvable_and_distinct(
    tmp_path,target,
):
    evidence=tmp_path/"independent-original-author.txt"
    evidence.write_text(
        "Original eight-chapter game, original graphics and native controls.",
        encoding="utf-8",
    )
    standard=emit(target,tmp_path/"standard",evidence)
    extended=emit(target,tmp_path/"extended",evidence,profile="full_campaign")
    manifest=json.loads((tmp_path/"extended"/"manifest.json").read_text())
    assert standard["original_campaign_profile"]=="standard"
    assert extended["original_campaign_profile"]=="full_campaign"
    assert extended["source_content_digest"] != standard["source_content_digest"]
    assert extended["world_digest"] != standard["world_digest"]
    assert manifest["levels"]==8
    assert manifest["companion_bond_ranks"]==8
    assert manifest["original_native_solution_attract_mode"] is True
    assert manifest["original_demo_playback_steps"]>100
    assert manifest["original_demo_compressed_rom_bytes"] >= (
        manifest["original_demo_playback_steps"] + 3
    ) // 4
    assert manifest["native_per_stage_hardware_bg_palette_accents"] is True
    assert len(manifest["master_system_original_stage_rgb222_accents"])==8
    assert len(manifest["game_gear_original_stage_rgb444_accents"])==8
    assert manifest["distribution_licensed"] is False
    assert manifest["release_approved"] is False
    code=(tmp_path/"extended"/"game.c").read_text(encoding="utf-8")
    assert code.count("static const unsigned char stage_")==8
    assert code.count("static const unsigned char demo_")==8
    assert "original_stage_accent_1[level_index]" in code
    assert len(extended["source_content_digest"])==64


@pytest.mark.parametrize("invalid",(None,True,False,12,{},[],"", "third_party_game", "full_campaign " ))
def test_extended_native_source_profile_fails_closed_before_file_generation(tmp_path,invalid):
    evidence=tmp_path/"authorship.txt"
    evidence.write_text("Independent original digital game.",encoding="utf-8")
    output=tmp_path/"not-a-game"
    with pytest.raises(ValueError,match="profile"):
        emit("sega_master_system",output,evidence,profile=invalid)
    assert not output.exists()



@pytest.mark.parametrize("target",("sega_master_system","sega_game_gear"))
@pytest.mark.parametrize("theme",("forest","space","desert","ocean","arcade"))
def test_custom_independent_original_game_emits_native_source_with_exact_author_identity(
    tmp_path,target,theme,
):
    author=tmp_path/"rights.txt"
    author.write_text(
        "Independently created puzzle rules, art, music, stage layouts.",
        encoding="utf-8",
    )
    parameters={
        "project_id":"authored-multiera-original",
        "title":"My Original Console Journey",
        "seed":271828,"theme":theme,"levels":1,
        "width":13,"height":11,
        "collectibles_per_level":2,"hazards_per_level":2,
    }
    path=tmp_path/target
    receipt=emit(
        target,path,author,profile="custom_original",original_config=parameters,
    )
    manifest=json.loads((path/"manifest.json").read_text(encoding="utf-8"))
    assert receipt["original_campaign_profile"]=="custom_original"
    assert receipt["world_digest"]==manifest["world_digest"]
    assert receipt["source_content_digest"]==sha256(b"\0".join(
        (path/name).read_bytes() for name in ("game.c","Makefile","manifest.json")
    )).hexdigest()
    assert manifest["project_id"]==parameters["project_id"]
    assert manifest["original_color_theme"]==theme
    assert manifest["levels"]==1
    assert manifest["width"]==13 and manifest["height"]==11
    assert manifest["binary_compiled"] is False
    assert manifest["distribution_licensed"] is False
    assert manifest["release_approved"] is False
    assert manifest["native_per_stage_hardware_bg_palette_accents"] is True
    assert manifest["original_native_solution_attract_mode"] is True
    again=emit(
        target,tmp_path/(target+"-again"),author,
        profile="custom_original",original_config=parameters,
    )
    assert receipt["world_digest"]==again["world_digest"]
    assert receipt["source_content_digest"]==again["source_content_digest"]


@pytest.mark.parametrize("target",("sega_master_system","sega_game_gear"))
def test_custom_original_cross_console_identity_without_copying_third_party_content(tmp_path,target):
    evidence=tmp_path/"author.txt"
    evidence.write_text("Source imagery and puzzle concepts created independently",encoding="utf-8")
    cfg={
        "project_id":"original-fixed-seed-reproducible",
        "title":"Unique Independently Authored Maze",
        "seed":123456,"theme":"arcade","levels":3,
        "width":17,"height":15,
    }
    emitted=emit(target,tmp_path/target,evidence,profile="custom_original",original_config=cfg)
    assert emitted["native_binary_built"] is False
    assert emitted["rights_independently_verified"] is False
    assert emitted["distribution_licensed"] is False


@pytest.mark.parametrize("custom",(
    None,{},{"project_id":"only-one"},
    {"project_id":"a","title":"b","seed":1,"theme":"forest","levels":1,
     "width":21},
    {"project_id":"a","title":"b","seed":1,"theme":"forest","levels":1,
     "height":17},
    {"project_id":"a","title":"b","seed":1,"theme":"forest","levels":9},
    {"project_id":"a","title":"b","seed":1,"theme":"forest","levels":8,
     "collectibles_per_level":7},
    {"project_id":"a","title":"b","seed":1,"theme":"forest","levels":1,
     "third_party_rom":"secret.sms"},
    {"project_id":"a","title":"b","seed":True,"theme":"forest","levels":1},
    {"project_id":"a","title":"b","seed":1,"theme":"nintendo","levels":1},
))
def test_custom_native_original_hardware_contract_refuses_unbounded_or_licensed_override(
    tmp_path,custom,
):
    author=tmp_path/"author.txt"
    author.write_bytes(b"independently-authored content")
    path=tmp_path/"must-not-exist"
    with pytest.raises(ValueError):
        emit(
            "sega_game_gear",path,author,
            profile="custom_original",original_config=custom,
        )
    assert not path.exists()


def test_native_preset_rejects_unreviewed_custom_parameters(tmp_path):
    author=tmp_path/"author.txt"
    author.write_bytes(b"original license and source evidence")
    with pytest.raises(ValueError,match="custom game overrides"):
        emit("sega_master_system",tmp_path/"no-game",author,
             profile="standard",original_config={"seed":9})
    assert not (tmp_path/"no-game").exists()
