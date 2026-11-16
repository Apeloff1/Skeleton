"""Evaluate explicitly supplied RGB/mask frame sequences and production follow-ups."""
import argparse
import json
import sys

from skeleton.app.recovered_evidence import canonical, read_document, pin
from skeleton.game.studio_frame_qualification import qualify_frames


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order",required=True)
    parser.add_argument("--expected-order-sha256",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit reference qualification required")
        order,sha=read_document(args.order)
        pin(sha,args.expected_order_sha256)
        report=qualify_frames(order,authorized=True)
        print(canonical(report).decode("ascii"))
        return 0 if report["reference_sequence_passed"] else 3
    except (ValueError,TypeError,KeyError,PermissionError,OSError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
