#!/usr/bin/env python3
"""Bind 1–15 exported native cohorts to one canonical 2–30 game study."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main(argv: list[str] | None = None) -> int:
    from scripts.compare_game_study import _read_json_file, _atomic_write
    from skeleton.jeeves.game_comparison_pairwise import MAX_EVIDENCE_BYTES
    from skeleton.jeeves.game_comparison_portfolio import (
        combine_comparison_cohorts, render_comparison_portfolio_dashboard)
    from skeleton.jeeves.game_comparison_schema import MAX_MANIFEST_BYTES
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", required=True, type=Path)
    p.add_argument("--evidence", required=True, type=Path, action="append")
    p.add_argument("--output-dir", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        if args.output_dir.is_symlink():
            raise ValueError("Portfolio output path cannot be a symlink")
        model = _read_json_file(args.study, MAX_MANIFEST_BYTES)
        packets = [_read_json_file(path, MAX_EVIDENCE_BYTES) for path in args.evidence]
        report = combine_comparison_cohorts(model, packets)
        root = args.output_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        file_json = root / "emulator_30_game_portfolio.json"
        file_html = root / "emulator_30_game_portfolio.html"
        _atomic_write(file_json, json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode())
        _atomic_write(file_html, render_comparison_portfolio_dashboard(report).encode())
        print(json.dumps({
            "status": "multi_cohort_native_receipts_compared_offline",
            "recorded_games": report["recorded_game_count"],
            "unrecorded_games": len(report["missing_game_ids"]),
            "pairs": report["pair_count"],
            "native_emulation_executed": False, "weights_changed": False,
            "json": str(file_json), "dashboard": str(file_html),
        }, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "portfolio_rejected",
                          "error": type(exc).__name__, "detail": str(exc)[:200]}),
              file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
