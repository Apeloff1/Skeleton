"""Complete suite for real SQLite work custody with explicit untested device holds."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
COMMANDS=(
 ("compile", [sys.executable,"-m","compileall","-q",
     "skeleton/ai/runtime/operational_ai/work_orders"]),
 ("unit", [sys.executable,"-m","unittest","discover",
     "-s","skeleton/testing","-p","test_ai_work_orders_*.py","-q"]),
)
def main(args=None):
    if args:raise SystemExit("unsupported arguments")
    rows=[]
    for name,command in COMMANDS:
        try:
            result=subprocess.run(command,cwd=ROOT,check=False,timeout=1200)
            code=result.returncode
        except subprocess.TimeoutExpired:code=124
        rows.append({"stage":name,"exit_code":code})
        if code!=0:
            print(json.dumps({"status":"held","evidence":rows,
                "native_e2e":False,"release_certified":False},sort_keys=True))
            return 2
    print(json.dumps({"status":"work-order-sqlite-contracts-tested",
        "evidence":rows,"real_model_e2e":False,"release_certified":False},sort_keys=True))
    return 0
if __name__=="__main__":raise SystemExit(main(sys.argv[1:]))
