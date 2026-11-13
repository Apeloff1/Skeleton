"""Read-only operator metrics from a local private state under exact identity."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Read-only native inference flight telemetry')
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--tenant',required=True)
    p.add_argument('--subject',required=True)
    p.add_argument('--model-sha256',required=True)
    p.add_argument('--tokenizer-sha256',required=True)
    p.add_argument('--max-jobs',type=int,default=2048)
    args=p.parse_args(argv)
    try:
        from ...execution_spine.contracts import Identity
        from ...execution_spine.database import SpineDatabase
        from .telemetry import snapshot
        from .. import doctor as flight_doctor
        identity=Identity(args.tenant,args.subject,args.model_sha256,args.tokenizer_sha256)
        with SpineDatabase(args.state_dir,readonly=True) as db:
            # FlightLedger installs schema, so cannot be used with readonly db.
            # Query only existing durable rows, with a minimal immutable facade.
            class ReadOnlyLedger:
                pass
            ledger=ReadOnlyLedger();ledger.db=db;ledger.identity=identity
            with db.snapshot() as conn:
                row=conn.execute('SELECT identity_json FROM principals WHERE principal=?',
                                 (identity.key(),)).fetchone()
                from ...execution_spine.contracts import canonical
                if row!=(canonical(identity.as_dict()),):
                    raise RuntimeError('private operator identity does not match stored principal')
                schema=conn.execute("SELECT value FROM controls WHERE control='flight_schema'").fetchone()
                if schema!=('1',):raise RuntimeError('flight queue schema not qualified')
            flight_doctor.inspect(ledger,max_jobs=args.max_jobs)
            report=snapshot(ledger,maximum=args.max_jobs)
        print(json.dumps({'status':'read-only-verified','telemetry':report},sort_keys=True))
        return 0
    except (Exception,) as exc:
        print(json.dumps({'status':'held','error_type':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
