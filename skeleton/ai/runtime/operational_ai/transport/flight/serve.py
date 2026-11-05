"""True GGUF-backed native flight HTTP entrypoint; no mock/provider fallback."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from ...orchestration.flight_control.production import activate_flight
from ...context.knowledge_plane.service import KnowledgePlane
from .dispatch import FlightDispatcher
from ...orchestration.flight_control.daemon import DaemonPolicy,SupervisedFlightHTTP
from ...orchestration.flight_control.daemon.signals import termination_interrupt


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Private offline native GGUF flight HTTP')
    p.add_argument('--model-root',type=Path,required=True)
    p.add_argument('--bearer-file',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--worker',default='local_http_worker')
    p.add_argument('--port',type=int,default=8766)
    p.add_argument('--context',type=int,default=8192)
    p.add_argument('--max-new-tokens',type=int,default=512)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--gpu-layers',type=int,default=0)
    p.add_argument('--isolate-native',action='store_true',
                   help='Execute all GGUF inference inside a killable local worker process')
    p.add_argument('--capacity-root',type=Path,
                   help='Private global native-model capacity root')
    p.add_argument('--capacity-slots',type=int,default=1)
    p.add_argument('--capacity-budget-bytes',type=int,default=8_000_000_000)
    p.add_argument('--poll-ms',type=int,default=200)
    p.add_argument('--shutdown-grace-ms',type=int,default=120000)
    args=p.parse_args(argv)
    try:
        # The bearer is read from an independently provisioned private file,
        # never copied into shell argv, a public environment variable or logs.
        from .credential import read_bearer
        from ...model.admission.paths import create_default_root
        token=read_bearer(args.bearer_file)
        with activate_flight(model_root=args.model_root,state_dir=args.state_dir,
              tenant=args.tenant,subject=args.subject,worker_id=args.worker,
              n_ctx=args.context,max_new_tokens=args.max_new_tokens,
              n_threads=args.threads,gpu_layers=args.gpu_layers,
              isolate_native=args.isolate_native,
              capacity_root=args.capacity_root if args.capacity_root is not None else create_default_root(),
              capacity_slots=args.capacity_slots,
              capacity_budget_bytes=args.capacity_budget_bytes) as app:
            knowledge=KnowledgePlane(app.spine.db,app.spine.identity,initialize=False)
            policy=DaemonPolicy(poll_ms=args.poll_ms,
                                shutdown_grace_ms=args.shutdown_grace_ms)
            with SupervisedFlightHTTP(app,knowledge,token,port=args.port,policy=policy) as (server,daemon):
                print(json.dumps({'status':'serving-local-private-flight',
                    'mode':'automatic-single-native-worker',
                    'bind':'127.0.0.1','port':server.server_port,
                    'model_sha256':app.spine.identity.model_sha256}),flush=True)
                with termination_interrupt():
                    try:server.serve_forever(poll_interval=.2)
                    except KeyboardInterrupt:pass
        return 0
    except (Exception,) as exc:
        print(json.dumps({'status':'held','error_type':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
