"""Operator-approved actual local GGUF -> SQLite -> replay -> restart doctor.

This is a real hardware/model test, not runnable without independently
approved installed bytes and a private prepared state directory.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from skeleton.ai.runtime.operational_ai.laptop_runtime.first_turn_acceptance import run
from skeleton.ai.runtime.operational_ai.laptop_runtime.restart_probe import inspect_restart

def main(argv=None):
    parser=argparse.ArgumentParser(description="Live verified offline GGUF acceptance")
    parser.add_argument("--model-root",type=Path,required=True)
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--capacity-root",type=Path,required=True)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--subject",required=True)
    parser.add_argument("--context",type=int,default=2048)
    parser.add_argument("--max-new-tokens",type=int,default=256)
    parser.add_argument("--threads",type=int,default=4)
    parser.add_argument("--prompt-stdin",action="store_true",required=True)
    parser.add_argument("--approve-real-model-test",action="store_true",required=True)
    args=parser.parse_args(argv)
    try:
        raw=sys.stdin.buffer.read(32769)
        if len(raw)>32768:
            raise ValueError("prompt ceiling exceeded")
        prompt=raw.decode("utf-8","strict").strip()
        stack,worker,model=activate_checked(
            model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,
            capacity_root=args.capacity_root,n_ctx=args.context,
            max_new_tokens=args.max_new_tokens,n_threads=args.threads,
            isolated=True)
        with stack:
            actual=run(worker,prompt=prompt,approved=True)
            model_sha=worker.spine.identity.model_sha256
            tokenizer_sha=worker.spine.identity.tokenizer_sha256
        # Reopen the real authoritative database read-only after native
        # shutdown. A second process/device test remains necessary to verify
        # cold restart on target Windows/WSL2 hardware.
        storage=inspect_restart(state_dir=args.state_dir,tenant=args.tenant,
            subject=args.subject,model_sha256=model_sha,
            tokenizer_sha256=tokenizer_sha)
        print(json.dumps({"status":"native-first-turn-replay-restart-observed",
            "model_sha256":model_sha,
            "output_sha256":actual["output_sha256"],
            "replayed_without_second_generation":actual["replayed_without_generation"],
            "state_doctor":storage["state"],
            "rights_approved":model.rights_approved,
            "release_certified":False},sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"held","error_class":type(exc).__name__}),
              file=sys.stderr)
        return 2

if __name__=="__main__":raise SystemExit(main())
