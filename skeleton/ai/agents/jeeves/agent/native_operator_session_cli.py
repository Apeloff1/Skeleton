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
from .native_source_fence import NativeSourceFence
from .native_operator_preflight import check_native_resource_shape
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identifier


class _RedactedParser(argparse.ArgumentParser):
    """Do not echo untrusted CLI tokens or private paths on argument errors."""

    def error(self, message: str) -> None:
        raise NativeOperatorSessionHold("invalid operator command-line arguments")


def main(argv:list[str]|None=None)->int:
    parser=_RedactedParser(
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
    parser.add_argument("--inference-ms",type=int,default=90000)
    parser.add_argument("--capacity-root",type=Path)
    parser.add_argument("--capacity-budget-bytes",type=int,default=8000000000)
    parser.add_argument("--maximum-commands",type=int,default=128)
    parser.add_argument("--maximum-reserved-model-calls",type=int,default=128)
    parser.add_argument("--maximum-reserved-output-tokens",type=int,default=131072)
    parser.add_argument("--maximum-wall-seconds",type=float,default=3600)
    parser.add_argument("--maximum-result-bytes",type=int,default=262144)
    parser.add_argument("--maximum-session-result-bytes",type=int,default=8388608)
    try:
        args=parser.parse_args(argv)
        if args.approve_native is not True or args.commands_stdin is not True:
            raise NativeOperatorSessionHold("native approval and explicit command stream required")
        # Check identity and paths before private stdin, source bytes or native
        # worker startup. Do not resolve untrusted paths in pure preflight.
        identifier(args.tenant, "tenant")
        identifier(args.subject, "subject")
        for name,value in (
            ("model-root",args.model_root),
            ("state-dir",args.state_dir),
            ("capacity-root",args.capacity_root),
        ):
            if value is None and name == "capacity-root":
                continue
            if (not isinstance(value,Path) or not value.is_absolute()
                    or ".." in value.parts or chr(0) in str(value)):
                raise NativeOperatorSessionHold("absolute canonical private "+name+" required")
        limits=OperatorSessionLimits(
            maximum_commands=args.maximum_commands,
            maximum_reserved_model_calls=args.maximum_reserved_model_calls,
            maximum_reserved_output_tokens=args.maximum_reserved_output_tokens,
            maximum_wall_seconds=args.maximum_wall_seconds,
            maximum_result_bytes=args.maximum_result_bytes,
            maximum_session_result_bytes=args.maximum_session_result_bytes,
        )
        if (type(args.max_output_tokens) is not int
            or not 1<=args.max_output_tokens<=8192
            or args.max_output_tokens>limits.maximum_reserved_output_tokens):
            raise NativeOperatorSessionHold("output reservation exceeds session limits")
        check_native_resource_shape(
            context_tokens=args.context,
            output_tokens=args.max_output_tokens,
            native_threads=args.threads,
            gpu_layers=args.gpu_layers,
            capacity_budget_bytes=args.capacity_budget_bytes,
            inference_ms=args.inference_ms,
        )
        # This structural check never proves installed rights or device capacity.
        # A signed model installer must already have approved all actual
        # weights. No model installation, network or rights shortcut occurs.
        stack,worker,installed=activate_checked(
            model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,
            n_ctx=args.context,max_new_tokens=args.max_output_tokens,
            n_threads=args.threads,gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
            inference_ms=args.inference_ms,
            isolated=True,
        )
        with stack:
            verified=inspect_native_jeeves(worker,installed)
            if not verified.source_bridge_ready:
                raise NativeOperatorSessionHold("source-bound native Jeeves activation unverified")
            # A structural readiness summary is NOT a real authorization.
            # Validate the canonical isolated child, held capacity lease,
            # installed archive and exact owner before private JSONL I/O.
            source_fence=NativeSourceFence(
                worker,installed,expected_tenant=args.tenant,
                expected_subject=args.subject,
            )
            session=NativeOperatorSession(
                worker,approved=True,limits=limits,
                source_fence=source_fence,
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
