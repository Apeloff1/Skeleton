#!/usr/bin/env python3
"""Rights-gated native console save-RAM backup and optional cold resume.

Uses a real, approved sandboxed libretro core and rights-cleared game media.
Writes raw SAVE_RAM region 0 into an operator-local private file and a separate
core/content/firmware-bound SHA-256 manifest. It does not prove in-game saves
work; many consoles store saves in opaque core-specific memory-card files.
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
MAX_RAM = 8 * 1024 * 1024


def _read_private_save(path: Path) -> bytes:
    from skeleton.jeeves.game_comparison_media import _open_no_symlink
    fd = _open_no_symlink(str(path))
    try:
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or not 1 <= first.st_size <= MAX_RAM:
            raise ValueError("Private SRAM must be a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(MAX_RAM + 1)
        last = os.fstat(fd)
        if (len(data) != first.st_size
            or (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
            != (last.st_dev, last.st_ino, last.st_size, last.st_mtime_ns)):
            raise ValueError("Saved RAM source mutated during local read")
        return data
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    from scripts.compare_game_study import _atomic_write, _read_json_file
    from skeleton.jeeves.game_comparison_schema import MAX_MANIFEST_BYTES, validate_study
    from skeleton.jeeves.game_comparison_media import prepare_comparison_media
    from skeleton.jeeves.game_comparison_host_preflight import inspect_native_host_runtime
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, REGISTRY_ENV
    from skeleton.jeeves.game_emulator_host import create_emulator_environment

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, type=Path,
                        help="Rights-cleared study with pinned game media and source SHA-256")
    parser.add_argument("--game", required=True, help="Exact game ID in study")
    parser.add_argument("--registry", type=Path, required=True,
                        help="Approved native libretro core manifest")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=4,
                        help="0–32 actual native game input steps before exporting")
    parser.add_argument("--resume-metadata", type=Path,
                        help="Optional earlier matching SRAM checkpoint JSON")
    parser.add_argument("--resume-save-ram", type=Path,
                        help="Optional earlier matching raw SRAM file")
    parser.add_argument("--verify-fresh-resume", action="store_true",
                        help="Boot a second core instance to verify raw imported bytes on a new worker")
    parser.add_argument("--rights-acknowledged", action="store_true")
    args = parser.parse_args(argv)
    if not args.rights_acknowledged:
        parser.error("Native console operation requires --rights-acknowledged")
    try:
        if (args.resume_metadata is None) != (args.resume_save_ram is None):
            raise ValueError("Provide both SRAM metadata and raw SRAM or neither")
        if not 0 <= args.steps <= 32:
            raise ValueError("Native SRAM capture input steps must be 0–32")
        if args.registry.is_symlink() or args.output_dir.is_symlink():
            raise ValueError("Operator output and registry paths cannot be symlinks")
        preflight = inspect_native_host_runtime(probe_sandbox=True)
        if not preflight["native_launch_preflight_passed"]:
            raise ValueError("Approved Linux Bubblewrap native execution preflight failed")
        study = validate_study(_read_json_file(args.study, MAX_MANIFEST_BYTES))
        rows = [item for item in study["games"] if item["id"] == args.game]
        if len(rows) != 1:
            raise ValueError("Game not found in pinned comparison study")
        game = rows[0]
        if game["rights_evidence_digest"] is None:
            raise ValueError("Required operator rights evidence reference is missing")
        registry_file = args.registry.resolve(strict=True)
        registry = GameEmulatorRegistry(registry_file)
        core = registry.resolve_core(game["core_id"])
        if game["target_id"] not in core.target_ids:
            raise ValueError("Approved core does not support declared study hardware target")
        os.environ[REGISTRY_ENV] = str(registry_file)
        media, source_digest = prepare_comparison_media(game)
        checkpoint = None
        source = None
        if args.resume_metadata:
            checkpoint = _read_json_file(args.resume_metadata, 128 * 1024)
            source = _read_private_save(args.resume_save_ram)
        def create():
            return create_emulator_environment(
                game["target_id"], core_id=game["core_id"],
                expected_registry_digest=registry.registry_digest,
                controller_devices=game["controller_devices"],
                max_steps=max(1, args.steps + 1),
                frames_per_step=game["frames_per_step"], timeout_seconds=5.0,
                **media,
            )
        with create() as environment:
            imported = (
                environment.import_save_ram(checkpoint, source)
                if checkpoint is not None else None
            )
            environment.reset(game["seed"])
            frame_evidence = []
            for i in range(args.steps):
                step = environment.step(game["actions"][i % len(game["actions"])])
                frame = environment._frame
                frame_evidence.append({
                    "index": i + 1, "input_action": game["actions"][i % len(game["actions"])],
                    "transition_sha256": step.transition_digest,
                    "frame_sha256": frame["pixel_sha256"],
                    "audio_sha256": frame["audio_sha256"],
                    "audio_frames": frame["audio_frames"],
                })
            metadata, ram = environment.export_save_ram()
            native_env_sha = environment.spec.environment_digest
        cold_resume = {"attempted": False, "verified": False}
        if args.verify_fresh_resume:
            with create() as resumed:
                cold_import = resumed.import_save_ram(metadata, ram)
                reexported, bytes_again = resumed.export_save_ram()
                if (not cold_import["native_ram_write_verified"]
                    or reexported["save_ram_sha256"] != metadata["save_ram_sha256"]
                    or bytes_again != ram):
                    raise ValueError("Fresh native worker SRAM readback did not match saved content")
                resumed.reset(game["seed"])
                post_reset, post_reset_bytes = resumed.export_save_ram()
                if (post_reset["save_ram_sha256"] != metadata["save_ram_sha256"]
                    or post_reset_bytes != ram):
                    raise ValueError("Fresh core reset replaced or modified the restored SRAM bytes")
                cold_resume = {
                    "attempted": True, "verified": True,
                    "survived_native_reset": True,
                    "cold_environment_sha256": resumed.spec.environment_digest,
                    "reset_frame_sha256": resumed._frame["pixel_sha256"],
                    "hardware_save_compatibility_verified": False,
                }
        report = {
            "schema_version": "skeleton.game.console_sram_operator_report.v1",
            "game_id": game["id"], "study_id": study["study_id"],
            "target_id": game["target_id"], "core_id": game["core_id"],
            "source_media_sha256": source_digest,
            "source_rights_digest": game["rights_evidence_digest"],
            "native_environment_sha256": native_env_sha,
            "restored_before_first_reset": imported,
            "native_input_frames": frame_evidence,
            "checkpoint": metadata, "fresh_worker_readback": cold_resume,
            "save_data_rights_verified": False,
            "game_save_load_behavior_qualified": False,
            "model_weights_updated": False,
        }
        from skeleton.jeeves.game_comparison_schema import digest
        report["report_sha256"] = digest(report)
        folder = args.output_dir.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        out_ram = folder / (game["id"] + ".srm")
        out_meta = folder / (game["id"] + ".sram.metadata.json")
        out_report = folder / (game["id"] + ".sram.report.json")
        _atomic_write(out_ram, ram)
        _atomic_write(out_meta, json.dumps(metadata, sort_keys=True, indent=2).encode())
        _atomic_write(out_report, json.dumps(report, sort_keys=True, indent=2, allow_nan=False).encode())
        print(json.dumps({
            "status": "native_save_ram_exported",
            "checkpoint_sha256": metadata["checkpoint_sha256"],
            "save_ram_sha256": metadata["save_ram_sha256"],
            "byte_count": metadata["byte_count"],
            "report": str(out_report), "checkpoint": str(out_meta),
            "raw_sram": str(out_ram),
            "fresh_worker_readback_verified": cold_resume["verified"],
            "hardware_game_save_compatibility_proven": False,
        }, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "native_console_sram_rejected",
                          "exception": type(exc).__name__, "reason": str(exc)[:250]}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
