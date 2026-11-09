#!/usr/bin/env python3
"""Fail closed if any of 576 Jeeves competency contracts drift before compilation."""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from skeleton.ai.training.jeeves_multidomain import validate_catalog


def main() -> int:
    try:
        value = validate_catalog(ROOT / "machine/jeeves_training_modules.json")
    except (OSError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)[:300]}), file=sys.stderr)
        return 1
    if value["modules"] != 576 or value["domains"] != ["ai", "coding", "gaming"]:
        print("Jeeves specialization coverage drift", file=sys.stderr)
        return 1
    print(json.dumps({"valid": True, **value}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
