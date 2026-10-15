#!/usr/bin/env python3
"""Operator comparative native-game study: plan <=30, run <=10 at once, view notes.

Explicit --run requires the existing operator-approved game-emulator registry.
Plan-only mode never opens ROMs, loads binaries or runs a model. Outputs a
shared JSON report, standalone HTML viewer and pending Dragon intake envelope.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read_json_file(path: Path, max_bytes: int):
    from skeleton.jeeves.game_comparison_schema import ComparativeStudyError, parse_json

    if path.is_symlink():
        raise ComparativeStudyError("Manifest or viewer-notes source must not be a symlink")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= max_bytes:
            raise ComparativeStudyError("JSON source exceeds bounded regular-file size")
        with os.fdopen(os.dup(fd), "rb") as source:
            data = source.read(max_bytes + 1)
        after = os.fstat(fd)
        if (len(data) != before.st_size or
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ComparativeStudyError("JSON source changed during admission")
    finally:
        os.close(fd)
    return parse_json(data, limit=max_bytes)


def _notes_into_manifest(manifest: dict, packet: object) -> dict:
    from skeleton.jeeves.game_comparison_schema import validate_note, ComparativeStudyError

    if not isinstance(packet, dict) or set(packet) != {"schema_version", "study_id", "notes"}:
        raise ComparativeStudyError("Notes file is not a valid standalone viewer/Dragon review packet")
    if packet["schema_version"] != "skeleton.game.comparison_notes.v1" or packet["study_id"] != manifest["study_id"]:
        raise ComparativeStudyError("Note ownership/study digest scope mismatch")
    data = packet["notes"]
    if not isinstance(data, list) or len(data) > 1500:
        raise ComparativeStudyError("Viewer/Dragon notes exceed 1500 entries")
    existing = {note["note_id"]: note for note in manifest["notes"]}
    known_games = {game["id"] for game in manifest["games"]}
    for raw in data:
        note = validate_note(raw, game_ids=known_games)
        prior = existing.get(note["note_id"])
        if prior is not None and prior != note:
            raise ComparativeStudyError("Viewer note ID conflicts with an existing version; review the correction explicitly")
        existing[note["note_id"]] = note
    if len(existing) > 1500:
        raise ComparativeStudyError("Merged notes exceed the bounded study limit")
    return {**manifest, "notes": list(existing.values())}


def _atomic_write(path: Path, data: bytes) -> None:
    if not 1 <= len(data) <= 32 * 1024 * 1024:
        raise ValueError("Result output exceeds its bounded file size")
    if path.exists() and path.is_symlink():
        raise ValueError("Refusing to replace a symlink evidence output")
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".comparative-", delete=False) as file:
        tmp = Path(file.name)
        try:
            os.fchmod(file.fileno(), 0o600)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    from skeleton.jeeves.game_comparison_schema import (
        ComparativeStudyError, MAX_MANIFEST_BYTES, plan_study, validate_study,
    )
    from skeleton.jeeves.game_comparison_studio import run_comparative_study
    from skeleton.jeeves.game_comparison_viewer import render_comparison_html
    from skeleton.ai.webcrawler.dragon_comparative_game_bridge import (
        export_dragon_comparison_intake,
    )
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, REGISTRY_ENV

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="Exact comparative 2–30-game study JSON")
    parser.add_argument("--notes-json", type=Path, help="Optional user/Dragon notes exported from the HTML viewer")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for user+AI evidence outputs")
    parser.add_argument("--run", action="store_true", help="Actually launch approved libretro workers, never simulated sessions")
    parser.add_argument("--registry", type=Path, help="Approved existing cores.json; required only with --run")
    parser.add_argument("--batch", type=int, help="0-based 10-game-or-smaller execution cohort; omit to run all batches sequentially")
    parser.add_argument("--without-previews", action="store_true", help="Do not embed screenshots in report/viewer")
    parser.add_argument("--train-shadow-policy", action="store_true", help="Explicitly train independent study-local tabular Q policies from actual native traces, never production LLM weights")
    parser.add_argument("--rights-acknowledged", action="store_true", help="Operator asserts legal rights to perform this study-local training; not independent license verification")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        if args.run != (args.registry is not None):
            raise ComparativeStudyError("Native --run must be paired with --registry; plan-only cannot have registry")
        if not args.run and args.batch is not None:
            raise ComparativeStudyError("Batch selection applies only to explicit native execution")
        if args.train_shadow_policy and (
            not args.run or not args.rights_acknowledged
            or args.batch is None or not args.without_previews
        ):
            raise ComparativeStudyError("Study-local training requires --run --batch N --without-previews --train-shadow-policy --rights-acknowledged")
        if args.rights_acknowledged and not args.train_shadow_policy:
            raise ComparativeStudyError("Rights training acknowledgement only applies to explicit study-local training")
        manifest = _read_json_file(args.manifest, MAX_MANIFEST_BYTES)
        manifest = validate_study(manifest)
        if args.notes_json is not None:
            notes = _read_json_file(args.notes_json, MAX_MANIFEST_BYTES)
            manifest = validate_study(_notes_into_manifest(manifest, notes))
        plan = plan_study(manifest)
        if args.output_dir.is_symlink():
            raise ComparativeStudyError("Output destination cannot be a symlink")
        destination = args.output_dir.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        if not destination.is_dir() or destination.is_symlink():
            raise ComparativeStudyError("Output destination is not a safe ordinary local directory")
        name = manifest["study_id"]
        _atomic_write(destination / (name + ".plan.json"), json.dumps(plan, indent=2, sort_keys=True).encode())
        if not args.run:
            print(json.dumps({
                "status": "bounded_study_planned_not_executed",
                "study_id": name,
                "planned_games": plan["game_count"],
                "batches": len(plan["batches"]),
                "pair_count": plan["pair_count"],
                "plan_path": str(destination / (name + ".plan.json")),
                "native_emulator_runs": 0,
                "training_weights_changed": False,
            }, indent=2))
            return 0
        if args.registry.is_symlink():
            raise ComparativeStudyError("Operator registry may not be a symlink")
        registry = GameEmulatorRegistry(args.registry.resolve(strict=True))
        os.environ[REGISTRY_ENV] = str(args.registry.resolve(strict=True))
        if registry.registry_digest != GameEmulatorRegistry.from_environment().registry_digest:
            raise ComparativeStudyError("Actual approved registry changed before the comparative run")
        def authorize_training():
            if not args.train_shadow_policy or not args.rights_acknowledged:
                raise PermissionError("Operator did not explicitly authorize study-local learning")
            if GameEmulatorRegistry.from_environment().registry_digest != registry.registry_digest:
                raise PermissionError("Actual libretro registry authority changed during training")

        result = run_comparative_study(
            manifest, selected_batch=args.batch,
            include_previews=not args.without_previews,
            shadow_policy_training=args.train_shadow_policy,
            authorize_training=authorize_training if args.train_shadow_policy else None,
            timeout_seconds=args.timeout_seconds,
        )
        _atomic_write(destination / (name + ".result.json"), json.dumps(result, indent=2, sort_keys=True, allow_nan=False).encode())
        viewer = render_comparison_html(result)
        _atomic_write(destination / (name + ".viewer.html"), viewer.encode("utf-8"))
        dragon = export_dragon_comparison_intake(result)
        _atomic_write(destination / (name + ".dragon-intake.json"), json.dumps(dragon, indent=2, sort_keys=True).encode())
        print(json.dumps({
            "status": "comparative_native_execution_completed_with_evidence_and_failures",
            "study_id": name,
            "sessions_attempted": result["actual_game_sessions_attempted"],
            "games_with_real_observations": result["game_observations_completed"],
            "maximum_parallel_game_sessions": result["maximum_parallel_native_game_sessions"],
            "pair_count": len(result["pairs"]),
            "note_count": len(result["observer_notes"]),
            "reviewed_knowledge_candidates": dragon["observer_card_count"],
            "games_with_local_q_policy_updates": result["games_with_study_local_q_updates"],
            "report_path": str(destination / (name + ".result.json")),
            "viewer_path": str(destination / (name + ".viewer.html")),
            "dragon_intake_path": str(destination / (name + ".dragon-intake.json")),
            "model_weights_changed": False,
        }, indent=2))
        return 0 if result["game_observations_completed"] == result["actual_game_sessions_attempted"] else 3
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "comparative_study_rejected", "type": type(exc).__name__, "message": str(exc)[:512]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
