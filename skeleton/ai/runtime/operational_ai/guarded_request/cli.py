"""Execute the real policy matrix without running or impersonating an LLM."""
from __future__ import annotations

import json
import sys

from .scenario_runner import verify_all


def main() -> int:
    try:
        report = verify_all()
    except Exception as exc:
        print(json.dumps({
            "schema": "skeleton.ai.guard.suite.v1",
            "status": "failed",
            "reason": type(exc).__name__,
            "real_model_tested": False,
            "release_certified": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
