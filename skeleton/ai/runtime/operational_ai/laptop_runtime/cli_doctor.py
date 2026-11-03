"""Separate read-only installed source and state integrity diagnostics."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from .installation import source_receipt
from .restart_probe import inspect_restart
from .contracts import identifier

def main(argv=None):
    parser=argparse.ArgumentParser(description="Read-only verified laptop AI doctor")
    parser.add_argument("--model-root",type=Path,required=True)
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--subject",required=True)
    parser.add_argument("--model-sha256",required=True)
    parser.add_argument("--tokenizer-sha256",required=True)
    args=parser.parse_args(argv)
    try:
        report=source_receipt(args.model_root,expected_model_sha256=args.model_sha256)
        state=inspect_restart(state_dir=args.state_dir,
             tenant=args.tenant,subject=args.subject,
             model_sha256=args.model_sha256,tokenizer_sha256=args.tokenizer_sha256)
        print(json.dumps({"status":"source-and-state-inspected",
            "model_sha256":report.model_sha256,
            "model_bytes":report.model_bytes,
            "rights_approved":report.rights_approved,
            "source_receipt_present":True,
            "state":state,
            "native_model_generated":False,
            "release_certified":False},sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"held","error_class":type(exc).__name__}),
              file=sys.stderr)
        return 2

if __name__=="__main__":raise SystemExit(main())
