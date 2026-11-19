"""Read-only local fixed-step input replay and independent save reconstruction."""
import argparse
import json
import sys

from skeleton.app.recovered_evidence import EvidenceError, read_document, canonical
from skeleton.game.simulation.fixed_input_replay import Simulation, qualify_motion


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("qualify","restore"))
    parser.add_argument("--order",required=True)
    parser.add_argument("--snapshot")
    parser.add_argument("--expected-digest")
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit local operator required")
        order,_=read_document(args.order)
        if args.operation=="qualify":
            if args.snapshot or args.expected_digest:
                raise EvidenceError("unexpected snapshot")
            result=qualify_motion(order,authorized=True)
        else:
            if not args.snapshot or not args.expected_digest:
                raise EvidenceError("independent snapshot required")
            snapshot,_=read_document(args.snapshot)
            run=Simulation.restore(order,snapshot,expected_digest=args.expected_digest,authorized=True)
            result=run.snapshot()
        print(canonical(result).decode("ascii"))
        return 0
    except (ValueError,PermissionError,TypeError,KeyError,OSError,OverflowError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
