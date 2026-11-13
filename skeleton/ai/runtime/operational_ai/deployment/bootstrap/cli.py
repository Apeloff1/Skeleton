"""Explicit first-install private AI state/key provisioning; never prints key bytes."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .provision import provision,ProvisionError


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Create private offline AI state and OS-generated memory encryption key')
    p.add_argument('--state-parent',type=Path,required=True)
    p.add_argument('--state-name',required=True)
    p.add_argument('--key-parent',type=Path,required=True)
    p.add_argument('--key-name',default='memory.key')
    args=p.parse_args(argv)
    try:
        print(json.dumps(provision(args.state_parent,args.state_name,
                                   args.key_parent,args.key_name).to_record(),sort_keys=True))
        return 0
    except (ProvisionError,ValueError,RuntimeError,OSError) as exc:
        print(json.dumps({'status':'blocked','reason':type(exc).__name__}),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
