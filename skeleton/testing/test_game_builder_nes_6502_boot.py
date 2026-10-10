"""Independent NES CPU/PPU bus and native game bootstrap acceptance tests.

No copyrighted NES image, external firmware, game console ROMs, or brand
artwork are included. The synthetic machine code checks the *test bench*;
real native 6502 assembly is compiled and exercised by NES GitHub CI.
"""
from __future__ import annotations

from hashlib import sha256
import struct

import pytest

from scripts.game_builder.nes_6502_boot import (
    ObservableNESBus, NES6502BootError, verify_original_nes_6502_boot,
    _MAX_INSTRUCTIONS, _VBLANK_START, _FRAME_CPU_CYCLES,
)
from skeleton.testing.test_game_builder_nes_reproducibility import (
    synthetic_original_nrom,
)


class DummyCPU:
    processorCycles=0


def new_bus():
    return ObservableNESBus(synthetic_original_nrom())


def test_real_mapper_zero_cpu_rom_mirrors_and_ram_mirrors():
    bus=new_bus()
    assert bus[0x8000] == 0x78
    assert bus[0x8001] == 0xea
    assert bus[0xFFFC] == 0x00
    assert bus[0xFFFD] == 0x80
    bus[0x0005]=0xA4
    assert bus[0x0805] == bus[0x1005] == bus[0x1805] == 0xA4
    bus[0x1805]=0x47
    assert bus[0x0005]==0x47


def test_ppu_palette_and_nametable_data_use_real_nes_address_latch():
    bus=new_bus()
    bus[0x2006]=0x3F
    bus[0x2006]=0x00
    for color in range(32):
        bus[0x2007]=color
    assert bus.palette_writes==32
    assert bytes(bus.palette)==bytes(range(32))
    bus[0x2002]
    bus[0x2006]=0x20
    bus[0x2006]=0x00
    for tile in range(255):
        bus[0x2007]=tile
    assert bus.nametable_writes==255
    assert bytes(bus.nametable[:255])==bytes(range(255))


def test_ppu_program_control_can_select_real_32_byte_name_table_stride():
    bus=new_bus()
    bus[0x2000]=4
    bus[0x2006]=0x20
    bus[0x2006]=0
    bus[0x2007]=1
    bus[0x2007]=2
    assert bus.nametable[0]==1
    assert bus.nametable[32]==2


def test_synthetic_ntsc_clock_produces_one_read_to_clear_vblank_per_frame():
    bus=new_bus()
    clock=DummyCPU()
    bus.cpu=clock
    assert bus[0x2002] == 0
    clock.processorCycles=_VBLANK_START+1
    assert bus[0x2002]==0x80
    assert bus[0x2002]==0
    clock.processorCycles=_FRAME_CPU_CYCLES+1
    assert bus[0x2002]==0
    clock.processorCycles=_FRAME_CPU_CYCLES+_VBLANK_START+1
    assert bus[0x2002]==0x80
    assert bus[0x2002]==0


def test_ppu_register_mirrors_still_access_original_status_and_palette_data():
    bus=new_bus()
    bus[0x3FFE]=0x3F  # mirrored $2006
    bus[0x3FFE]=0x00
    bus[0x3FFF]=0x28  # mirrored $2007
    assert bus.palette_writes==1 and bus.palette[0]==0x28
    assert bus[0x2002]==0


def test_actual_cpu_ram_sprite_dma_reads_from_page_and_preserves_order():
    bus=new_bus()
    for i in range(256):
        bus[0x200+i]=(i*7)&255
    bus[0x4014]=0x02
    assert bus.oam_dma_count==1
    assert bus.oam==bytearray((i*7)&255 for i in range(256))


@pytest.mark.parametrize("button,bits",[
    ("up",1<<4),("down",1<<5),("left",1<<6),("right",1<<7),
    (None,0),
])
def test_original_famicom_controller_shift_reads_all_eight_buttons(button,bits):
    bus=new_bus()
    bus.set_button(button)
    bus[0x4016]=1
    bus[0x4016]=0
    observations=sum((bus[0x4016]&1)<<index for index in range(8))
    assert observations==bits
    assert bus.reads_4016==8


@pytest.mark.parametrize("invalid",["jump","start+right", "",None.__class__, 1,False])
def test_native_nes_controller_rejects_unmodeled_player_actions(invalid):
    bus=new_bus()
    with pytest.raises((NES6502BootError,TypeError)):
        bus.set_button(invalid)


@pytest.mark.parametrize("invalid",[0,1,24999,850001,True,"9999",None,1.5])
def test_native_cpu_gameplay_rejects_unbounded_execution_budget(tmp_path,invalid):
    file=tmp_path/"game.nes"
    rom=synthetic_original_nrom()
    file.write_bytes(rom)
    with pytest.raises(NES6502BootError,match="budget"):
        verify_original_nes_6502_boot(
            file,expected_sha256=sha256(rom).hexdigest(),
            instruction_budget=invalid,
        )


def test_compiled_rom_signature_without_real_ppu_writes_does_not_boot(tmp_path):
    pytest.importorskip("py65")
    image=synthetic_original_nrom()
    file=tmp_path/"rom-with-no-gameplay.nes"
    file.write_bytes(image)
    with pytest.raises(NES6502BootError,match="exceeded|escaped"):
        verify_original_nes_6502_boot(
            file,expected_sha256=sha256(image).hexdigest(),
            instruction_budget=25000,
        )


def test_rom_substitution_rejected_before_loading_native_6502(tmp_path):
    path=tmp_path/"original-game.nes"
    image=synthetic_original_nrom()
    path.write_bytes(image)
    with pytest.raises(NES6502BootError,match="changed"):
        verify_original_nes_6502_boot(path,expected_sha256="f"*64)


def test_forged_nes_rom_symlink_refused_prior_to_any_native_cpu_execution(tmp_path):
    src=tmp_path/"original.nes"
    src.write_bytes(synthetic_original_nrom())
    link=tmp_path/"forged.nes"
    link.symlink_to(src)
    with pytest.raises(ValueError):
        verify_original_nes_6502_boot(
            link, expected_sha256=sha256(src.read_bytes()).hexdigest(),
        )


def test_native_cpu_observations_never_relabel_gameplay_as_hardware_or_rights():
    device=new_bus()
    assert not hasattr(device,"physical_hardware_verified")
    assert not hasattr(device,"copyright_status_certified")
