"""Operational AI CLI: exactly one verified local request, durable across restarts."""
from __future__ import annotations
import argparse,json,secrets,sys
from pathlib import Path
from .startup import activate
from ...orchestration.execution_spine.contracts import SpineError

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Real, offline, operator-authorized AI inference')
    p.add_argument('--model-root',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--session')
    p.add_argument('--request-id')
    p.add_argument('--prompt',required=True)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--isolate-native',action='store_true',
                   help='Run the real GGUF backend in a killable private subprocess')
    p.add_argument('--context',type=int,default=2048)
    p.add_argument('--max-new-tokens',type=int,default=256)
    p.add_argument('--capacity-root',type=Path)
    p.add_argument('--capacity-slots',type=int,default=1)
    p.add_argument('--capacity-budget-bytes',type=int,default=8_000_000_000)
    args=p.parse_args(argv)
    try:
        from ...model.admission.paths import create_default_root
        stack,worker=activate(model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,n_ctx=args.context,
            max_new_tokens=args.max_new_tokens,n_threads=args.threads,
            isolated=args.isolate_native,
            capacity_root=args.capacity_root if args.capacity_root is not None else create_default_root(),
            capacity_slots=args.capacity_slots,
            capacity_budget_bytes=args.capacity_budget_bytes)
        with stack:
            session=args.session or 's_'+secrets.token_hex(16)
            if not args.session:worker.spine.create(session)
            receipt=worker.turn(session,'r_'+secrets.token_hex(16) if not args.request_id else args.request_id,args.prompt)
            print(json.dumps({'status':'real-model-turn-committed', 'receipt':receipt},sort_keys=True))
        return 0
    except Exception as exc:
        # Never emit model prompt, private paths, secrets or evidence excerpts.
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
