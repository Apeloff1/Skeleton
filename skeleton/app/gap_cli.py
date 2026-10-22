"""skeleton/app/gap_cli.py
Complete CLI entry for the multi-gap orchestrator.
Prints the unified digest or fails closed.
"""
from __future__ import annotations

import json
import sys

from skeleton.app.gap_orchestrator import run_all_starters, OrchestratorError

def main() -> int:
    try:
        result = run_all_starters()
        print(json.dumps({"digest": result["digest"], "planes": len(result["planes"]), "stored_prose": 0}))
        return 0
    except OrchestratorError as exc:
        print(f"orchestrator failed: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
