#!/usr/bin/env python3
"""Merge existing evidence reports for large game series; no ROM execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    from scripts.compare_game_study import _read_json_file, _atomic_write
    from skeleton.jeeves.game_comparison_series_ledger import (
        merge_comparative_series, SeriesLedgerError,
    )
    from skeleton.jeeves.game_comparison_series_viewer import render_series_ledger_html

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, action="append", required=True,
                        help="Completed comparative study .result.json; repeat for 1–128 studies")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not 1 <= len(args.result) <= 128:
            raise SeriesLedgerError("Source study count exceeds 128")
        if args.output_dir.is_symlink():
            raise SeriesLedgerError("Series output path cannot be a symlink")
        inputs = [_read_json_file(path, 24*1024*1024) for path in args.result]
        ledger = merge_comparative_series(inputs)
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        _atomic_write(output/"game_series_ledger.json", json.dumps(ledger, indent=2, sort_keys=True, allow_nan=False).encode())
        viewer = render_series_ledger_html(ledger)
        _atomic_write(output/"game_series_ledger.html", viewer.encode("utf-8"))
        print(json.dumps({
            "status": "long_series_ledger_built_from_existing_native_evidence",
            "source_study_count": ledger["source_study_count"],
            "series_count": ledger["series_count"],
            "native_game_versions": ledger["native_game_variant_count"],
            "ledger_path": str(output/"game_series_ledger.json"),
            "viewer_path": str(output/"game_series_ledger.html"),
            "new_emulator_runs": 0,
            "training_weights_modified": False,
        }, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "long_series_ledger_rejected", "error_type": type(exc).__name__,
                          "message": str(exc)[:512]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
