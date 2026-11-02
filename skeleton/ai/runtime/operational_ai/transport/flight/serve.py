"""True GGUF-backed native flight HTTP entrypoint; no mock/provider fallback."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from ...orchestration.flight_control.production import activate_flight
from ...context.knowledge_plane.service import KnowledgePlane
from .dispatch import FlightDispatcher
from .http import FlightHTTPServer


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
    args=p.parse_args(argv)
    try:
        # The bearer is read from an independently provisioned private file,
        # never copied into shell argv, a public environment variable or logs.
        from .credential import read_bearer
        token=read_bearer(args.bearer_file)
        with activate_flight(model_root=args.model_root,state_dir=args.state_dir,
              tenant=args.tenant,subject=args.subject,worker_id=args.worker,
              n_ctx=args.context,max_new_tokens=args.max_new_tokens,
              n_threads=args.threads,gpu_layers=args.gpu_layers) as app:
            knowledge=KnowledgePlane(app.spine.db,app.spine.identity,initialize=False)
            dispatcher=FlightDispatcher(app,knowledge_plane=knowledge)
            with FlightHTTPServer(('127.0.0.1',args.port),dispatcher,token) as server:
                print(json.dumps({'status':'serving-local-private-flight',
                    'bind':'127.0.0.1','port':server.server_port,
                    'model_sha256':app.spine.identity.model_sha256}),flush=True)
                server.serve_forever(poll_interval=.2)
        return 0
    except (Exception,) as exc:
        print(json.dumps({'status':'held','error_type':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
