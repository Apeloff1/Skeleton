"""Six-era native homebrew ROM/tape inspection without firmware redistribution."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
import struct

import pytest

from skeleton.ai.game_builder.native_retro_artifact import (
    RetroArtifactError, inspect_original_retro_artifact,
)
from skeleton.ai.game_builder.sms_rom import make_sms
from skeleton.ai.game_builder.msx1_rom import make_msx1_rom
from skeleton.ai.game_builder.spectrum_tap import make_tape
from skeleton.testing.test_game_builder_sms_native import _fake_sms_binary
from skeleton.testing.test_game_builder_msx1_native import _fake_msx_program


def dmg(*,color=False):
    b=bytearray(32768)
    b[0x100:0x104]=b"\x00\xc3\x50\x01"
    b[0x143]=0x80 if color else 0
    b[0x147]=0
    b[0x148]=0
    b[0x14D]=(-sum(b[0x134:0x14D])-(0x14D-0x134))&255
    return bytes(b)


def nes():
    b=bytearray(16+32768+8192)
    b[:6]=b"NES\x1a\x02\x01"
    b[16]=0x78
    struct.pack_into("<H",b,16+32768-4,0x8000)
    return bytes(b)


@pytest.mark.parametrize("target,artifact",[
    ("nintendo_game_boy",dmg()),
    ("nintendo_game_boy_color",dmg(color=True)),
    ("nintendo_famicom",nes()),
    ("sega_master_system",make_sms(_fake_sms_binary())),
    ("msx1",make_msx1_rom(_fake_msx_program())),
    ("sinclair_zx_spectrum",make_tape(b"\xfb\xaf\xd3\xfe"+bytes(range(128)))),
])
def test_real_file_hardware_metadata_can_be_inspected_without_publisher_clearance(
    tmp_path,target,artifact,
):
    path=tmp_path/"my-authored-game.rom"
    path.write_bytes(artifact)
    receipt=inspect_original_retro_artifact(
        path,target_platform_id=target,expected_sha256=sha256(artifact).hexdigest(),
    )
    assert receipt.artifact_sha256==sha256(artifact).hexdigest()
    assert receipt.artifact_size==len(artifact)
    assert receipt.header_and_layout_checked
    assert not receipt.header_authenticity_proven
    assert not receipt.emulator_gameplay_verified
    assert not receipt.physical_hardware_verified
    assert not receipt.copied_asset_free_certified
    assert not receipt.licensed_distribution_authorized
    assert receipt.public_receipt()["licensed_distribution_authorized"] is False
    assert receipt==inspect_original_retro_artifact(
        path,target_platform_id=target,expected_sha256=sha256(artifact).hexdigest(),
    )
    with pytest.raises(RetroArtifactError):
        replace(receipt,licensed_distribution_authorized=True)
    with pytest.raises(RetroArtifactError):
        replace(receipt,emulator_gameplay_verified=True)


@pytest.mark.parametrize("target,artifact",[
    ("nintendo_game_boy",dmg()),
    ("nintendo_game_boy_color",dmg(color=True)),
    ("nintendo_famicom",nes()),
    ("sega_master_system",make_sms(_fake_sms_binary())),
    ("msx1",make_msx1_rom(_fake_msx_program())),
    ("sinclair_zx_spectrum",make_tape(b"\xfb\xaf\xd3\xfe"+bytes(range(128)))),
])
def test_every_historical_system_refuses_modified_rom_even_with_valid_old_header(
    tmp_path,target,artifact,
):
    path=tmp_path/"game"
    path.write_bytes(artifact[:-1]+bytes((artifact[-1]^1,)))
    with pytest.raises(RetroArtifactError,match="changed"):
        inspect_original_retro_artifact(
            path,target_platform_id=target,expected_sha256=sha256(artifact).hexdigest(),
        )


@pytest.mark.parametrize("offset,value",[
    (0x14D,0), (0x148,0xFF), (0x147,0xFF), (0x143,0xC0),
    (0x148,0x01),
])
def test_original_dmg_header_hardware_integrity_and_banked_rom_sizes(
    tmp_path,offset,value,
):
    b=bytearray(dmg())
    b[offset]=value
    path=tmp_path/"bad.gb"
    path.write_bytes(b)
    with pytest.raises(RetroArtifactError):
        inspect_original_retro_artifact(
            path,target_platform_id="nintendo_game_boy",
            expected_sha256=sha256(b).hexdigest(),
        )


@pytest.mark.parametrize("offset,value",[
    (0x143,0), (0x147,0xFF), (0x148,0x01), (0x14D,0),
])
def test_cgb_cartridge_requires_color_header_and_bounded_original_rom(
    tmp_path,offset,value,
):
    b=bytearray(dmg(color=True))
    b[offset]=value
    path=tmp_path/"bad.gbc"
    path.write_bytes(b)
    with pytest.raises(RetroArtifactError):
        inspect_original_retro_artifact(
            path,target_platform_id="nintendo_game_boy_color",
            expected_sha256=sha256(b).hexdigest(),
        )


@pytest.mark.parametrize("offset,value",[
    (0,0), (4,3),(5,3),(6,0x04),(6,0x10),(7,0x08),
    (8,0x40),(16,0),(16+32768-4,0xFF),
])
def test_nes_mapper_trainer_reserved_region_and_reset_vector_mutations_rejected(
    tmp_path,offset,value,
):
    b=bytearray(nes())
    b[offset]=value
    path=tmp_path/"changed.nes"
    path.write_bytes(b)
    with pytest.raises(RetroArtifactError):
        inspect_original_retro_artifact(
            path,target_platform_id="nintendo_famicom",
            expected_sha256=sha256(b).hexdigest(),
        )


def test_native_game_boy_cgb_exclusivity_cannot_be_rebranded_as_dmg(tmp_path):
    b=bytearray(dmg(color=True))
    b[0x143]=0xC0
    b[0x14D]=(-sum(b[0x134:0x14D])-(0x14D-0x134))&255
    path=tmp_path/"cgb-only.rom"
    path.write_bytes(b)
    with pytest.raises(RetroArtifactError,match="CGB-only"):
        inspect_original_retro_artifact(
            path,target_platform_id="nintendo_game_boy",
            expected_sha256=sha256(b).hexdigest(),
        )
    result=inspect_original_retro_artifact(
        path,target_platform_id="nintendo_game_boy_color",
        expected_sha256=sha256(b).hexdigest(),
    )
    assert not result.physical_hardware_verified


@pytest.mark.parametrize("target,artifact",[
    ("nintendo_game_boy",dmg()),
    ("nintendo_famicom",nes()),
    ("sega_master_system",make_sms(_fake_sms_binary())),
    ("msx1",make_msx1_rom(_fake_msx_program())),
])
def test_symlinked_retro_roms_cannot_be_laundered_as_original_local_files(
    tmp_path,target,artifact,
):
    a=tmp_path/"real"
    a.write_bytes(artifact)
    b=tmp_path/"symlink"
    b.symlink_to(a)
    with pytest.raises(RetroArtifactError):
        inspect_original_retro_artifact(
            b,target_platform_id=target,expected_sha256=sha256(artifact).hexdigest(),
        )


def test_unsupported_historic_platform_is_never_silently_treated_as_a_game_boy(tmp_path):
    b=dmg()
    p=tmp_path/"game"
    p.write_bytes(b)
    with pytest.raises(RetroArtifactError):
        inspect_original_retro_artifact(
            p,target_platform_id="nintendo_game_boy_advance",
            expected_sha256=sha256(b).hexdigest(),
        )



def test_game_boy_rom_with_blank_reset_entry_is_not_runnable_machine_code(tmp_path):
    rom=bytearray(dmg())
    rom[0x100:0x104]=bytes(4)
    path=tmp_path/"uninitialized.gb"
    path.write_bytes(rom)
    with pytest.raises(RetroArtifactError,match="entry"):
        inspect_original_retro_artifact(
            path,target_platform_id="nintendo_game_boy",
            expected_sha256=sha256(rom).hexdigest(),
        )
