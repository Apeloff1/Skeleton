"""Operator-only, locally source-checked GGUF entry point for Jeeves.

No hosted provider fallback. No automatic tool grants. No auto-installation.
Model text and user task enter only via bounded stdin and explicit stdout.
No password, token or private prompt appears in exception messages.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from .native_runtime import NativeJeevesRuntime
from .native_chat import NativeJeevesChat
from .native_repl import NativeJeevesRepl
from .native_readiness import inspect_native_jeeves
from .runtime import RunInputs
from .types import Budget, Goal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Host-guarded Jeeves against a source-verified real local GGUF"
    )
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--capacity-root", type=Path)
    parser.add_argument("--capacity-budget-bytes", type=int, default=8000000000)
    parser.add_argument("--mode", choices=("chat", "agent", "repl"), default="agent")
    parser.add_argument("--session")
    parser.add_argument("--request-id")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--max-model-calls", type=int, default=8)
    parser.add_argument("--max-wall-seconds", type=float, default=180)
    parser.add_argument(
        "--task-stdin", action="store_true",
        help="Read a bounded task from stdin (never place prompts in process args)",
    )
    args = parser.parse_args(argv)
    try:
        if args.mode == "repl":
            if args.task_stdin or args.request_id:
                raise ValueError("REPL reads lines directly and assigns unique request IDs")
            task = None
        else:
            if not args.task_stdin:
                raise ValueError("--task-stdin explicitly required")
            raw = sys.stdin.buffer.read(32769)
            if not 1 <= len(raw) <= 32768:
                raise ValueError("task stdin byte limit violated")
            task = raw.decode("utf-8", "strict").strip()
            if not task:
                raise ValueError("task cannot be empty")
        stack, worker, installed = activate_checked(
            model_root=args.model_root, state_dir=args.state_dir,
            tenant=args.tenant, subject=args.subject,
            n_ctx=args.context, max_new_tokens=args.max_output_tokens,
            n_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
            isolated=True,
        )
        with stack:
            readiness = inspect_native_jeeves(worker, installed)
            if not readiness.source_bridge_ready:
                raise ValueError("native Jeeves source preflight blocked")
            if args.mode == "repl":
                chat = NativeJeevesChat(worker, session_id=args.session)
                return NativeJeevesRepl(chat).serve(sys.stdin.buffer, sys.stdout)
            if args.mode == "chat":
                chat = NativeJeevesChat(worker, session_id=args.session)
                turn = chat.turn(task, request_id=args.request_id)
                sys.stdout.write(json.dumps({
                    "status": "native-chat-committed",
                    **turn.to_record(),
                }, sort_keys=True, ensure_ascii=False) + "\n")
                return 0
            if args.session or args.request_id:
                raise ValueError("chat identifiers cannot be supplied in agent mode")
            run = NativeJeevesRuntime(worker)
            digest = sha256(task.encode("utf-8")).hexdigest()
            result = run.run(RunInputs(
                goal=Goal(
                    goal_id="jeeves_native_" + digest[:24],
                    objective=task,
                    constraints=(
                        "No unapproved external tools or data writes.",
                        "Mark uncertain claims unresolved.",
                    ),
                ),
                tenant_id=args.tenant,
                user_id=args.subject,
                budget=Budget(
                    max_steps=args.max_steps,
                    max_model_calls=args.max_model_calls,
                    max_tool_calls=1,
                    max_tokens=min(
                        100_000,
                        args.max_output_tokens * args.max_model_calls * 2,
                    ),
                    max_wall_seconds=args.max_wall_seconds,
                ),
                preferred_provider="jeeves_native",
            ))
            record = {
                "schema": "jeeves.native_operator_turn.v1",
                "status": "verified-agent-response" if result.success else "held",
                "run_id": result.run_id,
                "goal_id": result.goal_id,
                "success": result.success,
                "termination_reason": result.reason.value,
                "usage": {
                    "model_calls": result.usage.model_calls,
                    "prompt_tokens": result.usage.prompt_tokens,
                    "completion_tokens": result.usage.completion_tokens,
                },
                "trace_fingerprint": result.trace_fingerprint,
                "native_model_sha256": run.identity.model_sha256,
                "device_qualified": False,
                "release_certified": False,
            }
            if result.success:
                # stdout is an explicit local disclosure to the invoking
                # operator; model text never enters shell arguments or stderr.
                record["answer"] = result.answer
            sys.stdout.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
            return 0 if result.success else 2
    except (Exception, KeyboardInterrupt) as exc:
        # Keep private task, source paths, installation receipts and native
        # exception text out of stderr, CI metadata and operational telemetry.
        sys.stderr.write(json.dumps({
            "schema": "jeeves.native_operator_error.v1",
            "status": "held",
            "error_class": type(exc).__name__,
            "device_qualified": False,
            "release_certified": False,
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
