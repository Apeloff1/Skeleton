"""Independent disposable-state real GGUF first-install canary entrypoint."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from ..production import activate_flight
from .canary import run_live_canary
from .contracts import DaemonError

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description='Real GGUF -> queued inference -> receipt -> exact replay canary')
    parser.add_argument('--model-root',type=Path,required=True)
    parser.add_argument('--fresh-private-state-dir',type=Path,required=True)
    parser.add_argument('--tenant',required=True)
    parser.add_argument('--subject',required=True)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--gpu-layers',type=int,default=0)
    parser.add_argument('--context-tokens',type=int,default=2048)
    parser.add_argument('--max-new-tokens',type=int,default=128)
    args=parser.parse_args(argv)
    try:
        from ...execution_spine.path_policy import open_private_root
        import os
        root_fd=open_private_root(args.fresh_private_state_dir)
        try:
            # Native activation creates state.identity.json itself. Any prior
            # spine or journal is unsafe to borrow as an independent canary.
            for name in ('ai-spine.sqlite','ai-spine.sqlite-wal',
                         'ai-spine.sqlite-shm','ai-spine.sqlite-journal',
                         'state.identity.json'):
                try:os.stat(name,dir_fd=root_fd,follow_symlinks=False)
                except FileNotFoundError:continue
                raise DaemonError('qualifier state must not contain a prior identity or database')
        finally:os.close(root_fd)
        # Production bootstrap must already have prepared owner-only directory,
        # binding and model manifest. Native activation refuses missing setup.
        with activate_flight(model_root=args.model_root,state_dir=args.fresh_private_state_dir,
             tenant=args.tenant,subject=args.subject,worker_id='qualifier',
             n_ctx=args.context_tokens,max_new_tokens=args.max_new_tokens,
             n_threads=args.threads,gpu_layers=args.gpu_layers) as app:
            result=run_live_canary(app)
            print(json.dumps(result,sort_keys=True))
            return 0
    except (Exception,) as exc:
        print(json.dumps({'status':'held','error_type':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
