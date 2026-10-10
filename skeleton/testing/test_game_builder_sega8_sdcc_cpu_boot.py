"""Device adversarial checks for real Sega SDCC Z80 opcode smoke harness.

Host device tests never imply that a synthetic cartridge is a playable game.
"""
from __future__ import annotations

import pytest

from scripts.game_builder.emulate_sega8_sdcc_boot import (
    MAX_INSTRUCTIONS, SDCCSegaBootError, Sega8Machine, boot_rom,
)


@pytest.mark.parametrize("target", ("sega_master_system", "sega_game_gear"))
def test_bounded_real_z80_memory_rom_readonly_ram_mirrors_and_controller(target):
    machine = Sega8Machine(bytes([0x76]) * 32768, target=target)
    assert machine.read(0) == 0x76
    assert machine.read(0x7FFF) == 0x76
    assert machine.read(0x8000) == 0xFF
    machine.write(0xC005, 0x91)
    assert machine.read(0xE005) == 0x91
    machine.write(0xE005, 0x64)
    assert machine.read(0xC005) == 0x64
    for address in (0, 0x7FFF, 0x8000, 0xBFFF):
        with pytest.raises(SDCCSegaBootError, match="immutable"):
            machine.write(address, 3)
    machine.controller = 0xFB
    assert machine.read_port(0xDC) == 0xFB
    assert machine.read_port(0xDD) == 0xFF
    if target == "sega_game_gear":
        machine.gg_start = 0x7F
        assert machine.read_port(0x00) == 0x7F
        machine.write_port(0x06, 0xFF)
    else:
        with pytest.raises(SDCCSegaBootError, match="unexpected"):
            machine.read_port(0x00)
        with pytest.raises(SDCCSegaBootError, match="unexpected"):
            machine.write_port(0x06, 3)


@pytest.mark.parametrize("target", ("sega_master_system", "sega_game_gear"))
def test_real_vdp_name_table_palette_and_character_validation(target):
    machine = Sega8Machine(bytes(32768), target=target)
    # Actual SMS VDP address setup: first low byte, second high/control.
    machine.write_port(0xBF, 0x0E)
    machine.write_port(0xBF, 0x82)   # R2 = 0x0E, name table at $3800.
    machine.write_port(0xBF, 0x40)
    machine.write_port(0xBF, 0x81)   # R1 = 0x40, display enabled.
    machine.write_port(0xBF, 0x00)
    machine.write_port(0xBF, 0xC0)   # CRAM address zero.
    for _ in range(16):
        machine.write_port(0xBE, 0x1F)
    assert machine.cram_writes == 16
    if target == "sega_master_system":
        with pytest.raises(SDCCSegaBootError, match="6-bit"):
            machine.write_port(0xBE, 0x80)
    left, top, hud = (0, 2, 0) if target == "sega_master_system" else (6, 5, 3)
    def bg(x, y, tile):
        address = 0x3800 + (y * 32 + x) * 2
        machine.write_port(0xBF, address & 255)
        machine.write_port(0xBF, 0x40 | (address >> 8))
        machine.write_port(0xBE, tile)
        machine.write_port(0xBE, 0)
    bg(left+1, top+1, 5)
    for x in (13, 14, 15, 16):
        bg(left+x, hud, 6)
    bg(left+18, hud, 17)
    observed = machine.observed_background()
    assert observed["background_display_enabled"] is True
    assert observed["hero_screen_tile_positions"] == [(left+1, top+1)]
    assert observed["score_digit_tiles"] == [6, 6, 6, 6]
    assert observed["companion_expression_tile"] == 17
    machine.frame_ready = True
    assert machine.read_port(0xBF) == 0x80
    assert machine.read_port(0xBF) == 0x00
    with pytest.raises(SDCCSegaBootError, match="graphics and palette"):
        machine.observe_boot()


