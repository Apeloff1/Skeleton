"""Run synthetic, aggregate-only quest playtest analytics from a bounded order."""
import argparse
import json
import sys

from skeleton.app.recovered_evidence import canonical, read_document, pin
from skeleton.ai.game_builder.quest_playtest_analytics import qualify_cohort


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order",required=True)
    parser.add_argument("--expected-order-sha256",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit synthetic playtest operator required")
        order,sha=read_document(args.order)
        pin(sha,args.expected_order_sha256)
        print(canonical(qualify_cohort(order,authorized=True)).decode("ascii"))
        return 0
    except (ValueError,TypeError,KeyError,PermissionError,OSError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
