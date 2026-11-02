"""Approved expired-intent hold; never replays model, rewrites output, or deletes events."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from ...orchestration.execution_spine.database import SpineDatabase
from ...orchestration.execution_spine.contracts import Identity
from ...orchestration.execution_spine.operator_recovery import hold_abandoned
from ..boot.identity import PrincipalBinding,inspect_binding

def main(argv=None):
    p=argparse.ArgumentParser(description='Explicit admin hold for expired local AI intents')
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--tenant',required=True);p.add_argument('--subject',required=True)
    p.add_argument('--model-sha256',required=True);p.add_argument('--tokenizer-sha256',required=True)
    p.add_argument('--approve-hold-expired',action='store_true')
    a=p.parse_args(argv)
    try:
        identity=Identity(a.tenant,a.subject,a.model_sha256,a.tokenizer_sha256)
        inspect_binding(a.state_dir,PrincipalBinding(identity.tenant,identity.subject,
            identity.model_sha256,identity.tokenizer_sha256))
        with SpineDatabase(a.state_dir) as db:
            result=hold_abandoned(db,identity,approved=a.approve_hold_expired)
        print(json.dumps(result,sort_keys=True));return 0
    except Exception as exc:
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
