"""Durably retain and reconstruct candidate frontier campaign versions."""
import argparse
import json
import sqlite3
import sys

from skeleton.app.recovered_evidence import canonical,read_document,pin
from skeleton.app.frontier_campaign_archive import append_campaign,audit_archive


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",required=True)
    parser.add_argument("--scope",required=True)
    parser.add_argument("--expected-head",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    sub=parser.add_subparsers(dest="action",required=True)
    append=sub.add_parser("append")
    append.add_argument("--order",required=True)
    append.add_argument("--expected-order-sha256",required=True)
    audit=sub.add_parser("audit")
    audit.add_argument("--retention",type=int,default=32)
    audit.add_argument("--history-limit",type=int,default=32)
    audit.add_argument("--campaign-id")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit archive operator required")
        if args.action=="append":
            order,sha=read_document(args.order)
            pin(sha,args.expected_order_sha256)
            result=append_campaign(args.db,args.scope,order,expected_head=args.expected_head,authorized=True)
        else:
            result=audit_archive(args.db,args.scope,expected_head=args.expected_head,
                                 retention=args.retention,history_limit=args.history_limit,
                                 campaign_id=args.campaign_id,authorized=True)
        print(canonical(result).decode("ascii"))
        return 0
    except (ValueError,TypeError,KeyError,PermissionError,OSError,sqlite3.Error) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
