#!/usr/bin/env python3
"""Explicit operator-run, bounded real libretro replay qualification.

No source/core/firmware acquisition, no sample game, no mock execution,
no automatic learning, and no production model weight changes. Input is a
small operator-owned ROM/homebrew file checked against an approved registry.
Large/disc-based content must use the existing governed content descriptors.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _read_operator_source(path: Path) -> tuple[bytes, str]:
    from skeleton.jeeves.game_emulator_catalog import MAX_CONTENT_BYTES

    if path.is_symlink():
        raise ValueError("Operator ROM source must not be a symlink")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        first = os.fstat(descriptor)
        if not stat.S_ISREG(first.st_mode) or not 1 <= first.st_size <= MAX_CONTENT_BYTES:
            raise ValueError("Operator source must be a nonempty bounded regular file")
        with os.fdopen(os.dup(descriptor), "rb") as source:
            data = source.read(MAX_CONTENT_BYTES + 1)
        second = os.fstat(descriptor)
        if (
            len(data) != first.st_size
            or (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns)
            != (second.st_dev, second.st_ino, second.st_size, second.st_mtime_ns)
        ):
            raise ValueError("ROM bytes changed during bounded operator source admission")
        return data, path.name
    finally:
        os.close(descriptor)

def _read_controller_tape(path: Path) -> list:
    """Read an exact bounded JSON-only four-port input tape, rejecting duplicate keys."""
    if path.is_symlink():
        raise ValueError("Controller tape may not be a symlink")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 2 <= before.st_size <= 128 * 1024:
            raise ValueError("Controller tape JSON exceeds its bounded file size")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(128 * 1024 + 1)
        after = os.fstat(fd)
        if (len(raw) != before.st_size or
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError("Controller tape changed while being read")
    finally:
        os.close(fd)

    def pairs(items):
        parsed = {}
        for key, value in items:
            if key in parsed:
                raise ValueError("Controller tape contains duplicate JSON keys")
            parsed[key] = value
        return parsed

    def invalid(value):
        raise ValueError("Nonfinite controller coordinates are forbidden")

    tape = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    if not isinstance(tape, list) or not 1 <= len(tape) <= 64:
        raise ValueError("Controller tape must be a JSON list of 1–64 input frames")
    from skeleton.jeeves.game_emulator_host import _controls

    return [_controls(frame) for frame in tape]


def main(argv: list[str] | None = None) -> int:
    from skeleton.jeeves.game_emulator_catalog import (
        GameEmulatorRegistry, REGISTRY_ENV,
    )
    from skeleton.jeeves.game_emulator_host import _ACTIONS, _KEY_ACTIONS
    from skeleton.jeeves.game_emulator_qualification import run_emulator_qualification
    from skeleton.jeeves.game_emulator_exploration import run_emulator_exploration

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True, help="Approved local cores.json (no download)")
    parser.add_argument("--target", required=True, help="Canonical hardware target ID")
    parser.add_argument("--core", required=True, help="Explicit approved libretro core ID")
    parser.add_argument("--source", type=Path, required=True, help="Local 1–16 MiB lawful ROM/homebrew data")
    tape_group = parser.add_mutually_exclusive_group(required=True)
    tape_group.add_argument("--action", action="append", choices=sorted((*_ACTIONS, *_KEY_ACTIONS)))
    tape_group.add_argument("--controller-tape-json", type=Path, help="Explicit 1–64 step JSON input tape for four-player button/axis/key/mouse/pointer controls")
    parser.add_argument("--runs", type=int, default=3, help="2–10 independent isolated worker sessions per scenario")
    parser.add_argument("--explore-scenarios", type=int, help="Explicit bounded deterministic boomerang exploration, 2–80 total scenarios")
    parser.add_argument("--stagnation-window", type=int, default=10, help="Stop exploration after 3–20 scenarios with no new audiovisual outcome (default 10)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--frames-per-step", type=int, default=1)
    parser.add_argument("--controller-device", action="append", choices=("none", "joypad", "mouse", "keyboard", "analog", "pointer"))
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--rights-evidence-digest", help="Optional operator-supplied SHA-256, not a legal certificate")
    parser.add_argument("--include-traces", action="store_true", help="Also output bounded raw native observations to stdout")
    args = parser.parse_args(argv)
    try:
        source_path = args.source.resolve(strict=True)
        if args.source.is_symlink():
            raise ValueError("A symlink ROM source cannot be accepted")
        source, name = _read_operator_source(source_path)
        if args.registry.is_symlink():
            raise ValueError("Approved operator registry cannot be a symlink")
        registry_path = args.registry.resolve(strict=True)
        registry = GameEmulatorRegistry(registry_path)
        registry.resolve_core(args.core)
        os.environ[REGISTRY_ENV] = str(registry_path)
        tape = _read_controller_tape(args.controller_tape_json) if args.controller_tape_json is not None else None
        if args.explore_scenarios is not None:
            if tape is not None:
                raise ValueError("Boomerang exploration currently requires policy actions; raw multi-port tapes use regular qualification")
            if args.include_traces:
                raise ValueError("Boomerang exploration returns bounded receipts, not large raw trace exports")
            result = run_emulator_exploration(
                args.target,
                core_id=args.core,
                expected_registry_digest=registry.registry_digest,
                rom_source=source,
                filename=name,
                actions=args.action,
                runs_per_scenario=args.runs,
                max_scenarios=args.explore_scenarios,
                stagnation_window=args.stagnation_window,
                seed=args.seed,
                frames_per_step=args.frames_per_step,
                controller_devices=args.controller_device,
                timeout_seconds=args.timeout_seconds,
                rights_evidence_digest=args.rights_evidence_digest,
            )
        else:
            result = run_emulator_qualification(
                args.target,
                core_id=args.core,
                expected_registry_digest=registry.registry_digest,
                rom_source=source,
                filename=name,
                actions=args.action,
                controller_tape=tape,
                runs=args.runs,
                seed=args.seed,
                frames_per_step=args.frames_per_step,
                controller_devices=args.controller_device,
                timeout_seconds=args.timeout_seconds,
                rights_evidence_digest=args.rights_evidence_digest,
                include_traces=args.include_traces,
            )
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "native_qualification_rejected", "reason": str(exc)[:512]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