def test_native_z80_emulator_fails_on_unsupported_io_and_invalid_bounds(tmp_path):
    machine = Sega8Machine(bytes(32768), target="sega_master_system")
    with pytest.raises(SDCCSegaBootError, match="unexpected"):
        machine.write_port(0x42, 0)
    with pytest.raises(SDCCSegaBootError, match="unexpected"):
        machine.read_port(0x42)
    with pytest.raises(SDCCSegaBootError, match="incomplete"):
        machine.write_port(0xBF, 2)
        machine.write_port(0xBE, 2)
    bad = tmp_path/"fake.sms"
    bad.write_bytes(b"MZ" * 16384)
    with pytest.raises(Exception):
        boot_rom(bad, target="sega_master_system")
    with pytest.raises(SDCCSegaBootError, match="unknown"):
        boot_rom(bad, target="sega_fictional")
    for count in (0, -1, MAX_INSTRUCTIONS + 1, True):
        with pytest.raises(SDCCSegaBootError, match="instruction limit"):
            boot_rom(bad, target="sega_master_system", max_instructions=count)



@pytest.mark.parametrize("target", ("sega_master_system", "sega_game_gear"))
def test_independent_z80_core_exercises_actual_opcode_bus_callbacks(target):
    """Isolate a broken CPU/I/O adapter from a defective full cartridge boot.

    The tiny instruction fixture is not real original-game proof; it merely
    proves the independently sourced CPU is connected to the device callbacks.
    """
    z80_python = pytest.importorskip("z80_python")
    rom = bytearray(32768)
    # Real opcodes: LD A,9Fh; OUT (7Fh),A; IN A,(BFh); HALT.
    rom[0:7] = bytes((0x3E, 0x9F, 0xD3, 0x7F, 0xDB, 0xBF, 0x76))
    machine = Sega8Machine(bytes(rom), target=target)
    cpu = z80_python.Z80CPU(
        machine.read, machine.write,
        read_port=machine.read_port, write_port=machine.write_port,
    )
    cpu.pc = 0
    for _ in range(4):
        cpu.step()
    assert cpu.halted is True
    assert machine.psg_writes == 1
    assert machine.vdp_read_status == 1
    assert machine.io_reads == 1
    assert cpu.pc >= 7



@pytest.mark.parametrize("target", ("sega_master_system", "sega_game_gear"))
def test_real_vdp_scanline_counter_drives_devkitsms_boot_without_fake_io(target):
    """Real SDK startup waits for B0 then C8 on port 7E before touching CRAM.

    The old constant-FF fake port made valid cartridges spin forever even
    though native SDCC builds and 256-action C differential replays passed.
    """
    machine=Sega8Machine(bytes(32768),target=target)
    assert machine.read_port(0x7E)==0
    assert machine.vcounter_b0_seen is False
    assert machine.vcounter_c8_seen is False
    for scanline in range(1,263):
        # Account for machine clock, not I/O reads; repeated IN must not
        # artificially advance time or make impossible timings pass.
        for _ in range(4):
            machine.advance_tstates(57)
        expected=scanline % 262
        if expected >= 219:
            expected=0xD5 + (expected-219)
        assert machine.read_port(0x7E)==expected
    assert machine.vcounter_b0_seen is True
    assert machine.vcounter_c8_seen is True
    assert machine.vcounter_reads==263
    assert machine.z80_tstates==262*228
    assert machine.vdp_writes==0 and machine.cram_writes==0
    assert machine.psg_writes==0
    for value in (0,-1,True,65,1000,3.1):
        with pytest.raises(SDCCSegaBootError,match="cycle"):
            machine.advance_tstates(value)
    assert machine.read_port(0x7E)==0


@pytest.mark.parametrize("target", ("sega_master_system", "sega_game_gear"))
def test_real_z80_instruction_clock_advances_vcounter_without_polling(target):
    z80_python=pytest.importorskip("z80_python")
    program=bytes((0x00,0x00,0x00,0x00,0x76))
    machine=Sega8Machine(program+bytes(32768-len(program)),target=target)
    cpu=z80_python.Z80CPU(
        machine.read,machine.write,
        read_port=machine.read_port,write_port=machine.write_port,
    )
    cpu.pc=0
    for _ in range(5):
        machine.advance_tstates(cpu.step())
    assert cpu.halted is True
    assert machine.z80_tstates>=20
    assert machine.vcounter_reads==0
    assert machine.vcounter==0
    assert machine.interrupts_issued==0
