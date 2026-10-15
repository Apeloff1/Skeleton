"""Original synthetic ROM SM83 interrupt, EI/DI/HALT/RETI control oracle.

Executes real interpreter instructions, hardware IF/IE arbitration and exact
CPU/register/WRAM/PPU savestate restoration. Explicitly does not certify
CPU bus microcycle ordering or full DMG electrical timing. No downloaded ROMs.
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

from skeleton.jeeves.game_rom_runtime import GameBoyMachine
from scripts.audit_original_gameboy_cpu_opcodes import _cartridge

SCHEMA = "skeleton.game.original_lr35902_interrupt_matrix.v1"


class InterruptMatrixError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def _verify(condition: bool, label: str):
    if condition is not True:
        raise InterruptMatrixError(label)


def _machine(code: bytes) -> GameBoyMachine:
    if type(code) is not bytes or not 1 <= len(code) <= 8:
        raise InterruptMatrixError("bounded original synthetic interrupt program required")
    rom = bytearray(_cartridge(0))
    rom[0x100:0x100 + len(code)] = code
    m = GameBoyMachine(bytes(rom))
    m.sp = 0xDFF0
    m.memory[0xFFFF] = 0
    m.memory[0xFF0F] = 0
    return m


def _replay(name, m, operation, validator):
    before = m.snapshot()
    cycles = operation(m)
    validator(m, cycles)
    after = m.snapshot()
    m.restore(before)
    second_cycles = operation(m)
    validator(m, second_cycles)
    if cycles != second_cycles or m.snapshot() != after:
        raise InterruptMatrixError(f"{name}: real interrupt/CPU state did not replay exactly")
    return {
        "probe": name,
        "actual_execution_cycles": cycles,
        "actual_source_before_sha256": _digest(before),
        "actual_source_after_sha256": _digest(after),
        "replayed_source_after_sha256": _digest(m.snapshot()),
        "real_interrupt_replay_passed": True,
        "hardware_bus_cycle_certified": False,
    }


def _irq_arbitration(bit: int):
    m = _machine(b"\x00")
    pending = sum(1 << i for i in range(bit, 5))
    m.pc = 0x2345
    m.ime = True
    m.memory[0xFFFF] = 31
    m.memory[0xFF0F] = pending

    def run(core):
        return core.instruction()

    def check(core, cycles):
        _verify(cycles == 20, f"IRQ priority {bit}: interrupt service must cost 20 T-cycles")
        _verify(core.pc == 0x40 + 8 * bit, f"IRQ priority {bit}: vector differs")
        _verify(core.sp == 0xDFEE, f"IRQ priority {bit}: stack push missing")
        _verify(core.read(0xDFEE) == 0x45 and core.read(0xDFEF) == 0x23, f"IRQ priority {bit}: return address is corrupt")
        _verify(core.memory[0xFF0F] & 31 == pending & ~(1 << bit), f"IRQ priority {bit}: wrong IF bit cleared")
        _verify(core.ime is False and core.ime_delay == 0, f"IRQ priority {bit}: IME remained enabled")

    return _replay(f"priority_vector_{bit}", m, run, check)


def _ei_delay():
    m = _machine(bytes((0xFB, 0x00, 0x00)))
    m.memory[0xFFFF] = 1
    m.memory[0xFF0F] = 1
    def op(core):
        first = core.instruction()
        _verify(first == 4 and core.pc == 0x101 and not core.ime
                and core.ime_delay == 1, "EI must not enable IRQ until following instruction completes")
        second = core.instruction()
        _verify(second == 4 and core.pc == 0x102 and core.ime,
                "EI did not enable after the next actual CPU instruction")
        third = core.instruction()
        return first + second + third

    def check(core, cycles):
        _verify(cycles == 28 and core.pc == 0x40 and core.sp == 0xDFEE,
                "delayed EI failed to vector only after the next source instruction")
        _verify(core.read(0xDFEE) == 0x02 and core.read(0xDFEF) == 0x01,
                "delayed EI returned to wrong original cartridge PC")

    return _replay("ei_one_instruction_delay", m, op, check)


def _di_after_ei():
    m = _machine(bytes((0xFB, 0xF3, 0x00)))
    m.memory[0xFFFF] = 1
    m.memory[0xFF0F] = 1
    def op(core):
        return core.instruction() + core.instruction() + core.instruction()

    def check(core, cycles):
        _verify(cycles == 12 and core.pc == 0x103 and core.ime is False
                and core.ime_delay == 0 and core.memory[0xFF0F] & 1,
                "DI failed to cancel pending EI or incorrectly serviced IRQ")

    return _replay("di_cancels_pending_ei", m, op, check)


def _halt_bug():
    m = _machine(bytes((0x76, 0x3E, 0x42)))
    m.memory[0xFFFF] = 1
    m.memory[0xFF0F] = 1
    def op(core):
        first = core.instruction()
        _verify(first == 4 and core.halt_bug is True and core.halted is False,
                "HALT bug not entered with pending interrupt and IME off")
        second = core.instruction()
        return first + second

    def check(core, cycles):
        _verify(cycles == 12 and core.a == 0x3E and core.pc == 0x102
                and core.halt_bug is False and core.ime is False,
                "HALT bug failed to reuse opcode byte as immediate next fetch")

    return _replay("halt_bug_duplicate_opcode_byte", m, op, check)


def _halt_wake():
    m = _machine(bytes((0x76, 0x00)))
    m.ime = True
    m.memory[0xFFFF] = 1
    def op(core):
        first = core.instruction()
        _verify(first == 4 and core.halted is True, "HALT with no IRQ did not enter sleeping state")
        core.memory[0xFF0F] = 1
        second = core.instruction()
        return first + second

    def check(core, cycles):
        _verify(cycles == 24 and core.halted is False and core.pc == 0x40
                and core.sp == 0xDFEE and not core.ime and not core.memory[0xFF0F] & 1,
                "HALT failed to service the newly pending IRQ from real source state")

    return _replay("halt_wake_immediate_irq", m, op, check)


def _reti():
    m = _machine(b"\xD9")
    m.memory[0xDFF0] = 0x56
    m.memory[0xDFF1] = 0xC0
    def op(core):
        return core.instruction()

    def check(core, cycles):
        _verify(cycles == 16 and core.pc == 0xC056 and core.sp == 0xDFF2
                and core.ime and core.ime_delay == 0, "RETI did not restore PC and immediately enable IME")

    return _replay("reti_stack_and_immediate_ime", m, op, check)


def _joypad_wake():
    m = _machine(bytes((0x10, 0x00, 0x00)))
    def op(core):
        before = core.instruction()
        _verify(before == 4 and core.stopped, "STOP did not freeze original oscillator")
        divider = core.divider
        core.instruction()
        _verify(core.stopped and core.divider == divider, "STOP oscillator advanced despite missing joypad input")
        core.write(0xFF00, 0x10)
        core.set_buttons(("a",))
        _verify(not core.stopped and core.memory[0xFF0F] & 0x10, "physical joypad failed to raise IF and wake CPU")
        return before + 4

    def check(core, cycles):
        _verify(cycles == 8 and core.pc == 0x102 and not core.stopped
                and core.memory[0xFF0F] & 0x10, "STOP joypad wake evidence differs")

    return _replay("stop_frozen_until_joypad_edge", m, op, check)


def audit_interrupt_matrix() -> dict:
    scenarios = [_irq_arbitration(index) for index in range(5)]
    scenarios += [_ei_delay(), _di_after_ei(), _halt_bug(), _halt_wake(), _reti(), _joypad_wake()]
    if len(scenarios) != 11 or any(not s["real_interrupt_replay_passed"] for s in scenarios):
        raise InterruptMatrixError("source interrupt vector and instruction-control corpus incomplete")
    result = {
        "schema_version": SCHEMA,
        "status": "original_cpu_interrupt_control_replayed",
        "source": "original_synthetic_ROM_real_GameBoyMachine",
        "priority_vectors_tested": [0x40, 0x48, 0x50, 0x58, 0x60],
        "actual_independently_replayed_scenarios": len(scenarios),
        "physical_state_executions": len(scenarios) * 2,
        "source_scenarios": scenarios,
        "cpu_interrupt_hardware_bus_phase_certified": False,
        "production_neural_weights_updated": 0,
    }
    result["report_digest"] = _digest(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        p = args.evidence_file
        if p.exists() or p.is_symlink() or not p.parent.is_dir():
            raise InterruptMatrixError("source interrupt evidence requires new private file and existing parent")
        report = audit_interrupt_matrix()
        payload = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        if len(payload) > 64 * 1024:
            raise InterruptMatrixError("source interrupt report exceeds finite capacity")
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        print(json.dumps({"status": report["status"], "actual_replayed_interrupt_scenarios": report["actual_independently_replayed_scenarios"], "hardware_bus_phase_certified": False}))
        return 0
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "source_interrupt_oracle_failed", "error": str(exc)[:600]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
