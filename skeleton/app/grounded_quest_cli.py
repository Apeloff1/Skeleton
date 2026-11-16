"""Operator-scoped signed authored route and quest replay qualification."""
import argparse
import json
import os
import sys

from skeleton.app.recovered_evidence import canonical,read_document,pin,EvidenceError
from skeleton.ai.game_builder.grounded_quest_qualification import qualify_grounded_quest

KEY_ENV="SKELETON_LOCAL_ROUTE_APPROVAL_KEY_HEX"


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order",required=True)
    parser.add_argument("--expected-order-sha256",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit signed-route operator required")
        raw=os.environ.get(KEY_ENV,"")
        if not 64<=len(raw)<=256 or any(c not in "0123456789abcdef" for c in raw):
            raise EvidenceError("local route approval key unavailable")
        key=bytes.fromhex(raw)
        order,sha=read_document(args.order)
        pin(sha,args.expected_order_sha256)
        result=qualify_grounded_quest(order,key=key,authorized=True)
        print(canonical(result).decode("ascii"))
        return 0
    except (ValueError,TypeError,KeyError,PermissionError,OSError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
