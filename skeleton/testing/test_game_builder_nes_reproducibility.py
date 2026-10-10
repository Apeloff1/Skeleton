"""NES real byte evidence: independent original source and NROM builds.

The synthetic ROM fixture is a structurally plausible *non-game*. It is
never used as proof of hardware execution or NES gameplay. The build
workflow compiles real authored game code using ca65/ld65 separately.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import struct

import pytest

from scripts.game_builder.native_nes_ci import generate, inspect_rom
from scripts.game_builder.nes_reproducibility_ci import (
    NESReproducibilityError, verify_original_nes_rebuild,
)


def synthetic_original_nrom() -> bytes:
    data=bytearray(16+32768+8192)
    data[:8]=b"NES\x1a\x02\x01\x00\x00"
    data[16]=0x78   # 6502 SEI at reset 0x8000
    data[17]=0xEA   # NOP
    data[18]=0x40   # RTI (synthetic interrupt handler)
    struct.pack_into("<HHH",data,16+0x7FFA,0x8002,0x8000,0x8002)
    data[16+32768]=0x18 # original nonempty CHR region
    return bytes(data)


def prepared(tmp_path: Path) -> dict[str, object]:
    first=tmp_path/"nes-authoring-first"
    second=tmp_path/"nes-authoring-second"
    first_evidence=generate(first)
    second_evidence=generate(second)
    cartridge=synthetic_original_nrom()
    first_rom=tmp_path/"original-build.nes"
    second_rom=tmp_path/"independent-rebuild.nes"
    first_rom.write_bytes(cartridge)
    second_rom.write_bytes(cartridge)
    return {
        "first_source":first, "second_source":second,
        "first_rom":first_rom, "second_rom":second_rom,
        "first_source_evidence":first_evidence,
        "second_source_evidence":second_evidence,
        "expected_first_rom_sha256":sha256(cartridge).hexdigest(),
    }


def test_nrom_reproducibility_bound_to_two_generated_original_sources_and_roms(tmp_path):
    args=prepared(tmp_path)
    result=verify_original_nes_rebuild(**args)
    assert result["target"]=="nintendo_famicom"
    assert result["mapper"]==0
    assert result["prg_rom_bytes"]==32768
    assert result["chr_rom_bytes"]==8192
    assert result["rom_sha256"]==sha256(synthetic_original_nrom()).hexdigest()
    assert result["two_distinct_source_directories_checked"] is True
    assert result["identical_generated_source_bytes"] is True
    assert result["two_distinct_cartridge_files_checked"] is True
    assert result["exact_nrom_prg_chr_bytes_match"] is True
    assert result["file_backed_interrupt_vectors_checked"] is True
    assert result["assembler_execution_independently_attested"] is False
    assert result["emulator_gameplay_verified"] is False
    assert result["physical_hardware_verified"] is False
    assert result["third_party_rights_independently_cleared"] is False
    assert result["publication_authorized"] is False
    assert len(result["receipt_sha256"])==64
    assert result==verify_original_nes_rebuild(**args)


@pytest.mark.parametrize("changed_file",("main.s","nes.cfg","Makefile","manifest.json"))
def test_regenerated_nes_source_mutation_fails_before_native_release(tmp_path,changed_file):
    args=prepared(tmp_path)
    target=args["second_source"]/changed_file
    target.write_bytes(target.read_bytes()+b"\nUNREVIEWED")
    with pytest.raises(NESReproducibilityError,match="deterministic"):
        verify_original_nes_rebuild(**args)


@pytest.mark.parametrize("extra",(
    "pirated-game.nes","copied-sprites.chr","unlicensed-song.wav",
    ".private-key","old-proprietary-sdk.dll","forged-license.json",
))
def test_unreviewed_original_nes_assets_fail_closed(tmp_path,extra):
    args=prepared(tmp_path)
    (args["first_source"]/extra).write_bytes(b"external material")
    with pytest.raises(NESReproducibilityError,match="unreviewed"):
        verify_original_nes_rebuild(**args)


@pytest.mark.parametrize("where",("first_rom","second_rom"))
def test_nes_binaries_reject_checksum_preserving_code_swaps(tmp_path,where):
    args=prepared(tmp_path)
    changed=bytearray(args[where].read_bytes())
    changed[17],changed[19]=changed[19],changed[17]
    args[where].write_bytes(changed)
    with pytest.raises(NESReproducibilityError,match="hash|differ"):
        verify_original_nes_rebuild(**args)


@pytest.mark.parametrize("byte,value",(
    (0,0), (4,3), (5,2), (6,0x10), (7,8),
    (16+0x7FFB,0), (16+0x7FFD,0), (16+0x7FFF,0),
    (16+0x7FFC,0xFF),
))
def test_native_nes_refuses_invalid_mapper_header_and_interrupt_vector(
    tmp_path,byte,value,
):
    rom=bytearray(synthetic_original_nrom())
    rom[byte]=value
    path=tmp_path/"bad.nes"
    path.write_bytes(rom)
    with pytest.raises(ValueError):
        inspect_rom(path)


@pytest.mark.parametrize("field",(
    "first_source","second_source","first_rom","second_rom",
))
def test_reusing_one_path_as_two_evidence_items_is_not_two_real_runs(tmp_path,field):
    args=prepared(tmp_path)
    if field.endswith("source"):
        args["second_source"]=args["first_source"]
    else:
        args["second_rom"]=args["first_rom"]
    with pytest.raises(NESReproducibilityError,match="distinct"):
        verify_original_nes_rebuild(**args)


@pytest.mark.parametrize("place",("first_rom","second_rom"))
def test_linked_nes_artifacts_cannot_launder_unapproved_rom_bytes(tmp_path,place):
    args=prepared(tmp_path)
    real=args[place]
    alias=tmp_path/"fake-cartridge.nes"
    alias.symlink_to(real)
    args[place]=alias
    with pytest.raises(ValueError):
        verify_original_nes_rebuild(**args)


@pytest.mark.parametrize("where",("first_source","second_source"))
def test_ancestor_symlink_source_refused_instead_of_following_project_files(
    tmp_path,where,
):
    args=prepared(tmp_path)
    real=args[where]
    alias=tmp_path/"linked-original-game"
    alias.symlink_to(real,target_is_directory=True)
    args[where]=alias
    with pytest.raises(ValueError):
        verify_original_nes_rebuild(**args)


def test_rights_evidence_and_world_identity_cannot_be_swapped_between_games(tmp_path):
    args=prepared(tmp_path)
    args["second_source_evidence"]=dict(args["second_source_evidence"],
                                        world_digest="f"*64)
    with pytest.raises(NESReproducibilityError,match="prebuild evidence"):
        verify_original_nes_rebuild(**args)


@pytest.mark.parametrize("flag",(
    "cartridge_built","emulator_verified","hardware_verified",
    "release_approved","distribution_licensed",
))
def test_generated_nes_manifest_cannot_claim_unproven_legal_hardware_authority(
    tmp_path,flag,
):
    args=prepared(tmp_path)
    manifest=args["first_source"]/"manifest.json"
    data=json.loads(manifest.read_text())
    data[flag]=True
    manifest.write_text(json.dumps(data))
    with pytest.raises(NESReproducibilityError,match="pre-certify"):
        verify_original_nes_rebuild(**args)


def test_nes_compiler_build_directory_is_allowed_but_not_symlinked(tmp_path):
    args=prepared(tmp_path)
    root=args["first_source"]
    build=root/"build"
    build.mkdir()
    # The separate build folder is a legitimate output workspace.
    assert verify_original_nes_rebuild(**args)["two_distinct_source_directories_checked"]
    build.rmdir()
    build.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(NESReproducibilityError,match="compiler output"):
        verify_original_nes_rebuild(**args)


def test_nes_rebuild_rejects_unindependently_claimed_source_hash(tmp_path):
    args=prepared(tmp_path)
    args["expected_first_rom_sha256"]="f"*64
    with pytest.raises(NESReproducibilityError,match="hash"):
        verify_original_nes_rebuild(**args)


def test_no_follow_nes_cartridge_intake_rejects_fifo_without_reading(tmp_path):
    if not hasattr(os,"mkfifo"):
        pytest.skip("POSIX FIFO support required")
    path=tmp_path/"pipe.nes"
    os.mkfifo(path)
    with pytest.raises(ValueError):
        inspect_rom(path)


def test_oversized_nes_cartridge_is_rejected_before_full_file_read(tmp_path):
    path=tmp_path/"giant.nes"
    with path.open("wb") as out:
        out.truncate(1024*1024*128)
    with pytest.raises(ValueError):
        inspect_rom(path)
