"""Operator-only local spool export with explicit principal/model authority."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import Identity
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.flight_control.ledger import FlightLedger
from skeleton.ai.runtime.operational_ai.deployment.boot.identity import PrincipalBinding,inspect_binding
from .contracts import DeliveryPolicy
from .sink import PrivateEventSink
from .pump import DeliveryPump

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Export only authenticated native AI event digests to private local spool')
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--spool-dir',type=Path,required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--model-sha256',required=True)
    p.add_argument('--tokenizer-sha256',required=True)
    p.add_argument('--limit',type=int,default=32)
    p.add_argument('--verify-only',action='store_true')
    p.add_argument('--doctor',action='store_true')
    p.add_argument('--follow-ticks',type=int,default=0)
    p.add_argument('--after-sequence',type=int,default=None)
    a=p.parse_args(argv)
    try:
        identity=Identity(a.tenant,a.subject,a.model_sha256,a.tokenizer_sha256)
        inspect_binding(a.state_dir,PrincipalBinding(a.tenant,a.subject,
            a.model_sha256,a.tokenizer_sha256))
        with SpineDatabase(a.state_dir) as db:
            ledger=FlightLedger(db,identity)
            with PrivateEventSink(a.spool_dir) as sink:
                pump=DeliveryPump(ledger,sink)
                if sum(bool(x) for x in (a.verify_only,a.doctor,
                    a.follow_ticks>0,a.after_sequence is not None))>1:
                    raise ValueError('only one local spool operation is supported')
                if a.verify_only:report=pump.audit()
                elif a.doctor:
                    from .doctor import inspect
                    report=inspect(ledger,sink)
                elif a.after_sequence is not None:
                    from .consumer import read_since
                    report=read_since(ledger,sink,sequence=a.after_sequence,limit=a.limit)
                elif a.follow_ticks:
                    from .daemon import LocalSpoolDaemon,SpoolDaemonPolicy
                    report=LocalSpoolDaemon(pump,SpoolDaemonPolicy(
                        maximum_ticks=a.follow_ticks,batch=a.limit)).run()
                else:report=pump.drain(limit=a.limit)
            print(json.dumps(report,sort_keys=True,default=list));return 0
    except BaseException as exc:
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
