#!/usr/bin/env python3
"""Operator-only native multi-disc console boot and controller/AV qualification.

No ROM/core/firmware fetching; uses one pinned comparison study game and its
approved locally installed core. The host runs a real sandboxed libretro worker,
not a simulated platform. Never grants automatic AI training or rights clearance.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _step_report(environment, action: str) -> dict:
    transition = environment.step(action)
    frame = environment._frame
    return {
        "action": action,
        "transition_sha256": transition.transition_digest,
        "frame_sha256": frame["pixel_sha256"],
        "audio_sha256": frame["audio_sha256"],
        "audio_frames": frame["audio_frames"],
        "native_frame_calls": frame["runs"],
        "video_callbacks": frame["video_callbacks"],
        "width": frame["width"],
        "height": frame["height"],
        "rotation": frame["rotation"],
        "audio_available": frame["audio_available"],
        "gameplay_or_hardware_accuracy_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    from scripts.compare_game_study import _atomic_write, _read_json_file
    from skeleton.jeeves.game_comparison_schema import MAX_MANIFEST_BYTES, validate_study
    from skeleton.jeeves.game_comparison_media import prepare_comparison_media
    from skeleton.jeeves.game_comparison_host_preflight import inspect_native_host_runtime
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, REGISTRY_ENV
    from skeleton.jeeves.game_emulator_host import create_emulator_environment

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True,
                        help="Validated local 2–30 game comparison manifest with exact media SHA-256")
    parser.add_argument("--game", required=True, help="Game ID inside the validated study")
    parser.add_argument("--registry", type=Path, required=True, help="Approved installed core registry")
    parser.add_argument("--disc-index", type=int, required=True,
                        help="0-based preloaded image to insert after first controller steps")
    parser.add_argument("--before-steps", type=int, default=2, help="1–8 actual inputs before disc swap")
    parser.add_argument("--after-steps", type=int, default=2, help="1–8 actual inputs after disc swap")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rights-acknowledged", action="store_true",
                        help="Operator explicitly confirms rights to execute all local game media")
    parser.add_argument("--check-savestate", action="store_true",
                        help="Attempt a core-supported disc-bound state roundtrip (may reject large states)")
    args = parser.parse_args(argv)
    if not args.rights_acknowledged:
        parser.error("The native console run requires --rights-acknowledged")
    try:
        if (not 1 <= args.before_steps <= 8 or not 1 <= args.after_steps <= 8
            or type(args.disc_index) is not int or not 0 <= args.disc_index <= 31):
            raise ValueError("Console disc index or input budget exceeds bounded limits")
        if args.output_dir.is_symlink() or args.registry.is_symlink():
            raise ValueError("Console operator paths must not be symlinks")
        host = inspect_native_host_runtime(probe_sandbox=True)
        if not host["native_launch_preflight_passed"]:
            raise ValueError("Native Linux bubblewrap host launch preflight failed")
        manifest = validate_study(_read_json_file(args.study, MAX_MANIFEST_BYTES))
        matching = [game for game in manifest["games"] if game["id"] == args.game]
        if len(matching) != 1:
            raise ValueError("Requested console game is not in the canonical study")
        game = matching[0]
        if game["rights_evidence_digest"] is None:
            raise ValueError("Console study lacks the required operator rights evidence reference")
        if game.get("content_bundle") is None:
            raise ValueError("Disc-cycle qualification requires a governed multi-file media bundle")
        registry_file = args.registry.resolve(strict=True)
        registry = GameEmulatorRegistry(registry_file)
        approved = registry.resolve_core(game["core_id"])
        if game["target_id"] not in approved.target_ids:
            raise ValueError("Installed approved core has no authority for this console target")
        os.environ[REGISTRY_ENV] = str(registry_file)
        kwargs, pinned_source = prepare_comparison_media(game)
        frames = []
        with create_emulator_environment(
            game["target_id"], core_id=game["core_id"],
            expected_registry_digest=registry.registry_digest,
            controller_devices=game["controller_devices"],
            max_steps=args.before_steps + args.after_steps + 2,
            frames_per_step=game["frames_per_step"],
            timeout_seconds=args.timeout_seconds, **kwargs,
        ) as environment:
            environment.reset(game["seed"])
            boot = environment._frame
            pre = environment.disc_status()
            if not pre["supported"] or pre["image_count"] < 2:
                raise ValueError("Actual core does not expose at least two loaded disk images")
            if args.disc_index == pre["image_index"]:
                raise ValueError("Requested disc is already active; choose a different registered image")
            if args.disc_index >= pre["image_count"]:
                raise ValueError("Requested disc index exceeds actual core registered media")
            if pre["ejected"]:
                raise ValueError("Native console media starts with an unexpectedly open tray")
            for index in range(args.before_steps):
                frames.append({"phase": "before_swap",
                               **_step_report(environment, game["actions"][index % len(game["actions"])])})
            swapped = environment.swap_disc(args.disc_index)
            if not swapped["changed"]:
                raise ValueError("Native disc-selection command did not change media")
            for index in range(args.after_steps):
                frames.append({"phase": "after_swap",
                               **_step_report(environment, game["actions"][index % len(game["actions"])])})
            checkpoint = {"attempted": bool(args.check_savestate), "restored": False}
            if args.check_savestate:
                state = environment.snapshot()
                context = state.get("disc_context")
                if context is None or context["status"]["image_index"] != args.disc_index:
                    raise ValueError("Saved state lacks confirmed post-swap media identity")
                environment.restore(state)
                checkpoint = {
                    "attempted": True, "restored": True,
                    "snapshot_sha256": state["snapshot_digest"],
                    "disc_event_chain_sha256": context["disc_event_chain_sha256"],
                }
            final = environment.disc_status()
            if final["image_index"] != args.disc_index or final["ejected"]:
                raise ValueError("Console did not retain the selected media after controller inputs")
            result = {
                "schema_version": "skeleton.game.full_console_disc_cycle.v1",
                "study_id": manifest["study_id"], "game_id": game["id"],
                "target_id": game["target_id"], "core_id": game["core_id"],
                "core_sha256": environment.core.library_sha256,
                "source_media_sha256": pinned_source,
                "approved_registry_sha256": registry.registry_digest,
                "source_rights_record_sha256": game["rights_evidence_digest"],
                "source_rights_independently_certified": False,
                "worker_environment_sha256": environment.spec.environment_digest,
                "native_boot": {
                    "frame_sha256": boot["pixel_sha256"],
                    "audio_sha256": boot["audio_sha256"],
                    "width": boot["width"], "height": boot["height"],
                    "native_calls": boot["runs"],
                },
                "before_swap": pre, "after_swap": final,
                "disc_change": swapped["receipt"],
                "disc_history": environment.disc_receipts(),
                "controller_and_av_steps": frames,
                "checkpoint": checkpoint,
                "real_sandboxed_native_frames_observed": True,
                "physical_console_fidelity_verified": False,
                "gameplay_success_verified": False,
                "training_weights_changed": False,
            }
        from skeleton.jeeves.game_comparison_schema import digest
        result["report_sha256"] = digest(result)
        location = args.output_dir.resolve()
        location.mkdir(parents=True, exist_ok=True)
        report = location / ("full_console_" + game["id"] + "_disc_cycle.json")
        _atomic_write(report, json.dumps(result, indent=2, sort_keys=True, allow_nan=False).encode())
        print(json.dumps({
            "status": "real_native_multi_disc_cycle_captured",
            "game_id": game["id"], "reported_image_count": final["image_count"],
            "controller_steps": len(frames), "report": str(report),
            "receipt_sha256": result["report_sha256"],
            "model_weights_changed": False, "console_fidelity_certified": False,
        }, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "console_disc_qualification_rejected",
                          "error_type": type(exc).__name__,
                          "reason": str(exc)[:250]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
