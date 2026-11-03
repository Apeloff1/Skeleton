"""Run completed source-local AI qualification without claiming native model proof."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
TASKS=(
    ("compile", [sys.executable,"-m","compileall","-q",
       "skeleton/ai/runtime/operational_ai/laptop_runtime"]),
    ("source-fixtures", [sys.executable,"-m",
       "skeleton.ai.runtime.operational_ai.laptop_runtime.qualification.cli"]),
    ("runtime-unittest", [sys.executable,"-m","unittest","discover",
       "-s","skeleton/testing","-p","test_laptop_runtime_*.py","-q"]),
    ("qualification-unittest", [sys.executable,"-m","unittest","discover",
       "-s","skeleton/testing","-p","test_laptop_qualification_*.py","-q"]),
)

def main(argv=None):
    if argv:
        print(json.dumps({"status":"held","reason":"unapproved-arguments"}),file=sys.stderr)
        return 2
    evidence=[]
    for name,command in TASKS:
        result=subprocess.run(command,cwd=ROOT,check=False,timeout=600)
        evidence.append({"step":name,"exit_code":result.returncode})
        if result.returncode!=0:
            print(json.dumps({"status":"held","evidence":evidence,
                "release_certified":False},sort_keys=True))
            return 2
    print(json.dumps({"status":"focused-source-tests-passed",
        "evidence":evidence,"real_model_e2e":False,
        "release_certified":False},sort_keys=True))
    return 0

if __name__=="__main__":raise SystemExit(main(sys.argv[1:]))
