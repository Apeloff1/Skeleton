#!/usr/bin/env python3
"""Run the deterministic governed-effect qualification and emit canonical JSON."""
from __future__ import annotations
import json
from skeleton.ai.runtime.effects.qualification import run_qualification

if __name__ == "__main__":
    report = run_qualification()
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    raise SystemExit(0 if report["passed"] else 1)
