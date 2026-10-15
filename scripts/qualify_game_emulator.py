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


def main(argv: list[str] | None = None) -> int:
    from skeleton.jeeves.game_emulator_catalog import (
        GameEmulatorRegistry, REGISTRY_ENV,
    )
    from skeleton.jeeves.game_emulator_host import _ACTIONS, _KEY_ACTIONS
    from skeleton.jeeves.game_emulator_qualification import run_emulator_qualification

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True, help="Approved local cores.json (no download)")
    parser.add_argument("--target", required=True, help="Canonical hardware target ID")
    parser.add_argument("--core", required=True, help="Explicit approved libretro core ID")
    parser.add_argument("--source", type=Path, required=True, help="Local 1–16 MiB lawful ROM/homebrew data")
    parser.add_argument("--action", action="append", required=True, choices=sorted((*_ACTIONS, *_KEY_ACTIONS)))
    parser.add_argument("--runs", type=int, default=3, help="2–10 independent isolated worker sessions")
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
        result = run_emulator_qualification(
            args.target,
            core_id=args.core,
            expected_registry_digest=registry.registry_digest,
            rom_source=source,
            filename=name,
            actions=args.action,
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
