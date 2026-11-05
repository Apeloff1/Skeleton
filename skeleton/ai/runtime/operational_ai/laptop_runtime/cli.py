"""First usable laptop AI: verified GGUF -> durable native inference or loopback API.

No model artifact generation, network fallback, credential printing or
implicit configuration repair. All model installation is an explicit prior step.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from .contracts import ContractViolation,token,utf8
from .source_guard import LocalSourceFence, SourceFencedLaptopDispatcher
from .publication import emit_native_jsonl
from .run_once import generate_once
from .first_turn_acceptance import run as run_first_turn_acceptance
from .cold_reopen_acceptance import run as run_cold_reopen_acceptance
from .server import LaptopHTTPServer
from .startup import activate_checked
from .preflight import validate_native_shape
from .contracts import identifier

class _RedactedArguments(argparse.ArgumentParser):
    """Do not expose private command arguments in automatic usage errors."""

    def error(self, message: str) -> None:
        raise ContractViolation("invalid local AI command-line arguments")


def main(argv=None):
    p=_RedactedArguments(description="Real first-usable offline AI laptop runtime")
    p.add_argument("--model-root",type=Path,required=True)
    p.add_argument("--state-dir",type=Path,required=True)
    p.add_argument("--tenant",required=True)
    p.add_argument("--subject",required=True)
    p.add_argument("--mode",choices=("once","serve","acceptance","cold-reopen"),required=True)
    p.add_argument("--approve-real-acceptance",action="store_true",
                   help="Explicitly permit one source-installed native inference acceptance run")
    p.add_argument("--session")
    p.add_argument("--request-id")
    p.add_argument("--prompt-stdin",action="store_true",
                   help="Read one bounded local prompt from stdin instead of process arguments")
    p.add_argument("--port",type=int,default=8765)
    p.add_argument("--context",type=int,default=2048)
    p.add_argument("--max-new-tokens",type=int,default=256)
    p.add_argument("--threads",type=int,default=4)
    p.add_argument("--inference-ms",type=int,default=90000,
                   help="Maximum native generation deadline, 100 to 600000 ms")
    p.add_argument("--gpu-layers",type=int,default=0)
    p.add_argument("--capacity-root",type=Path)
    p.add_argument("--capacity-budget-bytes",type=int,default=8000000000)
    p.add_argument("--capacity-slots",type=int,default=1)
    try:
        args=p.parse_args(argv)
        # Pure admission before reading private task bytes, source installer
        # receipts, creating SQLite state, or starting an isolated GGUF.
        identifier(args.tenant,"tenant")
        identifier(args.subject,"subject")
        for label, value in (
            ("model root",args.model_root),
            ("state directory",args.state_dir),
            ("capacity root",args.capacity_root),
        ):
            if value is None and label == "capacity root":
                continue
            if (not isinstance(value,Path) or not value.is_absolute()
                    or ".." in value.parts or chr(0) in str(value)):
                raise ContractViolation("absolute canonical private "+label+" required")
        if args.session is not None:
            identifier(args.session,"session")
        if args.request_id is not None:
            identifier(args.request_id,"request ID")
        validate_native_shape(
            n_ctx=args.context, max_new_tokens=args.max_new_tokens,
            n_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_budget_bytes=args.capacity_budget_bytes,
            capacity_slots=args.capacity_slots,
            inference_ms=args.inference_ms,
        )
        if type(args.port) is not int or not 1 <= args.port <= 65535:
            raise ContractViolation("finite loopback port required")
        if args.mode in ("once","acceptance","cold-reopen") and not args.prompt_stdin:
            raise ContractViolation("native one-shot command requires --prompt-stdin")
        if args.mode=="serve" and (args.prompt_stdin or args.session or args.request_id):
            raise ContractViolation("server cannot combine one-shot options")
        if args.mode in ("acceptance","cold-reopen"):
            if args.approve_real_acceptance is not True:
                raise ContractViolation("explicit real native acceptance approval required")
            if args.session is not None or args.request_id is not None:
                raise ContractViolation("native acceptance must allocate a new durable request")
        elif args.approve_real_acceptance:
            raise ContractViolation("real acceptance approval is restricted to acceptance mode")
        bearer=None
        if args.mode=="serve":
            bearer=token(os.environ.get("SKELETON_LOCAL_AI_BEARER",""))
        if args.mode in ("once","acceptance","cold-reopen"):
            raw=sys.stdin.buffer.read(32769)
            if len(raw)>32768:raise ContractViolation("stdin prompt exceeds byte ceiling")
            # Preserve exact private task indentation and trailing line breaks.
            # UTF-8 validation still rejects empty and whitespace-only input.
            message=utf8(raw.decode("utf-8","strict"),maximum=32768)
        if args.mode=="cold-reopen":
            published=[False]
            def publish_cold(worker,installed,report):
                guard=LocalSourceFence(
                    worker,installed,tenant=args.tenant,subject=args.subject,
                )
                emit_native_jsonl(worker,guard,{
                    "status":"native-cold-reopen-sqlite-verified",
                    "evidence":report,"release_certified":False,
                },sys.stdout,maximum_result_bytes=65536)
                published[0]=True
            # Two canonical, independently source-approved GGUF startups.
            # First context is closed before reading the same SQLite commit
            # from the second; no model-generated text or prompt is printed.
            report=run_cold_reopen_acceptance(
                model_root=args.model_root, state_dir=args.state_dir,
                tenant=args.tenant, subject=args.subject, prompt=message,
                approved=True, n_ctx=args.context,
                max_new_tokens=args.max_new_tokens, n_threads=args.threads,
                gpu_layers=args.gpu_layers, capacity_root=args.capacity_root,
                capacity_slots=args.capacity_slots,
                capacity_budget_bytes=args.capacity_budget_bytes,
                inference_ms=args.inference_ms,
                publisher=publish_cold,
            )
            if published[0] is not True:
                raise ContractViolation(
                    "cold native result not published through live source"
                )
            return 0
        stack,worker,installed=activate_checked(model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,n_ctx=args.context,
            max_new_tokens=args.max_new_tokens,n_threads=args.threads,
            gpu_layers=args.gpu_layers,isolated=True,
            capacity_root=args.capacity_root,
            capacity_slots=args.capacity_slots,
            capacity_budget_bytes=args.capacity_budget_bytes,
            inference_ms=args.inference_ms)
        with stack:
            source_fence=LocalSourceFence(
                worker,installed,tenant=args.tenant,subject=args.subject,
            )
            if args.mode=="acceptance":
                result=run_first_turn_acceptance(
                    worker,prompt=message,approved=True,
                    installed_receipt=installed, require_real=True,
                )
                # Return only hashes, counts and the new durable identifiers,
                # never the private stdin prompt or raw model output.
                emit_native_jsonl(worker,source_fence,{
                    "status":"real-first-turn-native-replay-checked",
                    "evidence":result,
                    "release_certified":False,
                },sys.stdout)
                return 0
            if args.mode=="once":
                result=generate_once(
                    worker,message,session=args.session,
                    request_id=args.request_id,
                    dispatcher=SourceFencedLaptopDispatcher(worker,source_fence),
                )
                emit_native_jsonl(worker,source_fence,{
                    "status":"real-offline-turn-committed",
                    "output":result,
                    "release_certified":False,
                },sys.stdout)
                return 0
            with LaptopHTTPServer(
                ("127.0.0.1",args.port),
                SourceFencedLaptopDispatcher(worker,source_fence),bearer,
            ) as server:
                emit_native_jsonl(worker,source_fence,{
                    "status":"native-loopback-listening",
                    "host":"127.0.0.1","port":server.server_port,
                    "model_sha256":worker.spine.identity.model_sha256,
                    "release_certified":False,
                },sys.stdout)
                server.serve_forever(poll_interval=0.2)
        return 0
    except (Exception,KeyboardInterrupt) as exc:
        # No prompt, token, private paths, traceback or model text in stderr.
        print(json.dumps({"status":"held","error_class":type(exc).__name__}),
              file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
