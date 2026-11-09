"""Read-only, source-reconstructed Jeeves/Dragon emulator lens campaign audit.

The output is a BOUNDED aggregate of pending review tasks, not fabricated
Dragon observations or a model training/production certification.

Usage:
  python -m scripts.game_emulator_lens_campaign --source-report /private/lab-report.json --page-size 64
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.jeeves.game_emulator_lens_campaign import (
    assemble_source_pinned_lens_campaign,
)

MAX_REPORT_BYTES = 32 * 1024 * 1024


def _no_duplicate_properties(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("duplicate source report property")
        fields[key] = value
    return fields


def source_report(path: Path) -> dict:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError("existing absolute, regular, non-symlink source report required")
    original = path.stat()
    if not 1 <= original.st_size <= MAX_REPORT_BYTES:
        raise ValueError("source report exceeds bounded size")
    with path.open("rb") as handle:
        raw = handle.read(MAX_REPORT_BYTES + 1)
    latest = path.stat()
    if (len(raw) != original.st_size
            or latest.st_ino != original.st_ino
            or latest.st_mtime_ns != original.st_mtime_ns):
        raise ValueError("source report changed during review")
    try:
        report = json.loads(
            raw, object_pairs_hook=_no_duplicate_properties,
            parse_constant=lambda x: (_ for _ in ()).throw(
                ValueError("nonfinite source value")
            ),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid training source report") from exc
    if type(report) is not dict:
        raise ValueError("training report must be one JSON object")
    return report


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source-report", required=True, type=Path)
    cli.add_argument("--page-size", default=64, type=int)
    args = cli.parse_args(argv)
    try:
        result = assemble_source_pinned_lens_campaign(
            source_report(args.source_report), page_size=args.page_size,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        cli.error(f"{type(exc).__name__}: {exc}")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
