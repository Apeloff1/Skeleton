"""Operator CLI for bounded, offline annual production backup and recovery.

Does not start workers, renew authority or treat archive evidence as e2e proof.
Run from the repository root: python -m scripts.annual_production_recovery ...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.automation.annual_backup import (
    AnnualBackupError,
    restore_annual_snapshot,
    snapshot_annual_production,
    verify_annual_snapshot,
)
from skeleton.automation.annual_production import AnnualProductionStore


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_subparsers(dest="command", required=True)
    snap = modes.add_parser("snapshot", help="Copy a live SQLite DB as a sealed, consistent archive")
    snap.add_argument("--database", type=Path, required=True)
    snap.add_argument("--archive-dir", type=Path, required=True)
    snap.add_argument("--label", required=True)
    check = modes.add_parser("verify", help="Independently verify a sealed archived image")
    check.add_argument("--archive-dir", type=Path, required=True)
    check.add_argument("--label", required=True)
    restore = modes.add_parser("restore", help="Publish a new fenced database; operator approval still required")
    restore.add_argument("--archive-dir", type=Path, required=True)
    restore.add_argument("--label", required=True)
    restore.add_argument("--destination", type=Path, required=True)
    return cli


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        if args.command == "snapshot":
            if (not args.database.is_absolute() or args.database.is_symlink()
                    or not args.database.is_file()):
                raise AnnualBackupError("existing non-symlinked absolute source database required")
            result = snapshot_annual_production(
                AnnualProductionStore(args.database),
                args.archive_dir, label=args.label,
            )
        elif args.command == "verify":
            result = verify_annual_snapshot(args.archive_dir, args.label)
        else:
            result = restore_annual_snapshot(
                args.archive_dir, args.label, args.destination,
            )
    except (ValueError, OSError, RuntimeError) as exc:
        cli.error(f"{type(exc).__name__}: {exc}")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
