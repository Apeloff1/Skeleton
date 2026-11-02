"""Operator-run live inference probe: no model output plaintext is logged."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .startup import activate
from ...orchestration.execution_spine.qualification import run_canary

def main(argv=None):
    p=argparse.ArgumentParser(description='Run real GGUF canary; never use mock fallback')
    p.add_argument('--model-root',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--capacity-root',type=Path)
    p.add_argument('--capacity-slots',type=int,default=1)
    p.add_argument('--capacity-budget-bytes',type=int,default=8_000_000_000)
    a=p.parse_args(argv)
    try:
        from ...model.admission.paths import create_default_root
        stack,worker=activate(model_root=a.model_root,state_dir=a.state_dir,tenant=a.tenant,subject=a.subject,
            capacity_root=a.capacity_root if a.capacity_root is not None else create_default_root(),
            capacity_slots=a.capacity_slots,capacity_budget_bytes=a.capacity_budget_bytes)
        with stack:
            report=run_canary(worker.spine.backend,worker.spine.identity,worker.spine.limits)
        print(json.dumps(report,sort_keys=True));return 0
    except BaseException as exc:
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
