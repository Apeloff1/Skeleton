"""Generate a pinned route, then execute real source gameplay across virtual controllers."""
import argparse
import json
import sys
import sqlite3
from skeleton.app.recovered_evidence import canonical,pin,read_document,EvidenceError
from skeleton.app.expedition_controller_model import plan_journey
from skeleton.app.expedition_controller_qualification import qualify_journey


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("plan","qualify"))
    parser.add_argument("--order",required=True)
    parser.add_argument("--expected-order-sha256",required=True)
    parser.add_argument("--expected-plan-digest")
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit controller operator required")
        order,sha=read_document(args.order)
        pin(sha,args.expected_order_sha256)
        if args.operation=="plan":
            if args.expected_plan_digest is not None:
                raise EvidenceError("plan operation does not accept old plan digest")
            result=plan_journey(order,authorized=True)
        else:
            result=qualify_journey(order,expected_plan_digest=args.expected_plan_digest,authorized=True)
        print(canonical(result).decode("ascii"))
        return 0
    except (ValueError,TypeError,KeyError,PermissionError,OSError,sqlite3.Error) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
