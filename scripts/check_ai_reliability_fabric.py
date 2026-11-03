"""Focused exact-source reliability suite; no native GGUF or release qualification."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CHECKS=(
    ("compile", [sys.executable,"-m","compileall","-q",
                 "skeleton/ai/runtime/operational_ai/reliability_fabric"]),
    ("fixture-engine", [sys.executable,"-m",
                 "skeleton.ai.runtime.operational_ai.reliability_fabric.cli"]),
    ("policy-unit-tests", [sys.executable,"-m","unittest","discover",
                 "-s","skeleton/testing","-p","test_ai_reliability_*.py","-q"]),
    ("flow-unit-tests", [sys.executable,"-m","unittest","discover",
                 "-s","skeleton/testing","-p","test_ai_reliability_flow_*.py","-q"]),
)

def main(argv=None):
    if argv:
        print(json.dumps({"status":"held","reason":"unexpected-arguments"}),file=sys.stderr)
        return 2
    outcomes=[]
    for name,command in CHECKS:
        try:
            result=subprocess.run(command,cwd=ROOT,check=False,timeout=600)
            exit_code=result.returncode
        except (OSError,subprocess.TimeoutExpired):
            exit_code=2
        outcomes.append({"step":name,"exit_code":exit_code})
        if exit_code:
            print(json.dumps({"status":"source-validation-held",
                "checks":outcomes,"native_model_e2e":False,
                "release_certified":False},sort_keys=True))
            return 2
    print(json.dumps({"status":"source-contracts-verified",
        "checks":outcomes,"native_model_e2e":False,
        "release_certified":False},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main(sys.argv[1:]))
