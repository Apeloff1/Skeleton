"""Read-only multi-source Jeeves SDK/ROM evidence and licensing checkpoint.

Read redacted SDK snapshots (from custody_snapshot) and re-audit an on-disk
ROM inventory/rights/receipt fleet. No ROM contents or SDK bodies are copied.
This never authorizes model weights, cross-platform compatibility, or release.

Example: python -m scripts.training.joint_learning_custody \\
 --sdk-before /private/old.json --sdk-after /private/current.json \\
 --rom-root /private/roms --frozen-inventory /private/frozen.json \\
 --rom-approvals /private/approvals.json --rom-receipts /private/receipts
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.training.joint_learning_custody import audit_joint_learning_custody

MAX_JSON_BYTES = 32 * 1024 * 1024


def _pairs_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate source JSON key")
        result[key] = value
    return result


def _snapshot(path: Path) -> dict:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("SDK snapshot must be existing absolute, regular source")
    before = path.stat()
    if not 1 <= before.st_size <= MAX_JSON_BYTES:
        raise ValueError("SDK snapshot outside bounded size")
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    after = path.stat()
    if (len(raw) != before.st_size or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns):
        raise ValueError("SDK snapshot changed while reading")
    try:
        doc = json.loads(
            raw, object_pairs_hook=_pairs_without_duplicates,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite input")),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid SDK custody JSON") from exc
    if type(doc) is not dict:
        raise ValueError("SDK snapshot must be one JSON object")
    return doc


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--sdk-before", required=True, type=Path)
    cli.add_argument("--sdk-after", required=True, type=Path)
    cli.add_argument("--rom-root", required=True, type=Path)
    cli.add_argument("--frozen-inventory", required=True, type=Path)
    cli.add_argument("--rom-approvals", required=True, type=Path)
    cli.add_argument("--rom-receipts", required=True, type=Path)
    cli.add_argument("--page-limit", type=int, default=64)
    cli.add_argument("--max-pages", type=int, default=0)
    args = cli.parse_args(argv)
    try:
        result = audit_joint_learning_custody(
            _snapshot(args.sdk_before), _snapshot(args.sdk_after),
            rom_root=args.rom_root,
            frozen_inventory=args.frozen_inventory,
            rom_approvals=args.rom_approvals, rom_receipts=args.rom_receipts,
            page_limit=args.page_limit, max_pages=args.max_pages,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        cli.error(f"{type(exc).__name__}: {exc}")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
