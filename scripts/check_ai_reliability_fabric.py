"""Run source-level qualification only after the completed source tree exists."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CHECKS=(
    ("compile", [sys.executable,"-m","compileall","-q",
        "skeleton/ai/runtime/operational_ai/reliability_fabric"]),
    ("adversarial-fixtures", [sys.executable,"-m",
        "skeleton.ai.runtime.operational_ai.reliability_fabric.cli"]),
    ("focused-unit-tests", [sys.executable,"-m","unittest","discover",
        "-s","skeleton/testing","-p","test_ai_reliability_*.py","-q"]),
)
def main(argv=None):
    if argv:
        print(json.dumps({"status":"held","error":"unrecognized-cli-args"}))
        return 2
    records=[]
    for name,command in CHECKS:
        try:
            executed=subprocess.run(command,cwd=ROOT,timeout=1200,check=False)
            code=executed.returncode
        except subprocess.TimeoutExpired:
            code=124
        records.append({"check":name,"exit_code":code})
        if code:
            print(json.dumps({"status":"held","evidence":records,
                              "native_model_e2e":False,"release_certified":False},sort_keys=True))
            return 2
    print(json.dumps({"status":"source-contracts-tested","evidence":records,
                      "native_model_e2e":False,"release_certified":False},sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main(sys.argv[1:]))
