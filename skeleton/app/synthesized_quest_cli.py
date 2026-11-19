"""Operator CLI for synthesized quest plan, play, verify and qualification."""
import argparse
import json
import sys

from skeleton.app.recovered_evidence import EvidenceError, read_document, canonical, pin, fields, array
from skeleton.ai.game_builder.synthesized_quest_planner import plan_campaign
from skeleton.ai.game_builder.synthesized_quest_runtime import Campaign, qualify_campaign, MAX_ACTIONS


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("plan","qualify","play","restore"))
    parser.add_argument("--order",required=True)
    parser.add_argument("--expected-order-sha256")
    parser.add_argument("--plan")
    parser.add_argument("--expected-plan-digest")
    parser.add_argument("--save")
    parser.add_argument("--expected-save-digest")
    parser.add_argument("--actions")
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit local operator required")
        document,source_hash=read_document(args.order)
        if args.expected_order_sha256:
            pin(source_hash,args.expected_order_sha256)
        if args.operation in ("plan","qualify"):
            if any((args.plan,args.expected_plan_digest,args.save,args.expected_save_digest,args.actions)):
                raise EvidenceError("unexpected replay arguments")
            result=(plan_campaign(document,authorized=True) if args.operation=="plan"
                    else qualify_campaign(document,authorized=True))
        else:
            if not args.plan or not args.expected_plan_digest:
                raise EvidenceError("independent plan required")
            plan,_=read_document(args.plan)
            if args.operation=="restore":
                if not args.save or not args.expected_save_digest:
                    raise EvidenceError("independent save required")
                saved,_=read_document(args.save)
                run=Campaign.restore(document,plan,saved,expected_plan_digest=args.expected_plan_digest,
                                     expected_save_digest=args.expected_save_digest,authorized=True)
            else:
                if args.save or args.expected_save_digest:
                    raise EvidenceError("use restore for saves")
                run=Campaign.start(document,plan,expected_plan_digest=args.expected_plan_digest,authorized=True)
            if args.actions:
                actions,_=read_document(args.actions)
                fields(actions,{"actions"})
                for action in array(actions["actions"],0,MAX_ACTIONS):
                    run.apply(action)
            result=run.snapshot()
        print(canonical(result).decode("ascii"))
        return 0
    except (ValueError,PermissionError,TypeError,KeyError,OSError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
