"""Linux offline model flight control; operator CLI only, not a model tool.

All operations require successful real model activation. A missing checkpoint,
invalid identity or unavailable native backend is a hard error, not a demo.
"""
from __future__ import annotations
import argparse,json,secrets,sys
from pathlib import Path
from .contracts import FlightSpec
from .production import activate_flight


def parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description='Private local AI durable inference operations')
    p.add_argument('action',choices=('submit','work','doctor','recover','pause','resume'))
    p.add_argument('--model-root',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--worker',default='offline_worker')
    p.add_argument('--session')
    p.add_argument('--request-id')
    p.add_argument('--job-id')
    p.add_argument('--new-session',action='store_true')
    p.add_argument('--approve',action='store_true')
    p.add_argument('--priority',type=int,default=0)
    p.add_argument('--maximum',type=int,default=16)
    p.add_argument('--context',type=int,default=8192)
    p.add_argument('--max-new-tokens',type=int,default=512)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--gpu-layers',type=int,default=0)
    return p


def main(argv:list[str]|None=None)->int:
    args=parser().parse_args(argv)
    try:
        if args.action=='submit':
            # Read bounded stdin rather than accepting secrets in shell argv.
            data=sys.stdin.buffer.read(32769)
            if not data or len(data)>32768:raise ValueError('prompt must be <= 32768 bytes')
            prompt=data.decode('utf8','strict')
            if not prompt.strip():raise ValueError('empty prompt')
            if args.session is None and not args.new_session:
                raise ValueError('new or existing session must be explicit')
            if args.new_session and args.session is not None:
                raise ValueError('new-session cannot override existing session')
        elif args.new_session:
            raise ValueError('session creation is only available during submit')
        with activate_flight(model_root=args.model_root,state_dir=args.state_dir,
                tenant=args.tenant,subject=args.subject,worker_id=args.worker,
                n_ctx=args.context,max_new_tokens=args.max_new_tokens,
                n_threads=args.threads,gpu_layers=args.gpu_layers) as app:
            if args.action=='submit':
                session=args.session or 'session_'+secrets.token_hex(12)
                if args.new_session:app.spine.create(session)
                else:app.spine.history(session)
                job=args.job_id or 'job_'+secrets.token_hex(12)
                request=args.request_id or 'request_'+secrets.token_hex(12)
                record=app.ledger.submit(FlightSpec(app.spine.identity,job,session,
                    request,prompt,priority=args.priority))
                result={'status':'accepted','job':record}
            elif args.action=='work':
                jobs=app.worker.drain(maximum=args.maximum)
                result={'status':'drained','completed':[
                    {'job_id':r.job_id,'state':r.state,'revision':r.revision} for r in jobs]}
            elif args.action=='doctor':
                result={'status':'observed',**app.operator.diagnose(max_jobs=args.maximum)}
            elif args.action=='recover':
                result={'status':'reconciled',**app.operator.recover(approved=args.approve,limit=args.maximum)}
            elif args.action=='pause':
                result={'status':'operator-mode',**app.operator.pause(approved=args.approve)}
            else:
                result={'status':'operator-mode',**app.operator.resume(approved=args.approve)}
        print(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':')))
        return 0
    except (Exception,) as exc:
        # Never print exception messages, which may contain prompt/private paths.
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
