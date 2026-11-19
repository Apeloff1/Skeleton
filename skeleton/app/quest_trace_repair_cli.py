"""Run deterministic source-pinned B039 quest trace repair, review only."""
import argparse
import json
import sys

from skeleton.app.recovered_evidence import canonical,read_document,pin
from skeleton.ai.game_builder.quest_trace_repair import repair_trace


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order",required=True)
    parser.add_argument("--expected-order-sha256",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit repair operator required")
        order,sha=read_document(args.order)
        pin(sha,args.expected_order_sha256)
        report=repair_trace(order,authorized=True)
        print(canonical(report).decode("ascii"))
        return 0 if report["eligible_for_human_review"] else 3
    except (ValueError,TypeError,KeyError,PermissionError,OSError,RuntimeError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
