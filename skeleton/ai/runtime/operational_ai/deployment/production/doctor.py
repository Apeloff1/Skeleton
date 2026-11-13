"""Read-only operator doctor for already provisioned, principal-bound AI state."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from ...orchestration.execution_spine.database import SpineDatabase
from ...orchestration.execution_spine.doctor import inspect
from ...orchestration.execution_spine.contracts import Identity
from ..boot.identity import PrincipalBinding,inspect_binding

def main(argv=None)->int:
    parser=argparse.ArgumentParser(description='Read-only offline AI state health')
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--tenant',required=True)
    parser.add_argument('--subject',required=True)
    parser.add_argument('--model-sha256',required=True)
    parser.add_argument('--tokenizer-sha256',required=True)
    args=parser.parse_args(argv)
    try:
        identity=Identity(args.tenant,args.subject,args.model_sha256,args.tokenizer_sha256)
        inspect_binding(args.state_dir,PrincipalBinding(identity.tenant,identity.subject,
            identity.model_sha256,identity.tokenizer_sha256))
        with SpineDatabase(args.state_dir,readonly=True) as db:proof=inspect(db)
        print(json.dumps(proof,sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
