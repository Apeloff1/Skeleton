"""Explicit real GGUF, installer-checked native work-order acceptance CLI."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time

def main(argv=None):
    p=argparse.ArgumentParser(description="Actual approved local GGUF + SQLite work acceptance")
    p.add_argument("--model-root",type=Path,required=True)
    p.add_argument("--spine-state",type=Path,required=True)
    p.add_argument("--work-state",type=Path,required=True)
    p.add_argument("--capacity-root",type=Path,required=True)
    p.add_argument("--tenant",required=True)
    p.add_argument("--subject",required=True)
    p.add_argument("--max-new-tokens",type=int,default=128)
    p.add_argument("--context",type=int,default=2048)
    p.add_argument("--threads",type=int,default=4)
    p.add_argument("--token-ceiling",type=int,default=16384)
    p.add_argument("--approve-real-model-test",action="store_true",required=True)
    p.add_argument("--prompt-stdin",action="store_true",required=True)
    args=p.parse_args(argv)
    try:
        key=os.environ.get("SKELETON_OPERATOR_HMAC_KEY_HEX","")
        if len(key)!=64:raise ValueError("32-byte operator key required from environment")
        operator_key=bytes.fromhex(key)
        message=sys.stdin.buffer.read(32769)
        if len(message)>32768:raise ValueError("prompt exceeds 32768 UTF8 bytes")
        question=message.decode("utf-8","strict").strip()
        from skeleton.ai.runtime.operational_ai.work_orders.acceptance import run_live
        from skeleton.ai.runtime.operational_ai.work_orders.report import snapshot
        from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
        stack,worker,model=activate_checked(
            model_root=args.model_root,state_dir=args.spine_state,
            tenant=args.tenant,subject=args.subject,
            capacity_root=args.capacity_root,n_ctx=args.context,
            n_threads=args.threads,max_new_tokens=args.max_new_tokens,
            isolated=True)
        with stack:
            accepted=run_live(worker=worker,queue_dir=args.work_state,
                tenant=args.tenant,subject=args.subject,prompt_text=question,
                operator_key=operator_key,now_seconds=int(time.time()),
                token_ceiling=args.token_ceiling,
                max_output_tokens=args.max_new_tokens)
        reopened=snapshot(args.work_state,tenant=args.tenant,subject=args.subject,
            model_sha256=accepted["model_sha256"])
        if reopened["integrity"]["head_sha256"]!=accepted["audit_head_sha256"]:
            raise ValueError("cold reopen integrity differs from native work receipt")
        print(json.dumps({"status":"real-native-work-accepted",
            "work":accepted,"cold_reopen_integrity":"matched",
            "release_certified":False},sort_keys=True))
        return 0
    except Exception as exc:
        # Do not include prompt text, API key, private local directory, or traceback.
        print(json.dumps({"status":"held","error_class":type(exc).__name__}),
              file=sys.stderr)
        return 2
if __name__=="__main__":raise SystemExit(main())
