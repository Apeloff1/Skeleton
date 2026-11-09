"""Exercise actual LR35902 interpreter cartridge bus with authored synthetic ROMs.

This local-only audit is additional evidence about ROM bank / SRAM decode and
native interpreter savestates. It cannot certify commercial title compatibility,
hardware-cycle timing, audio, RGBDS/native binary builds or legal ROM content.

No downloaded cores, copyrighted ROMs, BIOS or network accesses. Generated
cartridge patterns, hashes and reference expectations are explicitly local.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skeleton.jeeves.game_rom_runtime import (
    GameBoyMachine, GameRomRuntimeError, RTC_CYCLES_PER_SECOND,
)


SCHEMA = "skeleton.game.original_mapper_bus_matrix.v1"
_CASES = (
    ("rom_only", 0x00, 0, 0),
    ("mbc1_large", 0x03, 5, 2),  # 1 MiB, ROM extension, 8 KiB SRAM
    ("mbc1_ram", 0x03, 4, 3),    # 512 KiB, 32 banks, 32 KiB SRAM
    ("mbc2", 0x06, 3, 0),  # 256 KiB, 16 banks, 512 internal nibbles
    ("mbc3", 0x13, 6, 3), # 2 MiB, 128 banks, 32 KiB SRAM; no RTC
    ("mbc3_timer_only", 0x0F, 2, 0),  # virtual RTC and no SRAM
    ("mbc3_timer_ram", 0x10, 2, 3),  # virtual RTC plus four SRAM banks
    ("mbc5", 0x1B, 8, 4), # 8 MiB, 512 banks, 128 KiB SRAM
)


class MapperAuditError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _rom(cartridge_type: int, size_code: int, ram_code: int) -> bytes:
    # Every bank has two synthetic marker bytes: bank's low and upper bits.
    # A real bus read of 0x4000 and 0x4001 proves the addressed full bank.
    if type(size_code) is not int or not 0 <= size_code <= 8:
        raise MapperAuditError("bounded original ROM bank count required")
    result = bytearray(32768 << size_code)
    for bank in range(len(result) // 0x4000):
        i = bank * 0x4000
        result[i], result[i + 1] = bank & 255, (bank >> 8) & 1
    result[0x134:0x13C] = b"OWNEDMBC"
    result[0x147] = cartridge_type
    result[0x148] = size_code
    result[0x149] = ram_code
    checksum = 0
    for byte in result[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 255
    result[0x14D] = checksum
    return bytes(result)


def _read_bank(machine: GameBoyMachine, expected: int) -> None:
    observed = machine.read(0x4000) | (machine.read(0x4001) << 8)
    if observed != expected:
        raise MapperAuditError(
            f"source ROM bank was {observed} but bus reference requires {expected}"
        )


def _assert(condition: bool, label: str) -> None:
    if condition is not True:
        raise MapperAuditError(label)


def _probe(label: str, kind: int, size: int, ram: int) -> dict[str, Any]:
    raw = _rom(kind, size, ram)
    source_hash = hashlib.sha256(raw).hexdigest()
    machine = GameBoyMachine(raw)
    _assert(machine.metadata["rom_digest"] == source_hash, "source cartridge SHA256 identity changed")
    expected_type = (
        "mbc1" if label.startswith("mbc1_")
        else "mbc3" if label.startswith("mbc3_")
        else label
    )
    _assert(machine.metadata["mapper"] == expected_type, "source emulator mapper type resolution differs")
    checkpoints = []

    def check(name: str, condition: bool) -> None:
        _assert(condition, f"{label}:{name}")
        checkpoints.append(name)

    check("initial_bank_one", machine.read(0x4000) == 1)
    if label == "rom_only":
        check("bank_zero_at_rom0", machine.read(0x0000) == 0)
        check("ram_not_declared", machine.metadata["ram_bytes"] == 0)
        check("ignored_mapper_write", (machine.write(0x2100, 3) is None
                                       and machine.read(0x4000) == 1))
    elif label in ("mbc1_large", "mbc1_ram"):
        machine.write(0x2000, 4)
        _read_bank(machine, 4)
        check("rom_bank_four", True)
        machine.write(0x4000, 1)
        if label == "mbc1_large":
            _read_bank(machine, 36)
            check("upper_rom_bank_bits", True)
            machine.write(0x6000, 1)
            check("bank_mode_changes_rom0", machine.read(0x0000) == 32)
            machine.write(0x0000, 0x0A)
            machine.write(0xA023, 0x79)
            machine.write(0x4000, 0)
            check("single_ram_bank_without_fake_32K_SRAM", machine.read(0xA023) == 0x79)
        else:
            # 512 KiB cart ignores upper ROM selector bits after physical
            # address masking, but can wire them to four SRAM banks.
            _read_bank(machine, 4)
            check("rom_bank_high_masked_by_512K_cart", True)
            machine.write(0x6000, 1)
            check("ram_mode_uses_rom_bank_zero", machine.read(0x0000) == 0)
            machine.write(0x0000, 0x0A)
            machine.write(0xA023, 0x79)
            machine.write(0x4000, 0)
            check("ram_switch_avoids_overwrite", machine.read(0xA023) == 0)
            machine.write(0x4000, 1)
            check("ram_bank_restored", machine.read(0xA023) == 0x79)
    elif label == "mbc2":
        check("512_internal_half_bytes", machine.metadata["ram_bytes"] == 512)
        machine.write(0x2000, 7)
        _read_bank(machine, 1)
        check("A8_clear_does_not_select_rom_bank", True)
        machine.write(0x2100, 7)
        _read_bank(machine, 7)
        check("A8_set_selects_bank_seven", True)
        check("disabled_ram_reads_open_bus", machine.read(0xA123) == 0xFF)
        machine.write(0x0100, 10)
        check("A8_set_cannot_enable_internal_ram", machine.read(0xA123) == 0xFF)
        machine.write(0x0000, 10)
        machine.write(0xA123, 0xBC)
        check("four_bit_readback", machine.read(0xA123) == 0xFC)
        check("internal_half_kib_mirror", machine.read(0xB323) == 0xFC)
        machine.write(0x0000, 0)
        check("internal_ram_disable", machine.read(0xA123) == 0xFF)
        machine.write(0x0000, 10)
        check("internal_ram_persists", machine.read(0xA123) == 0xFC)
    elif label == "mbc3":
        machine.write(0x2000, 127)
        _read_bank(machine, 127)
        check("seven_bit_rom_bank", True)
        machine.write(0x2000, 0)
        _read_bank(machine, 1)
        check("zero_bank_maps_to_one", True)
        machine.write(0x0000, 10)
        machine.write(0x4000, 3)
        machine.write(0xA123, 0xCD)
        machine.write(0x4000, 0)
        check("ram_banks_independent", machine.read(0xA123) == 0)
        machine.write(0x4000, 3)
        check("selected_ram_restored", machine.read(0xA123) == 0xCD)
        try:
            machine.write(0x4000, 8)
        except GameRomRuntimeError:
            checkpoints.append("RTC_register_rejected")
        else:
            raise MapperAuditError("unsupported MBC3 clock latch was falsely accepted")
    elif label in ("mbc3_timer_only", "mbc3_timer_ram"):
        check("virtual_cpu_cycle_rtc_only", machine.metadata["virtual_rtc"] is True)
        machine.write(0x0000, 10)
        machine.write(0x4000, 8)
        machine.write(0xA000, 58)
        machine.write(0x6000, 0)
        machine.write(0x6000, 1)
        check("latched_seconds_are_58", machine.read(0xA000) == 58)
        machine._rtc_advance(3 * RTC_CYCLES_PER_SECOND)
        check("source_latch_remains_stable", machine.read(0xA000) == 58)
        machine.write(0x6000, 0)
        machine.write(0x6000, 1)
        check("seconds_wrap_after_CPU_clock", machine.read(0xA000) == 1)
        machine.write(0x4000, 9)
        check("minute_advances", machine.read(0xA000) == 1)
        machine.write(0x4000, 12)
        machine.write(0xA000, 0x40)
        old_clock = tuple(machine.rtc_regs)
        machine._rtc_advance(5 * RTC_CYCLES_PER_SECOND)
        check("RTC_halt_disables_virtual_ticks", tuple(machine.rtc_regs) == old_clock)
        machine.write(0xA000, 0)
        machine._rtc_advance(RTC_CYCLES_PER_SECOND)
        check("RTC_resume_works", machine.rtc_regs[0] == 2)
        if label == "mbc3_timer_only":
            machine.write(0x4000, 0)
            check("timer_only_has_no_external_SRAM", machine.read(0xA123) == 255)
        else:
            machine.write(0x4000, 3)
            machine.write(0xA123, 0xB7)
            machine.write(0x4000, 0)
            check("timer_board_RAM_banks_independent", machine.read(0xA123) == 0)
            machine.write(0x4000, 3)
            check("timer_board_RAM_bank_restored", machine.read(0xA123) == 0xB7)
    elif label == "mbc5":
        machine.write(0x2000, 0)
        machine.write(0x3000, 1)
        _read_bank(machine, 256)
        check("ninth_rom_address_bit", True)
        machine.write(0x2000, 255)
        _read_bank(machine, 511)
        check("highest_512_bank", True)
        machine.write(0x2000, 0)
        machine.write(0x3000, 0)
        _read_bank(machine, 0)
        check("bank_zero_is_addressable", True)
        machine.write(0x0000, 10)
        machine.write(0x4000, 15)
        machine.write(0xA123, 0xD5)
        machine.write(0x4000, 0)
        check("ram_banks_independent", machine.read(0xA123) == 0)
        machine.write(0x4000, 15)
        check("last_ram_bank_preserved", machine.read(0xA123) == 0xD5)
    else:
        raise MapperAuditError("unsupported source mapper diagnostic was requested")
    # Exact CPU/register/bus/sprite snapshots, not simulated state labels.
    checkpoint = machine.snapshot()
    before = _digest(checkpoint)
    saved_bank = (machine.read(0x4000), machine.read(0x4001))
    saved_ram = machine.read(0xA123)
    machine.write(0x2100, 2)
    machine.write(0xA123, 0x0D)
    machine.restore(checkpoint)
    after = _digest(machine.snapshot())
    check("exact_snapshot_roundtrip", after == before)
    check("bank_after_restore", saved_bank == (
        machine.read(0x4000), machine.read(0x4001),
    ))
    check("RAM_after_restore", machine.read(0xA123) == saved_ram)
    receipt = {
        "mapper": label,
        "actual_mapper_type": expected_type,
        "cartridge_type": kind,
        "original_rom_sha256": source_hash,
        "actual_source_rom_banks": machine.metadata["rom_banks"],
        "actual_mapper_ram_bytes": machine.metadata["ram_bytes"],
        "verified_register_and_memory_cases": checkpoints,
        "real_source_bus_checks": len(checkpoints),
        "actual_memory_cpu_savestate_roundtrip": True,
        "hardware_cycle_accuracy_certified": False,
        "real_native_libretro_core_tested": False,
        "commercial_rom_compatibility_certified": False,
    }
    receipt["receipt_digest"] = _digest(receipt)
    return receipt


def audit_mapper_matrix() -> dict[str, Any]:
    items = [_probe(label, code, size, ram) for label, code, size, ram in _CASES]
    if len(items) != 8 or any(not item["actual_memory_cpu_savestate_roundtrip"] for item in items):
        raise MapperAuditError("not all eight original cartridge/RTC profiles completed source bus checks")
    result = {
        "schema_version": SCHEMA,
        "status": "original_cartridge_mapper_bus_checks_passed",
        "source_original_cartridge_only": True,
        "mapped_cartridge_categories": ["rom_only", "mbc1", "mbc2", "mbc3", "mbc5"],
        "tested_actual_mapper_categories": 5,
        "tested_bank_geometry_profiles": len(items),
        "verified_source_bus_checks": sum(x["real_source_bus_checks"] for x in items),
        "mapper_results": items,
        "original_game_ROMs_downloaded": 0,
        "native_libretro_hardware_certified": False,
        "independent_cycle_exact_certification": False,
        "production_model_weights_updated": 0,
    }
    result["report_digest"] = _digest(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.evidence_file.exists() or args.evidence_file.is_symlink():
            raise MapperAuditError("source mapper report file must be new")
        if not args.evidence_file.parent.is_dir():
            raise MapperAuditError("mapper report parent directory must already exist")
        report = audit_mapper_matrix()
        payload = _canonical(report) + b"\n"
        if len(payload) > 256 * 1024:
            raise MapperAuditError("ROM hardware mapper result exceeds source result bound")
        fd = os.open(args.evidence_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        print(json.dumps({
            "status": report["status"],
            "mapped_categories": report["tested_actual_mapper_categories"],
            "verified_bank_geometry_profiles": report["tested_bank_geometry_profiles"],
            "real_source_bus_checks": report["verified_source_bus_checks"],
            "report_file": str(args.evidence_file),
            "hardware_accuracy_certified": False,
        }, sort_keys=True))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps({
            "status": "source_mapper_matrix_rejected",
            "reason": str(exc)[:500],
            "hardware_accuracy_certified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
