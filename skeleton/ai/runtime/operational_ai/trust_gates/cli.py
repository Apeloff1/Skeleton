"""Machine-readable, no-secret operator check and contract fixture runner."""
import argparse
import json
from pathlib import Path
import sys
from .contracts import GateViolation,load_json
from .engine import domains,validate
from .fixtures import run_all

def main(argv=None):
    parser=argparse.ArgumentParser(description="Strict offline AI contract gates")
    parser.add_argument("command",choices=("check","selftest"))
    parser.add_argument("--gate",choices=domains())
    parser.add_argument("--input",type=Path)
    opts=parser.parse_args(argv)
    try:
        if opts.command=="selftest":
            if opts.gate or opts.input: raise GateViolation("unexpected selftest arguments")
            cases=run_all()
            print(json.dumps({"schema":"ai-trust-selftest.v1","gates":len(cases),
                              "cases":sum(x["total"] for x in cases),
                              "status":"contract-fixtures-passed"},sort_keys=True))
            return 0
        if opts.gate is None or opts.input is None: raise GateViolation("missing check arguments")
        # Owner-controlled input only. No claim of descriptor-safe hostile package traversal.
        if opts.input.is_symlink() or not opts.input.is_file() or opts.input.stat().st_size>524288:
            raise GateViolation("unsafe or oversized input")
        result=validate(opts.gate,load_json(opts.input.read_bytes()))
        print(json.dumps(result,sort_keys=True));return 0
    except (GateViolation,OSError,ValueError) as exc:
        print(json.dumps({"status":"blocked","reason":type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=="__main__": raise SystemExit(main())
