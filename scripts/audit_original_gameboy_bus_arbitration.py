"""CPU-only DMG VRAM/OAM/DMA bus ownership source acceptance gate.

Executes independently generated original ROM instructions from ROM/HRAM,
tests blocked external writes, video memory mode windows, sprite DMA source
progression and exact full machine savestate rewind. Rejects any trace that
claims unsupported DMG bus electrical timing or full hardware fidelity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skeleton.jeeves.game_rom_runtime import GameBoyMachine, GameRomRuntimeError
from scripts.audit_original_gameboy_cpu_opcodes import _cartridge

SCHEMA = "skeleton.game.original_dmg_cpu_bus_arbitration.v1"


class OriginalBusError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _check(ok, label):
    if not ok:
        raise OriginalBusError(label)


def _machine(opcode=0x7E):
    rom = bytearray(_cartridge(0x00))
    rom[0x100] = opcode
    return GameBoyMachine(bytes(rom))


def _cpu_step(machine, address, pc=0x100, opcode=0x7E):
    machine._set_pair(2, address)
    machine.pc = pc
    if pc >= 0xFF80:
        machine.memory[pc] = opcode
    return machine.instruction()


def _video_probe(address, phase, opcode, lcd_on=True):
    m = _machine(opcode)
    m.a = 0xA3
    m.memory[address] = 0x72
    m.line_cycles = phase
    m.memory[0xFF44] = 0
    if not lcd_on:
        m.memory[0xFF40] &= ~0x80
    _cpu_step(m, address)
    return m.a if opcode == 0x7E else m.memory[address]


def audit_original_bus_arbitration() -> dict:
    checks = []
    def checked(label, result):
        _check(result, label)
        checks.append(label)

    m = _machine()
    m.memory[0xC000] = 0x53
    m.memory[0xC010] = 0x6A
    m.memory[0xFF80] = 0x7E  # Original HRAM LD A,(HL)
    m.write(0xFF46, 0xC0)
    checked("source_DMA_not_instantaneous", m.memory[0xFE00] == 0)
    _cpu_step(m, 0xC010, 0xFF80)
    checked("active_DMA_CPU_external_WRAM_read_is_open_bus", m.a == 0xFF)
    checked("real_DMA_reads_WRAM_on_clock_tcycles", m.memory[0xFE00] == 0x53)
    checked("real_CPU_bus_context_does_not_leak", m._cpu_bus_active is False)

    m.pc = 0xFF80
    m.memory[0xFF80] = 0x77  # LD (HL),A
    m.a = 0x7D
    _cpu_step(m, 0xC010, 0xFF80, 0x77)
    checked("active_DMA_CPU_WRAM_write_ignored", m.memory[0xC010] == 0x6A)

    m.pc = 0xFF80
    m.memory[0xFF90] = 0xA5
    _cpu_step(m, 0xFF90, 0xFF80, 0x7E)
    checked("active_DMA_CPU_HRAM_read_allowed", m.a == 0xA5)
    m.a = 0x5C
    _cpu_step(m, 0xFF90, 0xFF80, 0x77)
    checked("active_DMA_CPU_HRAM_write_allowed", m.memory[0xFF90] == 0x5C)

    m.pc = 0x0100
    try:
        m.instruction()
    except GameRomRuntimeError:
        checks.append("unmodeled_external_opcode_fetch_fails_closed")
    else:
        raise OriginalBusError("inaccessible CPU ROM fetch during OAM DMA was treated as valid gameplay")
    checked("illegal_dma_fetch_did_not_leak_CPU_bus_flag", m._cpu_bus_active is False)

    tests = (
        ("PPU_VRAM_mode2_access_allowed", 0x8000, 20, 0x7E, True, 0x72),
        ("PPU_VRAM_mode3_read_blocked", 0x8000, 100, 0x7E, True, 0xFF),
        ("PPU_VRAM_mode0_read_allowed", 0x8000, 300, 0x7E, True, 0x72),
        ("PPU_OAM_mode2_read_blocked", 0xFE00, 20, 0x7E, True, 0xFF),
        ("PPU_OAM_mode3_read_blocked", 0xFE00, 100, 0x7E, True, 0xFF),
        ("PPU_OAM_mode0_read_allowed", 0xFE00, 300, 0x7E, True, 0x72),
        ("PPU_VRAM_mode3_write_ignored", 0x8000, 100, 0x77, True, 0x72),
        ("PPU_OAM_mode2_write_ignored", 0xFE00, 20, 0x77, True, 0x72),
        ("LCDC_off_VRAM_write_allowed", 0x8000, 100, 0x77, False, 0xA3),
        ("LCDC_off_OAM_write_allowed", 0xFE00, 20, 0x77, False, 0xA3),
    )
    for label, address, phase, instruction, lcd, expected in tests:
        checked(label, _video_probe(address, phase, instruction, lcd) == expected)

    rewind = _machine()
    rewind.memory[0xC000] = 0xE2
    rewind.pc = 0xFF80
    rewind.memory[0xFF80] = 0x00
    rewind.write(0xFF46, 0xC0)
    rewind._advance(35)
    before = rewind.snapshot()
    rewind._advance(400)
    after = rewind.snapshot()
    rewind.restore(before)
    rewind._advance(400)
    checked("inflight_OAM_DMA_full_replay_identical", rewind.snapshot() == after)
    checked("clocked_DMA_source_original_rom_or_WRAM", rewind.memory[0xFE00] == 0xE2)

    result = {
        "schema_version": SCHEMA,
        "status": "original_DMG_source_bus_arbitration_passed",
        "source": "real_GameBoyMachine_CPU_HRAM_video_and_DMA_source",
        "synthetic_original_cartridges_only": True,
        "actual_CPU_memory_and_DMA_reference_checks": len(checks),
        "tested_source_bus_constraints": checks,
        "cpu_dma_hram_only": True,
        "cpu_video_ppu_mode_lockout": True,
        "real_DMA_and_PPU_source_memories_unblocked": True,
        "exact_inflight_DMA_savestate_replay": True,
        "machine_rom_digest": m.metadata["rom_digest"],
        "source_video_timing_dot_perfect": False,
        "cpu_DMA_interrupt_bus_microcycles_certified": False,
        "production_model_weights_updated": False,
    }
    result["report_digest"] = _digest(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path = args.evidence_file
        if path.exists() or path.is_symlink() or not path.parent.is_dir():
            raise OriginalBusError("source bus receipt must be a new file under existing parent")
        result = audit_original_bus_arbitration()
        payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
        if len(payload) > 65536:
            raise OriginalBusError("CPU bus evidence exceeds source-bound capacity")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        print(json.dumps({
            "status": result["status"],
            "real_CPU_dma_video_checks": result["actual_CPU_memory_and_DMA_reference_checks"],
            "receipt": str(path),
            "certified_hardware_accuracy": False,
        }))
        return 0
    except (ValueError, TypeError, RuntimeError, OSError) as exc:
        print(json.dumps({"status": "original_CPU_bus_source_rejected", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
