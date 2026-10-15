"""Explicit operator CLI to replay 2..30 actual ROMs across approved emulators.

One physical emulator executes at a time, selected in bounded waves of ten.
No game content is fetched, no BIOS is bundled, and neural weights are never
updated. Each local ROM is SHA-verified and checked for source-file changes.
Only <=2 MiB inline single-file ROMs are currently accepted here; larger
media must use the separately governed streamed native-disc acceptance gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.audit_game_emulator_first_boot import _read
from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry
from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
from skeleton.jeeves.game_emulator_cross_game_lab import (
    CrossGameConfig, CrossGameComparisonError,
    compare_real_emulator_games, verify_cross_game_comparison_receipt,
)

SCHEMA = "skeleton.game.operator_cross_emulator_source_manifest.v1"
MAX_MANIFEST_BYTES = 128 * 1024
MAX_INLINE_ROM_BYTES = 2 * 1024 * 1024
DEFAULT_PROGRAMS = (
    ("idle",), ("a",), ("right",), ("a_right",),
    ("a", "idle", "right"),
)


def _no_duplicates(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise CrossGameComparisonError("operator comparison manifest has duplicate JSON keys")
        record[key] = value
    return record


def _manifest(path: Path):
    payload = _read(path, MAX_MANIFEST_BYTES)
    try:
        raw = json.loads(payload, object_pairs_hook=_no_duplicates)
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise CrossGameComparisonError("source game comparison manifest JSON is invalid") from exc
    if (
        not isinstance(raw, dict)
        or set(raw) != {"schema_version", "games"}
        or raw["schema_version"] != SCHEMA
        or not isinstance(raw["games"], list)
        or not 2 <= len(raw["games"]) <= 30
    ):
        raise CrossGameComparisonError("cross-game manifest requires 2..30 exact input ROM identities")
    return _validate_cases(raw["games"])


def _validate_cases(cases):
    if not isinstance(cases, list) or not 2 <= len(cases) <= 30:
        raise CrossGameComparisonError("programmatic comparison needs 2..30 actual ROMs")
    admitted, seen = [], set()
    for row in cases:
        if (
            not isinstance(row, dict)
            or set(row) != {
                "source_kind", "core_id", "target_id", "filename",
                "rom_path", "rom_sha256",
            }
            or row["source_kind"] not in ("original_dmg", "approved_native")
            or type(row["target_id"]) is not str or not 1 <= len(row["target_id"]) <= 128
            or type(row["filename"]) is not str or not 1 <= len(row["filename"]) <= 128
            or "/" in row["filename"] or "\\" in row["filename"]
            or row["filename"] in (".", "..")
            or type(row["rom_path"]) is not str or not 1 <= len(row["rom_path"]) <= 4096
            or type(row["rom_sha256"]) is not str or len(row["rom_sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in row["rom_sha256"])
            or row["source_kind"] == "original_dmg" and (
                row["core_id"] is not None or row["target_id"] != "game_boy"
            )
            or row["source_kind"] == "approved_native" and (
                type(row["core_id"]) is not str or not 1 <= len(row["core_id"]) <= 128
            )
        ):
            raise CrossGameComparisonError("operator ROM game requires exact safe source/target/core identity")
        name = Path(row["rom_path"])
        if not name.is_absolute() or name.is_symlink() or any(p.is_symlink() for p in name.parents):
            raise CrossGameComparisonError("comparison input must be a direct absolute non-symlink ROM source")
        identity = (row["source_kind"], row["core_id"], row["target_id"], row["rom_sha256"])
        if identity in seen:
            raise CrossGameComparisonError("repeated media cannot inflate source-game comparison coverage")
        seen.add(identity)
        admitted.append(row)
    return admitted


def run_manifest(cases, *, seed: int = 42, rights_acknowledged: bool, programs=DEFAULT_PROGRAMS):
    if rights_acknowledged is not True or not isinstance(cases, list) or not 2 <= len(cases) <= 30:
        raise CrossGameComparisonError("explicit lawful local game rights and 2..30 ROMs required")
    cases = _validate_cases(cases)
    requests = []
    registry = None
    for case in cases:
        rom = _read(Path(case["rom_path"]), MAX_INLINE_ROM_BYTES)
        if not rom or hashlib.sha256(rom).hexdigest() != case["rom_sha256"]:
            raise CrossGameComparisonError("actual local ROM differs from operator source SHA256")
        if case["source_kind"] == "original_dmg":
            requests.append(GameEnvironmentRequest(
                target_id="game_boy", kind="builtin", rom_source=rom,
                filename=case["filename"], max_steps=8, cycles_per_step=1024,
            ))
        else:
            if registry is None:
                registry = GameEmulatorRegistry.from_environment()
            requests.append(GameEnvironmentRequest(
                target_id=case["target_id"], kind="libretro",
                core_id=case["core_id"], registry_digest=registry.registry_digest,
                rom_source=rom, filename=case["filename"],
                max_steps=8, frames_per_step=1,
            ))
    result = compare_real_emulator_games(
        requests, programs, config=CrossGameConfig(seed=seed, games_per_wave=10),
        rights_acknowledged=True,
    )
    verify_cross_game_comparison_receipt(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-file", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--rights-acknowledged", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--program", action="append", default=None,
        help="Repeat for controller programs such as idle, a, right,idle,a",
    )
    args = parser.parse_args(argv)
    try:
        if not args.rights_acknowledged:
            raise CrossGameComparisonError("rights-cleared source ROM acknowledgement required")
        if (
            args.evidence_file.exists() or args.evidence_file.is_symlink()
            or args.evidence_file.resolve(strict=False) == args.manifest_file.resolve(strict=False)
            or not args.evidence_file.parent.is_dir()
        ):
            raise CrossGameComparisonError("source comparison evidence requires a new private file")
        programs = (
            DEFAULT_PROGRAMS if args.program is None
            else tuple(tuple(action.split(",")) for action in args.program)
        )
        report = run_manifest(
            _manifest(args.manifest_file), rights_acknowledged=True,
            seed=args.seed, programs=programs,
        )
        payload = json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
        if len(payload) > 2 * 1024 * 1024:
            raise CrossGameComparisonError("source comparison exceeds finite output capacity")
        fd = os.open(
            args.evidence_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        print(json.dumps({
            "status": "source_comparative_evidence_written",
            "games_replayed": report["selected_games"],
            "pairwise_comparisons": len(report["pairwise_measured_evidence"]),
            "actual_verified_comparison_steps": report["actual_source_action_steps"],
            "source_output": str(args.evidence_file),
            "native_cores_verified_universally_compatible": False,
            "neural_training_updates": 0,
        }, sort_keys=True))
        return 0
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({
            "status": "cross_emulator_comparison_rejected",
            "error": str(exc)[:600], "neural_training_updates": 0,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
