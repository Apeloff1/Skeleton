"""Manual synthetic LR35902 opcode execution and savestate equality audit.

Executes all 245 legal base opcodes and 256 CB-prefixed instructions in the
actual project GameBoyMachine and verifies exactly repeated state from the
same CPU/memory/raster snapshot. Invalid opcodes must fail, never silently
contribute falsely interpreted training transitions.

This is an instruction coverage / deterministic replay proof, NOT cycle-
accurate hardware certification or a commercial-title compatibility test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skeleton.jeeves.game_rom_runtime import GameBoyMachine, GameRomRuntimeError

SCHEMA = "skeleton.game.original_lr35902_opcode_matrix.v1"
INVALID_BASE = frozenset((
    0xD3, 0xDB, 0xDD, 0xE3, 0xE4, 0xEB, 0xEC, 0xED,
    0xF4, 0xFC, 0xFD,
))


class OpcodeMatrixError(ValueError):
    pass


def _json_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _cartridge(opcode: int, cb: int | None = None) -> bytes:
    """Source-own 32 KiB ROM with a single instruction and benign operands."""
    if type(opcode) is not int or not 0 <= opcode <= 255:
        raise OpcodeMatrixError("source opcode outside a byte")
    if cb is not None and (opcode != 0xCB or type(cb) is not int or not 0 <= cb <= 255):
        raise OpcodeMatrixError("CB suboperation must be a finite source opcode")
    raw = bytearray(32768)
    raw[0x100] = opcode
    # $C020 is a valid WRAM destination for immediate 16-bit addresses.
    # Relative and 8-bit immediates remain bounded for the single step.
    raw[0x101:0x103] = bytes((cb, 0) if cb is not None else (0x20, 0xC0))
    raw[0x134:0x13C] = b"OPCODETX"
    raw[0x147] = 0
    raw[0x148] = 0
    raw[0x149] = 0
    checksum = 0
    for byte in raw[0x134:0x14D]:
        checksum = (checksum - byte - 1) & 255
    raw[0x14D] = checksum
    return bytes(raw)


@lru_cache(maxsize=1)
def _reference_table() -> dict:
    path = ROOT / "machine" / "gbdev_sm83_opcode_reference.json"
    with path.open("rb") as reader:
        source = json.load(reader)
    if (
        source.get("schema_version") != "skeleton.game.gbdev_sm83_opcode_reference.v1"
        or source.get("provenance", {}).get("upstream_commit_sha")
        != "376f61c86fdac2048f7ce5fe838ae756b306017e"
        or source["provenance"].get("license") != "CC0-1.0"
        or any(len(source.get(group, {})) != 256 for group in ("unprefixed", "cbprefixed"))
    ):
        raise OpcodeMatrixError("pinned CC0 independent SM83 reference missing or changed")
    return source


def _expected_reference(opcode: int, cb: int | None, flags: int) -> tuple[int, int, str]:
    group = "cbprefixed" if cb is not None else "unprefixed"
    index = cb if cb is not None else opcode
    reference = _reference_table()[group]["0x" + format(index, "02X")]
    cycles = reference["cycles"]
    if not isinstance(cycles, list) or not 1 <= len(cycles) <= 2:
        raise OpcodeMatrixError("opcode reference has invalid timings")
    if len(cycles) == 1:
        expected = cycles[0]
    else:
        # gbdev lists taken/not-taken T-cycles for conditionals. Source
        # flags are explicitly captured BEFORE this real instruction.
        z = bool(flags & 0x80)
        carry = bool(flags & 0x10)
        if opcode in (0x20, 0x28, 0x30, 0x38):
            which = (opcode - 0x20) // 8
        else:
            which = (opcode >> 3) & 3
        taken = (not z, z, not carry, carry)[which]
        expected = cycles[0 if taken else 1]
    if (
        type(expected) is not int or expected not in (4, 8, 12, 16, 20, 24)
        or type(reference.get("bytes")) is not int
        or not 1 <= reference["bytes"] <= 3
    ):
        raise OpcodeMatrixError("SM83 sourced reference instruction length or cycles invalid")
    return expected, reference["bytes"], reference["mnemonic"]


def _result(opcode: int, cb: int | None = None) -> dict:
    cart = _cartridge(opcode, cb)
    machine = GameBoyMachine(cart)
    machine.sp = 0xDFF0
    machine._set_pair(2, 0xC010)
    machine.memory[0xC010] = 0x81
    machine.memory[0xC020] = 0xA6
    original = machine.snapshot()
    reference_cycles, reference_bytes, mnemonic = _expected_reference(
        opcode, cb, machine.f
    )
    first_error = None
    try:
        first_cycles = machine.instruction()
        first = machine.snapshot()
    except GameRomRuntimeError as exc:
        first_error = exc
        first_cycles, first = None, None
    if opcode in INVALID_BASE:
        if first_error is None:
            raise OpcodeMatrixError(f"illegal source opcode {opcode:02x} executed instead of being refused")
        if "Unsupported/invalid opcode" not in str(first_error):
            raise OpcodeMatrixError(
                f"illegal opcode {opcode:02x} failed for unrelated reason: {str(first_error)[:100]}"
            )
        return {
            "opcode": opcode,
            "cb": None,
            "expected_invalid_opcode_rejected": True,
            "real_instruction_executed": False,
        }
    if first_error is not None:
        raise OpcodeMatrixError(
            f"documented valid opcode {opcode:02x} CB={cb} failed: {first_error}"
        ) from first_error
    if (
        type(first_cycles) is not int
        or first_cycles != reference_cycles
        or first["registers"]["instructions"] != original["registers"]["instructions"] + 1
        or first["registers"]["cycles"] - original["registers"]["cycles"] != first_cycles
        or first["rom_digest"] != original["rom_digest"]
    ):
        raise OpcodeMatrixError("original CPU instruction accounting or cycle bound is inconsistent")
    machine.restore(original)
    repeated_cycles = machine.instruction()
    repeated = machine.snapshot()
    if first_cycles != repeated_cycles or first != repeated:
        raise OpcodeMatrixError(f"original CPU opcode {opcode:02x} CB={cb} was not exactly replayable")
    return {
        "opcode": opcode,
        "cb": cb,
        "real_instruction_executed": True,
        "emulated_t_cycles": first_cycles,
        "reference_documented_t_cycles": reference_cycles,
        "reference_documented_instruction_bytes": reference_bytes,
        "reference_documented_mnemonic": mnemonic,
        "source_reference_cycles_verified": True,
        "actual_source_rom_sha256": hashlib.sha256(cart).hexdigest(),
        "source_registers_after_sha256": _digest(first["registers"]),
        "source_snapshot_after_sha256": _digest(first),
        "repeated_snapshot_sha256": _digest(repeated),
        "real_independent_replay_executed": True,
        "hardware_reference_cycle_accurate": False,
    }


def audit_cpu_opcode_matrix() -> dict:
    base = [_result(opcode) for opcode in range(256) if opcode != 0xCB]
    prefixed = [_result(0xCB, opcode) for opcode in range(256)]
    if (
        len(base) != 255 or len(prefixed) != 256
        or sum(bool(row["real_instruction_executed"]) for row in base) != 244
        or sum(bool(row["real_instruction_executed"]) for row in prefixed) != 256
        or sum(bool(row.get("expected_invalid_opcode_rejected")) for row in base) != 11
    ):
        raise OpcodeMatrixError("actual original LR35902 decoder coverage is incomplete")
    result = {
        "schema_version": SCHEMA,
        "status": "all_documented_opcodes_executed_and_replayed",
        "actual_legal_base_opcodes": 245,  # Includes one CB dispatch itself
        "actual_base_opcode_single_step_executed": 244,
        "actual_cb_prefix_expansions_executed": len(prefixed),
        "expected_illegal_base_opcodes_rejected": 11,
        "actual_total_single_step_source_replays": (244 + len(prefixed)) * 2,
        "original_generated_synthetic_cartridges": True,
        "external_sm83_reference_commit": _reference_table()["provenance"]["upstream_commit_sha"],
        "source_reference_opcodes_compared_to_actual_timing": 500,
        "base_instruction_receipts": base,
        "prefixed_instruction_receipts": prefixed,
        "hardware_instruction_cycle_accuracy_independently_proven": False,
        "native_libretro_corpus_tested": False,
        "production_jeeves_weights_modified": False,
    }
    result["report_digest"] = _digest(result)
    if len(_json_bytes(result)) > 512 * 1024:
        raise OpcodeMatrixError("bounded CPU opcode coverage receipt exceeded capacity")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        path = args.evidence_file
        if path.exists() or path.is_symlink() or not path.parent.is_dir():
            raise OpcodeMatrixError("create-only original opcode evidence requires an existing parent")
        report = audit_cpu_opcode_matrix()
        payload = _json_bytes(report) + b"\n"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        print(json.dumps({
            "status": report["status"],
            "real_opcodes_single_stepped_and_replayed": report["actual_total_single_step_source_replays"],
            "illegal_cpu_opcodes_refused": report["expected_illegal_base_opcodes_rejected"],
            "hardware_accuracy_certified": False,
            "receipt_file": str(path),
        }, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({
            "status": "original_opcode_coverage_rejected",
            "failure": str(exc)[:500],
            "hardware_accuracy_certified": False,
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
