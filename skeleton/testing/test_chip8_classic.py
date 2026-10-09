"""Adversarial classic CHIP-8 CPU/timers/memory/quirks regression suite."""
from __future__ import annotations

import hashlib

import pytest

from skeleton.ai.runtime.chip8_machine import (
    Chip8Error, Chip8Machine, Chip8Quirks, FONT_ADDR,
)


def vm(*instructions: int, quirks: Chip8Quirks | None = None,
       seed: int = 0xC801) -> Chip8Machine:
    rom = b"".join(x.to_bytes(2, "big") for x in instructions)
    return Chip8Machine(rom, quirks=quirks, random_seed=seed)


def test_classic_alu_add_carry_subtract_borrow_and_register_logic():
    machine = vm(0x60FE, 0x6103, 0x8014)
    for _ in range(3):
        machine.step()
    assert machine.v[0] == 1 and machine.v[15] == 1

    machine = vm(0x6001, 0x6103, 0x8015)
    for _ in range(3):
        machine.step()
    assert machine.v[0] == 254 and machine.v[15] == 0
    machine = vm(0x6001, 0x6103, 0x8017)
    for _ in range(3):
        machine.step()
    assert machine.v[0] == 2 and machine.v[15] == 1

    for op, expected in ((0x8010, 0x0F), (0x8011, 0xFF),
                         (0x8012, 0x00), (0x8013, 0xFF)):
        machine = vm(0x60F0, 0x610F, op)
        for _ in range(3):
            machine.step()
        assert machine.v[0] == expected


def test_classic_shift_quirks_are_explicit_not_silently_platform_inferred():
    for quirk, expect in ((Chip8Quirks(), 2), (Chip8Quirks(shift_uses_vy=True), 3)):
        machine = vm(0x6004, 0x6107, 0x8016, quirks=quirk)
        for _ in range(3):
            machine.step()
        assert machine.v[0] == expect
        assert machine.v[15] == (0 if expect == 2 else 1)
    machine = vm(0x6081, 0x800E)
    machine.step()
    machine.step()
    assert machine.v[0] == 2 and machine.v[15] == 1


def test_u8_immediate_add_wrap_and_branches():
    machine = vm(0x60FF, 0x7002, 0x3001, 0x6109, 0x6102)
    machine.step()
    machine.step()
    assert machine.v[0] == 1
    machine.step()
    assert machine.pc == 0x208  # SE skips one instruction
    machine.step()
    assert machine.v[1] == 2
    machine = vm(0x6001, 0x6102, 0x9010, 0x6204, 0x6205)
    for _ in range(3):
        machine.step()
    assert machine.pc == 0x208
    machine.step()
    assert machine.v[2] == 5


def test_call_return_stack_and_fail_closed_overflow():
    machine = vm(0x2206, 0x600F, 0x120A, 0x600A, 0x00EE, 0x120A)
    machine.step()
    assert machine.pc == 0x206 and len(machine.stack) == 1
    machine.step()
    assert machine.v[0] == 0x0A
    machine.step()
    assert machine.pc == 0x202 and machine.stack == []
    machine.step()
    assert machine.v[0] == 15
    with pytest.raises(Chip8Error, match="without"):
        vm(0x00EE).step()
    recursive = vm(0x2200)
    for _ in range(16):
        recursive.step()
    with pytest.raises(Chip8Error, match="stack"):
        recursive.step()


def test_bcd_register_store_and_restore_and_strict_address_bounds():
    machine = vm(0x60FF, 0xA300, 0xF033)
    for _ in range(3):
        machine.step()
    assert bytes(machine.memory[0x300:0x303]) == b"\x02\x05\x05"

    machine = vm(0x6007, 0x6108, 0xA300, 0xF155,
                 0x6000, 0x6100, 0xA300, 0xF165)
    for _ in range(8):
        machine.step()
    assert machine.v[:2] == [7, 8]
    assert machine.i == 0x300
    machine = vm(0x6007, 0x6108, 0xA300, 0xF155,
                 quirks=Chip8Quirks(increment_i_after_transfer=True))
    for _ in range(4):
        machine.step()
    assert machine.i == 0x302
    bad = vm(0xAFFF, 0xF033)
    bad.step()
    with pytest.raises(Chip8Error, match="BCD"):
        bad.step()


