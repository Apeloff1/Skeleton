"""Build or independently verify review-only GLB wing animation page archives."""
import argparse
import json
import sys
from skeleton.app.recovered_evidence import canonical,read_document,pin
from skeleton.app.frontier_wing_export_custody import operate


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("export","verify"))
    parser.add_argument("--order",required=True)
    parser.add_argument("--expected-order-sha256",required=True)
    parser.add_argument("--archive",required=True)
    parser.add_argument("--expected-archive-sha256")
    parser.add_argument("--sample-stride",type=int,default=1)
    parser.add_argument("--page-frames",type=int,default=17)
    parser.add_argument("--allow-reference-defects",action="store_true")
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit asset export operator required")
        order,sha=read_document(args.order)
        pin(sha,args.expected_order_sha256)
        report=operate(order,args.archive,operation=args.operation,sample_stride=args.sample_stride,
                       page_frames=args.page_frames,allow_reference_defects=args.allow_reference_defects,
                       authorized=True,expected_archive_sha256=args.expected_archive_sha256)
        print(canonical(report).decode("ascii"))
        return 0
    except (ValueError,TypeError,KeyError,PermissionError,OSError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
