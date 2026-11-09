#!/usr/bin/env python3
"""Offline operator analysis of the live native multi-emulator export."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def main(argv: list[str] | None = None) -> int:
    from scripts.compare_game_study import _atomic_write, _read_json_file
    from skeleton.jeeves.game_comparison_pairwise import (
        MAX_EVIDENCE_BYTES, analyze_live_comparison_evidence,
        render_pairwise_observation_dashboard)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output_dir.is_symlink():
            raise ValueError("Report destination cannot be a symlink")
        report = analyze_live_comparison_evidence(
            _read_json_file(args.evidence, MAX_EVIDENCE_BYTES))
        folder = args.output_dir.resolve()
        folder.mkdir(parents=True, exist_ok=True)
        output_json = folder / "live_pairwise_observations.json"
        output_html = folder / "live_pairwise_observations.html"
        _atomic_write(output_json, json.dumps(report, indent=2, sort_keys=True, allow_nan=False).encode())
        _atomic_write(output_html, render_pairwise_observation_dashboard(report).encode())
        print(json.dumps({
            "status": "native_receipts_analyzed_offline",
            "lanes": report["lane_count"], "pairs": report["pair_count"],
            "captured_native_steps": report["total_input_steps"],
            "json": str(output_json), "dashboard": str(output_html),
            "new_emulator_executions": 0, "model_training": False,
        }, indent=2))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "native_evidence_rejected",
                          "exception": type(exc).__name__,
                          "reason": str(exc)[:200]}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
