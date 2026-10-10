"""Executable, offline acceptance for the Sega Z80 build-evidence intake.

Synthetic ROMs test only structural evidence; they never attest SDCC runs.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

import pytest

from scripts.game_builder.native_sega_8bit_ci import emit, verify


REVISION = "533ae572c897cf44f1da865013ebf690134301a3"


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
