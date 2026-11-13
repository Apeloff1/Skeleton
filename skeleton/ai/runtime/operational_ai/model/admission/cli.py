"""Private operator inspection and explicitly authorized recovery only."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from .broker import CapacityBroker
from .contracts import CapacityPolicy
from .recovery import reconcile_orphans
from .migration import migrate_unused
from .paths import verified_dir,open_file


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Private per-UID native model capacity')
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--slots',type=int,default=1)
    p.add_argument('--budget-bytes',type=int,default=8_000_000_000)
    p.add_argument('--action',choices=('inspect','reconcile','bootstrap-policy-migration'),default='inspect')
    p.add_argument('--approve',action='store_true')
    p.add_argument('--new-budget-bytes',type=int)
    p.add_argument('--maximum',type=int,default=8)
    a=p.parse_args(argv)
    try:
        rootfd=verified_dir(a.root)
        try:
            fd=open_file(rootfd,'policy.json')
            os.close(fd)
        finally:
            os.close(rootfd)
        policy=CapacityPolicy(a.slots,a.budget_bytes)
        with CapacityBroker(a.root,policy) as broker:
            if a.action=='inspect':
                report=broker.inspect()
            elif a.action=='reconcile':
                report=reconcile_orphans(broker,approved=a.approve,maximum=a.maximum)
            else:
                if a.new_budget_bytes is None:
                    raise ValueError('new capacity budget required')
                report=migrate_unused(broker,CapacityPolicy(a.slots,a.new_budget_bytes),approved=a.approve)
    except Exception as exc:
        # Do not expose paths or exception messages that could contain secrets.
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2
    print(json.dumps(report,sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
