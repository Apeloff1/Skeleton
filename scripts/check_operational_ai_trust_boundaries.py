"""Run the completed source qualification suite; no release certification."""
from __future__ import annotations
import argparse
import json
import sys
from skeleton.ai.runtime.operational_ai.trust_gates.contracts import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.inventory import qualification_snapshot

def main(argv=None):
    parser=argparse.ArgumentParser(description="Operational AI source-level qualification")
    parser.add_argument("--run-fixtures",action="store_true",
                        help="Execute all 240 real policy fixtures")
    args=parser.parse_args(argv)
    try:
        result=qualification_snapshot(execute_fixtures=args.run_fixtures)
    except (GateViolation,OSError,ValueError) as exc:
        print(json.dumps({"status":"blocked","reason":type(exc).__name__}),
              file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
