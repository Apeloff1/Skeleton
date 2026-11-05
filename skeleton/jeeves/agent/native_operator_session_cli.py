"""Operator-owned Jeeves durable JSON-lines terminal on one approved GGUF.

No model installation or downloads, no remote inference provider, no
automatic tool grants and no implicit crash retry. The operator must
already have an independently approved, source-bound model installation.

Example:
  python -m skeleton.jeeves.agent.native_operator_session_cli \
    --model-root /private/models/approved \
    --state-dir /private/ai \
    --tenant local --subject operator \
    --approve-native --commands-stdin < /private/commands.jsonl

The stream contains one strict command per line, never a hidden prompt in
process arguments. A line may start, inspect, replay or explicitly resume
a durable task. Output is sent only to the invoking local operator terminal.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from .native_operator_session import (
    NativeOperatorSession,OperatorSessionLimits,NativeOperatorSessionHold,
)
from .native_readiness import inspect_native_jeeves


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(
        description="Source-bound local durable Jeeves multi-run operator terminal",
    )
    parser.add_argument("--model-root",type=Path,required=True)
    parser.add_argument("--state-dir",type=Path,required=True)
    parser.add_argument("--tenant",required=True)
    parser.add_argument("--subject",required=True)
    parser.add_argument("--approve-native",action="store_true")
    parser.add_argument("--commands-stdin",action="store_true")
    parser.add_argument("--context",type=int,default=4096)
    parser.add_argument("--max-output-tokens",type=int,default=1024)
    parser.add_argument("--threads",type=int,default=4)
    parser.add_argument("--gpu-layers",type=int,default=0)
    parser.add_argument("--capacity-root",type=Path)
    parser.add_argument("--capacity-budget-bytes",type=int,default=8000000000)
    parser.add_argument("--maximum-commands",type=int,default=128)
    parser.add_argument("--maximum-reserved-model-calls",type=int,default=128)
    parser.add_argument("--maximum-reserved-output-tokens",type=int,default=131072)
    parser.add_argument("--maximum-wall-seconds",type=float,default=3600)
    args=parser.parse_args(argv)
    try:
        if args.approve_native is not True or args.commands_stdin is not True:
            raise NativeOperatorSessionHold("native approval and explicit command stream required")
        for name,value in (("model-root",args.model_root),
                           ("state-dir",args.state_dir)):
            if not isinstance(value,Path) or not value.is_absolute() or ".." in value.parts:
                raise NativeOperatorSessionHold("absolute private "+name+" required")
        limits=OperatorSessionLimits(
            maximum_commands=args.maximum_commands,
            maximum_reserved_model_calls=args.maximum_reserved_model_calls,
            maximum_reserved_output_tokens=args.maximum_reserved_output_tokens,
            maximum_wall_seconds=args.maximum_wall_seconds,
        )
        if (type(args.max_output_tokens) is not int
            or not 1<=args.max_output_tokens<=8192
            or args.max_output_tokens>limits.maximum_reserved_output_tokens):
            raise NativeOperatorSessionHold("output reservation exceeds session limits")
        # A signed model installer must already have approved all actual
        # weights. No model installation, network or rights shortcut occurs.
        stack,worker,installed=activate_checked(
            model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,
            n_ctx=args.context,max_new_tokens=args.max_output_tokens,
            n_threads=args.threads,gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
            isolated=True,
        )
        with stack:
            verified=inspect_native_jeeves(worker,installed)
            if not verified.source_bridge_ready:
                raise NativeOperatorSessionHold("source-bound native Jeeves activation unverified")
            session=NativeOperatorSession(
                worker,approved=True,limits=limits,
            )
            # The operator explicitly controls when the process starts new
            # native inference. Merely starting the terminal never generates.
            return session.serve(sys.stdin.buffer,sys.stdout)
    except (Exception,KeyboardInterrupt) as exc:
        sys.stderr.write(json.dumps({
            "schema":"jeeves.native_operator_session_cli_error.v1",
            "status":"held","error_class":type(exc).__name__,
            "installed_source_bypassed":False,
            "native_effect_retried":False,
            "release_certified":False,
        },sort_keys=True)+"\n")
        return 2


if __name__=="__main__":
    raise SystemExit(main())


__all__=["main"]
