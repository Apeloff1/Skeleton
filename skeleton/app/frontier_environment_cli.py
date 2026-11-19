"""Run coupled frontier CPU-reference environment replay from a pinned order."""
import argparse
import json
import sys

from skeleton.app.recovered_evidence import canonical,read_document,pin
from skeleton.app.frontier_environment_replay import qualify_environment


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order",required=True)
    parser.add_argument("--expected-order-sha256",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit reference operator required")
        order,sha=read_document(args.order)
        pin(sha,args.expected_order_sha256)
        result=qualify_environment(order,authorized=True)
        print(canonical(result).decode("ascii"))
        return 0 if result["simulation"]["reference_invariants_passed"] else 3
    except (ValueError,TypeError,KeyError,PermissionError,OSError,RuntimeError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
