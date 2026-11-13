"""Operator-only real GGUF endurance qualification, secured by capacity lease."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from contextlib import ExitStack
from .contracts import BurnInPolicy
from .bench import measure
from .storage import publish_private
from ..gguf.service import load_approved_manifest
from ..isolation.client import IsolatedGGUFBackend
from ..admission import CapacityPolicy,CapacityBroker
from ..admission.estimates import reservation_for
from ..admission.paths import create_default_root
from ..admission.wrapper import AdmittedBackend


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Real approved local GGUF stability probe; no mock fallback')
    p.add_argument('--model-root',type=Path,required=True)
    p.add_argument('--result-dir',type=Path,required=True)
    p.add_argument('--report-name',required=True)
    p.add_argument('--capacity-root',type=Path)
    p.add_argument('--capacity-slots',type=int,default=1)
    p.add_argument('--capacity-budget-bytes',type=int,default=8_000_000_000)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--trials',type=int,default=12)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--context',type=int,default=2048)
    p.add_argument('--output-tokens',type=int,default=48)
    p.add_argument('--native-timeout-ms',type=int,default=120000)
    a=p.parse_args(argv)
    try:
        manifest=load_approved_manifest(a.model_root)
        policy=CapacityPolicy(a.capacity_slots,a.capacity_budget_bytes)
        trial_policy=BurnInPolicy(trials=a.trials,max_output_tokens=a.output_tokens,
                                 context_tokens=a.context,inference_ms=a.native_timeout_ms)
        with ExitStack() as stack:
            root=a.capacity_root if a.capacity_root else create_default_root()
            broker=stack.enter_context(CapacityBroker(root,policy))
            lease=stack.enter_context(broker.acquire(reservation_for(manifest,
                tenant=a.tenant,subject=a.subject,policy=policy)))
            model=stack.enter_context(IsolatedGGUFBackend(a.model_root.absolute(),manifest,
                n_ctx=a.context,n_threads=a.threads,inference_ms=a.native_timeout_ms,
                capacity_lease=lease))
            report=measure(AdmittedBackend(model,lease),trial_policy)
            persisted=publish_private(a.result_dir,a.report_name,report)
        print(json.dumps({'status':'real-model-observed-not-release-certified',
                          'model_sha256':manifest.model_sha256,'trials':a.trials,
                          'result_sha256':persisted['report_sha256']}))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
