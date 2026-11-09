"""Independent fixed-boundary SM83 arithmetic-flags oracle.

This uses REAL GameBoyMachine._alu state changes against separately computed
Z/N/H/C flag mathematics. A deterministic replay is insufficient if both
copies reproduce the same incorrect arithmetic flags: this independent
reference catches consistent CPU faults that would poison game AI signals.

No proprietary ROM content, emulator core, BIOS or production neural weights.
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
from skeleton.jeeves.game_rom_runtime import GameBoyMachine, Z, N, H, C
from scripts.audit_original_gameboy_cpu_opcodes import _cartridge

SCHEMA = "skeleton.game.original_sm83_alu_reference.v1"
BOUNDARY_VALUES = (0, 1, 2, 3, 7, 8, 15, 16, 17, 31, 63, 64, 127, 128, 129, 240, 254, 255)


class ALUOracleError(ValueError):
    pass


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _reference(operation: int, a: int, operand: int, carry: int) -> tuple[int, int]:
    if operation in (0, 1):
        n = carry if operation == 1 else 0
        full = a + operand + n
        return (
            full & 255,
            (Z if full & 255 == 0 else 0)
            | (H if (a & 15) + (operand & 15) + n > 15 else 0)
            | (C if full > 255 else 0),
        )
    if operation in (2, 3, 7):
        n = carry if operation == 3 else 0
        full = a - operand - n
        return (
            a if operation == 7 else full & 255,
            N | (Z if full & 255 == 0 else 0)
            | (H if (a & 15) < (operand & 15) + n else 0)
            | (C if full < 0 else 0),
        )
    computed = (
        a & operand if operation == 4
        else a ^ operand if operation == 5
        else a | operand
    )
    return computed, (Z if computed == 0 else 0) | (H if operation == 4 else 0)


def audit_alu_flags() -> dict:
    m = GameBoyMachine(_cartridge(0))
    cases = 0
    results = []
    for operation in range(8):
        group_cases = 0
        checked = hashlib.sha256()
        for a in BOUNDARY_VALUES:
            for value in BOUNDARY_VALUES:
                for carry in (0, 1):
                    m.a = a
                    m.f = C if carry else 0
                    expected_a, expected_f = _reference(operation, a, value, carry)
                    m._alu(operation, value)
                    if m.a != expected_a or m.f != expected_f or m.f & 15:
                        raise ALUOracleError(
                            "independent SM83 flag mismatch at "
                            f"ALU {operation}, accumulator {a}, operand {value}, "
                            f"carry {carry}: expected {expected_a:02x}/{expected_f:02x}, "
                            f"actual {m.a:02x}/{m.f:02x}"
                        )
                    checked.update(bytes((operation, a, value, carry, m.a, m.f)))
                    group_cases += 1
        cases += group_cases
        results.append({
            "operation": operation,
            "observed_real_machine_cases": group_cases,
            "bounded_reference_result_sha256": checked.hexdigest(),
            "source_arithmetic_flags_matched": True,
        })
    expected = 8 * len(BOUNDARY_VALUES) ** 2 * 2
    if cases != expected:
        raise ALUOracleError("source arithmetic boundary corpus is incomplete")
    out = {
        "schema_version": SCHEMA,
        "source": "actual_GameBoyMachine_ALU_vs_independent_reference",
        "reference_inputs": list(BOUNDARY_VALUES),
        "tested_operations": ["ADD", "ADC", "SUB", "SBC", "AND", "XOR", "OR", "CP"],
        "actual_source_flag_comparisons": cases,
        "actual_passed_alu_operations": len(results),
        "real_machine_results": results,
        "independent_hardware_flag_math_reference": True,
        "external_roms_downloaded": 0,
        "full_game_accuracy_certified": False,
        "production_model_updates": 0,
    }
    out["report_digest"] = _digest(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        p = args.evidence_file
        if p.exists() or p.is_symlink() or not p.parent.is_dir():
            raise ALUOracleError("independent ALU proof must be published to a new private local file")
        report = audit_alu_flags()
        payload = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > 64 * 1024:
            raise ALUOracleError("source flag evidence exceeded finite report capacity")
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        print(json.dumps({
            "real_alu_reference_comparisons": report["actual_source_flag_comparisons"],
            "source_ALU_flags_verified": True,
            "full_hardware_accuracy_certified": False,
            "receipt_file": str(p),
        }, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({
            "status": "original_alu_reference_failed",
            "error": str(exc)[:500],
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
