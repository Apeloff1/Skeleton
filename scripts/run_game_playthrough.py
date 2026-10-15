#!/usr/bin/env python3
"""Operator-run native libretro playthrough with durable resumable receipts.

No ROM/core/BIOS download, no hidden automation, no unverified game mastery,
no model-weight promotion. Native game completion is only an operator-defined
watch; an exhausted controller tape is never reported as a game victory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.qualify_game_emulator import _read_operator_source


def main(argv: list[str] | None = None) -> int:
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, REGISTRY_ENV
    from skeleton.jeeves.game_emulator_host import create_emulator_environment
    from skeleton.jeeves.game_emulator_playthrough import (
        load_playthrough_plan, run_native_full_playthrough,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True, help="Installed approved core registry")
    parser.add_argument("--target", required=True, help="Exact registered console target")
    parser.add_argument("--core", required=True, help="Installed approved core ID")
    parser.add_argument("--source", type=Path, required=True, help="Operator-authorized local ROM/homebrew source")
    parser.add_argument("--plan", type=Path, required=True, help="Compressed input plan JSON")
    parser.add_argument("--checkpoint-dir", type=Path, required=True, help="Private durable progress/evidence directory")
    parser.add_argument("--resume", action="store_true", help="Restore exact pinned game, plan and native savestate")
    parser.add_argument("--frames-per-step", type=int, default=1)
    parser.add_argument("--controller-device", action="append", choices=("none", "joypad", "mouse", "keyboard", "analog", "pointer"))
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="Deadline per native worker command")
    parser.add_argument("--max-run-seconds", type=float, default=3600.0, help="1–7200 wall-seconds per invocation")
    parser.add_argument("--checkpoint-every", type=int, default=4096, help="1–4096 real steps between durable savestates")
    parser.add_argument("--evidence-every", type=int, default=64, help="1–4096 real steps between detailed evidence samples")
    parser.add_argument("--rights-evidence-digest", help="Optional operator-provided SHA256 evidence identity")
    args = parser.parse_args(argv)
    try:
        if args.registry.is_symlink() or args.source.is_symlink():
            raise ValueError("Registry and source symlinks are not allowed")
        registry_path = args.registry.resolve(strict=True)
        source_path = args.source.resolve(strict=True)
        rom, filename = _read_operator_source(source_path)
        os.environ[REGISTRY_ENV] = str(registry_path)
        registry = GameEmulatorRegistry(registry_path)
        registry.resolve_core(args.core)
        plan = load_playthrough_plan(args.plan)
        with create_emulator_environment(
            args.target,
            core_id=args.core,
            expected_registry_digest=registry.registry_digest,
            rom_source=rom,
            filename=filename,
            max_steps=4096,
            frames_per_step=args.frames_per_step,
            controller_devices=args.controller_device,
            timeout_seconds=args.timeout_seconds,
        ) as environment:
            result = run_native_full_playthrough(
                environment, plan,
                checkpoint_directory=args.checkpoint_dir,
                resume=args.resume,
                checkpoint_every=args.checkpoint_every,
                evidence_every=args.evidence_every,
                max_run_seconds=args.max_run_seconds,
                rights_evidence_digest=args.rights_evidence_digest,
            )
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "status": "native_full_playthrough_rejected",
            "reason": str(exc)[:512],
            "game_success_verified": False
        }), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