def test_font_glyphs_are_locally_authored_and_xor_collision_works():
    machine = vm(0x6000, 0x6100, 0x620A, 0xF229, 0xD015, 0xD015)
    for _ in range(4):
        machine.step()
    assert machine.i == FONT_ADDR + 5 * 10
    assert machine.memory[machine.i] != 0
    first = machine.step()
    assert first["lit_pixels"] > 0 and machine.v[15] == 0
    last = machine.step()
    assert last["lit_pixels"] == 0 and machine.v[15] == 1


def test_held_key_skip_wait_and_false_key_admission():
    machine = vm(0x6004, 0xE09E, 0x6101, 0x6102, 0xF20A)
    machine.set_keys({4})
    machine.step()
    machine.step()
    assert machine.pc == 0x206
    machine.step()
    assert machine.v[1] == 2
    result = machine.step()
    assert result["registers"][2] == 4
    assert result["waiting_for_key"] is False
    with pytest.raises(Chip8Error):
        machine.set_keys({16})
    with pytest.raises(Chip8Error):
        machine.set_keys({True})
    with pytest.raises(Chip8Error):
        machine.set_keys([4])


def test_timer_ticks_do_not_claim_wall_clock_or_real_cosmac_vip_cycle_accuracy():
    machine = vm(0x6005, 0xF015, 0x6003, 0xF018, 0xF007)
    for _ in range(4):
        machine.step()
    assert machine.delay_timer == 5 and machine.sound_timer == 3
    assert machine.tick_60hz(frames=2) == {
        "delay_timer": 3, "sound_timer": 1,
        "sound_active": True, "hardware_cycle_accuracy_claimed": False,
    }
    assert machine.tick_60hz(frames=3)["sound_active"] is False
    machine.step()
    assert machine.v[0] == 0
    with pytest.raises(Chip8Error):
        machine.tick_60hz(frames=0)
    with pytest.raises(Chip8Error):
        machine.tick_60hz(frames=True)


def test_deterministic_randomness_is_not_cryptographic_or_global_state():
    def values(seed):
        machine = vm(0xC0FF, 0xC1FF, 0xC2F0, seed=seed)
        for _ in range(3):
            machine.step()
        return machine.v[:3]
    assert values(1) == values(1)
    assert values(1) != values(2)
    assert values(1)[2] & 15 == 0
    with pytest.raises(Chip8Error):
        vm(0xC0FF, seed=True)
    with pytest.raises(Chip8Error):
        vm(0xC0FF, seed=-1)


def test_jump_with_v0_offset_and_memory_safe_execution():
    machine = vm(0x6002, 0xB204, 0x6101, 0x6103)
    machine.step()
    machine.step()
    assert machine.pc == 0x206
    machine.step()
    assert machine.v[1] == 3
    with pytest.raises(Chip8Error):
        vm(0x1FFF).step()


def test_unsupported_new_variants_are_declined_not_claimed_as_compatible():
    for code in (0x00FD, 0xF030, 0xD010, 0x8008, 0x5001):
        with pytest.raises(Chip8Error):
            vm(code).step()


def test_legacy_generated_chip8_game_still_uses_canonical_vm_exactly():
    from scripts.game.export_chip8 import (
        _original_capsule, compile_chip8_homebrew,
        verify_chip8_executable,
    )
    game = compile_chip8_homebrew(_original_capsule(42))
    assert verify_chip8_executable(game)["win_state_reached"] is True
    assert len(game["rom_sha256"]) == 64
