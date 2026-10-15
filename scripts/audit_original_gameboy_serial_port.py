"""Source-executed original DMG serial register and timing acceptance.

Each probe boots a synthetic authored cartridge instruction stream, actually
writes SB and SC from CPU opcodes, then runs the CPU/HALT oscillator to
complete (internal clock) or hold (external clock) and replay the full
machine savestate from the identical mid-transfer cycle boundary.
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

from scripts.audit_original_gameboy_cpu_opcodes import _cartridge
from skeleton.jeeves.game_rom_runtime import GameBoyMachine

SCHEMA = "skeleton.game.original_dmg_serial_source_proof.v1"


class SerialProofError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def _cpu_program(data: int, control: int) -> GameBoyMachine:
    rom = bytearray(_cartridge(0))
    rom[0x100:0x109] = bytes((
        0x3E, data, 0xE0, 0x01,
        0x3E, control, 0xE0, 0x02,
        0x76,
    ))
    return GameBoyMachine(bytes(rom))


def _run(control: int):
    core = _cpu_program(0x6A, control)
    actual_source_cpu_cycles = 0
    for ordinal in range(4):
        elapsed = core.instruction()
        actual_source_cpu_cycles += elapsed
        if ordinal == 3 and elapsed != 12:
            raise SerialProofError("source serial-starting LDH opcode has unexpected cycles")
    # The fourth opcode writes SC *before* _advance(12) runs, so 12 serial
    # T-cycles have already elapsed when the following HALT begins. Avoid
    # inventing a 2048T halfway point by ignoring the launch instruction.
    start_opcode_serial_cycles = elapsed
    halfway_idle_instructions = (2048 - start_opcode_serial_cycles - 4) // 4
    if start_opcode_serial_cycles + 4 + halfway_idle_instructions * 4 != 2048:
        raise SerialProofError("source HALT cannot align to serial bit boundary")
    if (
        core.memory[0xFF01] != 0x6A
        or core.memory[0xFF02] != control
        or core.serial_active is not True
        or core.pc != 0x108
    ):
        raise SerialProofError("original source opcode program did not start DMG serial transfer")
    beginning = core.snapshot()
    if core.instruction() != 4 or not core.halted:
        raise SerialProofError("original source HALT did not preserve clocked serial bus")
    for _ in range(halfway_idle_instructions):
        core.instruction()
    midpoint = core.snapshot()
    if control == 0x81:
        if core.serial_bits != 4 or core.serial_phase != 0:
            raise SerialProofError("4096-cycle disconnected serial transfer not halfway after 2048T")
    elif core.serial_bits or core.serial_phase:
        raise SerialProofError("external clock without attached peer fabricated serial bits")
    for _ in range(512):
        core.instruction()
    first_finish = core.snapshot()
    if control == 0x81:
        if (
            core.memory[0xFF01] != 255 or core.memory[0xFF02] & 0x80
            or not core.memory[0xFF0F] & 8 or core.serial_active
        ):
            raise SerialProofError("original internal serial transfer did not finish at exactly 4096T")
    elif (
        not core.memory[0xFF02] & 0x80 or core.memory[0xFF01] != 0x6A
        or core.memory[0xFF0F] & 8 or not core.serial_active
    ):
        raise SerialProofError("disconnected external serial clock falsely reported game-link completion")
    core.restore(midpoint)
    for _ in range(512):
        core.instruction()
    if core.snapshot() != first_finish:
        raise SerialProofError("real original serial CPU/HALT replay differs from saved completed state")
    return {
        "mode": "DMG_internal_disconnected" if control == 0x81 else "DMG_external_unclocked",
        "CPU_started_actual_SB_SC_writes": 4,
        "actual_cpu_clock_advance_instructions": 1 + halfway_idle_instructions + 512,
        "source_program_cpu_instruction_calls": 4 + 1 + halfway_idle_instructions + 512,
        "serial_start_opcode_clocked_tcycles": start_opcode_serial_cycles,
        "hardware_clock_t_cycles_observed": 4096,
        "source_ROM_SHA256": core.metadata["rom_digest"],
        "source_initial_snapshot_sha256": _digest(beginning),
        "source_midpoint_snapshot_sha256": _digest(midpoint),
        "source_finished_snapshot_sha256": _digest(first_finish),
        "source_replayed_snapshot_sha256": _digest(core.snapshot()),
        "serial_interrupt_set": bool(core.memory[0xFF0F] & 8),
        "serial_SC_still_active": core.serial_active,
        "serial_final_SB": core.memory[0xFF01],
        "exact_source_cpu_replay": True,
    }


def audit_serial_port() -> dict:
    trials = [_run(0x81), _run(0x80)]
    if not (len(trials) == 2
            and trials[0]["serial_interrupt_set"] is True
            and trials[0]["serial_final_SB"] == 255
            and trials[0]["serial_SC_still_active"] is False
            and trials[1]["serial_SC_still_active"] is True
            and trials[1]["serial_interrupt_set"] is False
            and all(x["source_finished_snapshot_sha256"] == x["source_replayed_snapshot_sha256"]
                    for x in trials)):
        raise SerialProofError("source real internal/external link clock experiment incomplete")
    report = {
        "schema_version": SCHEMA,
        "status": "original_DMG_disconnected_serial_source_replayed",
        "original_owned_source_ROM_only": True,
        "real_serial_cpu_modes": 2,
        "actual_cpu_oscillator_steps": sum(
            trial["actual_cpu_clock_advance_instructions"] for trial in trials
        ),
        "actual_original_cpu_instruction_calls": sum(
            trial["source_program_cpu_instruction_calls"] for trial in trials
        ),
        "real_source_trials": trials,
        "hardware_serial_bit_cycles": 512,
        "unattached_external_link_peer_fabricated": False,
        "interconsole_link_gameplay_verified": False,
        "production_neural_model_updated": False,
    }
    report["report_digest"] = _digest(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path = args.evidence_file
        if path.exists() or path.is_symlink() or not path.parent.is_dir():
            raise SerialProofError("new private serial source evidence path and existing parent required")
        result = audit_serial_port()
        encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
        if len(encoded) > 65536:
            raise SerialProofError("source serial report capacity exceeded")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(encoded)
            file.flush()
            os.fsync(file.fileno())
        print(json.dumps({"status": result["status"], "CPU_oscillator_steps": result["actual_cpu_oscillator_steps"], "hardware_accuracy": False, "evidence_file": str(path)}))
        return 0
    except (ValueError, TypeError, RuntimeError, OSError) as exc:
        print(json.dumps({"status": "serial_source_probe_failed", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
