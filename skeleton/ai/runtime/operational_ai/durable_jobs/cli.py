"""Read-only command to execute the executable offline AI job acceptance suite."""
from __future__ import annotations
import json
import sys
from .scenario_runner import run_matrix


def main()->int:
    try:
        report=run_matrix()
    except Exception as exc:
        print(json.dumps({
            "schema":"skeleton.ai.jobs.suite.v1","status":"blocked",
            "reason":type(exc).__name__,"release_certified":False,
        },sort_keys=True))
        return 2
    print(json.dumps(report,sort_keys=True))
    return 0 if report["failed"]==0 else 1


if __name__=="__main__":
    sys.exit(main())
