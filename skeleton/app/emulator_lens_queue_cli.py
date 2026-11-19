"""Read and reconcile externally signed emulator lens review metadata."""
import argparse
import json
import os
import sys

from skeleton.app.recovered_evidence import canonical,read_document,pin,fields,EvidenceError
from skeleton.app.emulator_lens_work_index import load_index,LANES
from skeleton.app.emulator_lens_receipt_queue import page_queue,GENESIS


def _key(lane):
    value=os.environ.get("SKELETON_LENS_"+lane.upper()+"_KEY_HEX","")
    if not 64<=len(value)<=256 or any(c not in "0123456789abcdef" for c in value):
        raise EvidenceError("local review lane key unavailable")
    return bytes.fromhex(value)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report",required=True)
    parser.add_argument("--source-file-sha256",required=True)
    parser.add_argument("--source-report-digest",required=True)
    parser.add_argument("--receipts")
    parser.add_argument("--receipt-file-sha256")
    parser.add_argument("--expected-submission-head",required=True)
    parser.add_argument("--page",type=int,default=0)
    parser.add_argument("--page-size",type=int,default=64)
    parser.add_argument("--lane",choices=LANES)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit local review operator required")
        keys={lane:_key(lane) for lane in LANES}
        source,sha=read_document(args.source_report)
        pin(sha,args.source_file_sha256)
        index=load_index(source,expected_source_digest=args.source_report_digest,authorized=True)
        receipts=[]
        if args.receipts:
            record,sha=read_document(args.receipts)
            pin(sha,args.receipt_file_sha256)
            fields(record,{"schema","index_digest","receipts"})
            if record["schema"]!="skeleton.emulator-lens-work-receipts.v1" or record["index_digest"]!=index.identity:
                raise EvidenceError("submitted ledger belongs to another review index")
            receipts=record["receipts"]
        elif args.receipt_file_sha256 is not None or args.expected_submission_head!=GENESIS:
            raise EvidenceError("missing submitted receipt ledger")
        report=page_queue(index,receipts,keys=keys,expected_head=args.expected_submission_head,
                          authorized=True,page=args.page,page_size=args.page_size,lane=args.lane)
        print(canonical(report).decode("ascii"))
        return 0
    except (ValueError,TypeError,KeyError,PermissionError,OSError,RuntimeError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
