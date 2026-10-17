"""Operator CLI for create-only game-production history backup and restore.

Only canonical, sealed, segmented qualification journals are copied. The
restore command NEVER resumes the app, certifies native emulators, or renews
campaign authority. Run: python -m scripts.studio_history_recovery ...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_history_backup import (
    restore_studio_history,
    snapshot_studio_history,
    verify_studio_history_snapshot,
)


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_subparsers(dest="command", required=True)
    snap = modes.add_parser("snapshot", help="Seal a validated studio qualification history")
    snap.add_argument("--source", type=Path, required=True)
    snap.add_argument("--archive-dir", type=Path, required=True)
    snap.add_argument("--name", required=True)
    snap.add_argument("--identity", required=True)
    check = modes.add_parser("verify", help="Verify every archived history segment")
    check.add_argument("--archive-dir", type=Path, required=True)
    check.add_argument("--name", required=True)
    check.add_argument("--identity", required=True)
    restore = modes.add_parser("restore", help="Recover into a fresh independent campaign directory")
    restore.add_argument("--archive-dir", type=Path, required=True)
    restore.add_argument("--name", required=True)
    restore.add_argument("--identity", required=True)
    restore.add_argument("--destination", type=Path, required=True)
    return cli


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        if args.command == "snapshot":
            result = snapshot_studio_history(
                args.source, args.archive_dir,
                name=args.name, identity=args.identity,
            )
        elif args.command == "verify":
            result = verify_studio_history_snapshot(
                args.archive_dir, name=args.name, identity=args.identity,
            )
        else:
            result = restore_studio_history(
                args.archive_dir, args.destination,
                name=args.name, identity=args.identity,
            )
    except (ValueError, OSError, RuntimeError) as exc:
        cli.error(f"{type(exc).__name__}: {exc}")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
