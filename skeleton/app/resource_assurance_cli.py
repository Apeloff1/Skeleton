"""Run known local AI assurance suites under measured cooperative admission."""
import argparse
import json
import sys

from skeleton.app.resource_assurance import AdmissionPolicy
from skeleton.app.resource_assurance_runner import run_campaign
from skeleton.app.local_source_assurance import SUITES
from skeleton.app.recovered_evidence import EvidenceError, canonical, read_document


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all",action="store_true")
    selection.add_argument("--suite",choices=SUITES,action="append")
    parser.add_argument("--max-workers",type=int,default=4)
    parser.add_argument("--per-worker-mib",type=int,default=256)
    parser.add_argument("--reserve-mib",type=int,default=512)
    parser.add_argument("--interactive-cores",type=int,default=1)
    parser.add_argument("--samples",type=int,default=3)
    parser.add_argument("--interval-ms",type=int,default=100)
    parser.add_argument("--repeat",action="store_true")
    parser.add_argument("--previous")
    parser.add_argument("--previous-digest")
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit operator required")
        previous=None
        if args.previous:
            previous,_=read_document(args.previous)
        policy=AdmissionPolicy(args.max_workers,args.per_worker_mib,args.reserve_mib,
                               args.interactive_cores,args.samples,args.interval_ms)
        report=run_campaign(SUITES if args.all else args.suite,authorized=True,policy=policy,
                            repeat=args.repeat,previous=previous,previous_digest=args.previous_digest)
        print(canonical(report).decode("ascii"))
        return 0 if report["completed_selection"] else 3
    except (ValueError,TypeError,PermissionError,OSError,RuntimeError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
