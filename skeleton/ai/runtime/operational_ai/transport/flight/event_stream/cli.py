"""Operator CLI: finite event watch with explicit source-provenance cursors."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .client import get_events
from ..credential import read_bearer

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Watch verified native AI job transitions, never output private model text')
    p.add_argument('--bearer-file',type=Path,required=True)
    p.add_argument('--job',required=True)
    p.add_argument('--port',type=int,default=8766)
    p.add_argument('--limit',type=int,default=32)
    p.add_argument('--wait-ms',type=int,default=1000)
    p.add_argument('--rounds',type=int,default=1)
    p.add_argument('--cursor')
    args=p.parse_args(argv)
    try:
        if type(args.rounds)is not int or not 1<=args.rounds<=100:
            raise ValueError('operator watch must be finite')
        bearer=read_bearer(args.bearer_file);cursor=args.cursor
        for _ in range(args.rounds):
            rows=get_events(port=args.port,token=bearer,job_id=args.job,
                            cursor=cursor,limit=args.limit,wait_ms=args.wait_ms)
            for row in rows:
                print(json.dumps(row,sort_keys=True,separators=(',',':')))
                if row['cursor']:cursor=row['cursor']
            if rows[-1]['data'].get('terminal'):break
        return 0
    except Exception as exc:
        print(json.dumps({'status':'held','reason':type(exc).__name__}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
