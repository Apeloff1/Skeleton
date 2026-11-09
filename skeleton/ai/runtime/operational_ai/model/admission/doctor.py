"""Read-only proof of resource occupancy; no lease deletion or PID guessing."""
from __future__ import annotations
import json
from .broker import CapacityBroker
from .contracts import CapacityPolicy


def inspect(root,policy:CapacityPolicy|None=None)->dict:
    # This inspect creates the first policy only if no prior registry exists;
    # the operator-facing read-only CLI below refuses absent directories.
    with CapacityBroker(root,policy) as broker:
        return broker.inspect()


def main(argv:list[str]|None=None)->int:
    import argparse
    from pathlib import Path
    from .paths import verified_dir
    p=argparse.ArgumentParser(description='Read private native-model occupancy ledger')
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--slots',type=int,default=1)
    p.add_argument('--budget-bytes',type=int,default=8_000_000_000)
    a=p.parse_args(argv)
    try:
        fd=verified_dir(a.root)
        import os
        os.close(fd)
        report=inspect(a.root,CapacityPolicy(a.slots,a.budget_bytes))
    except Exception as exc:
        print(json.dumps({'status':'held','error_class':type(exc).__name__}))
        return 2
    print(json.dumps(report,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
