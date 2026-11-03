"""Operator-only, locally source-checked GGUF entry point for Jeeves.

No hosted provider fallback. No automatic tool grants. No auto-installation.
Model text and user task enter only via bounded stdin and explicit stdout.
No password, token or private prompt appears in exception messages.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import time
from pathlib import Path
import sys

from skeleton.ai.runtime.operational_ai.laptop_runtime.startup import activate_checked
from .native_runtime import NativeJeevesRuntime
from .native_chat import NativeJeevesChat
from .native_repl import NativeJeevesRepl
from .native_signed_evidence import (
    NativeSignedEvidenceProvider, attach_signed_native_evidence,
)
from .native_source_tool import (
    BoundSignedSourceTool, readonly_source_grant,
)
from .tools import ToolRegistry
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
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--signed-source-manifest", type=Path)
    parser.add_argument("--max-sources", type=int, default=4)
    parser.add_argument("--enable-source-tool", action="store_true")
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
            if (args.source_root is None) != (args.signed_source_manifest is None):
                raise ValueError("private source root and signed manifest must be paired")
            if args.enable_source_tool and (args.mode != "agent" or args.source_root is None):
                raise ValueError("source tool requires explicit agent mode and signed source")
            if args.mode == "agent" and args.source_root is not None and not args.enable_source_tool:
                raise ValueError("agent source material requires an explicit tool grant")
            source_provider = None
            if args.source_root is not None:
                from skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli import (
                    _environment_key, _read_private_manifest,
                )
                from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope
                manifest = _read_private_manifest(args.signed_source_manifest)
                source_provider = NativeSignedEvidenceProvider(
                    source_root=args.source_root,
                    raw_manifest=manifest,
                    operator_key=_environment_key(),
                    scope=Scope(
                        args.tenant, args.subject,
                        worker.spine.identity.model_sha256,
                        worker.spine.identity.tokenizer_sha256,
                    ),
                    maximum_sources=args.max_sources,
                    clock=time.time,
                )
                if args.mode != "agent":
                    # The native chat prompt is the actual bounded question.
                    # Agent model prompts are structured envelopes and
                    # retrieval is instead an explicitly granted host tool.
                    attach_signed_native_evidence(worker, source_provider)
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
            registry = ToolRegistry()
            grants = ()
            if args.enable_source_tool:
                BoundSignedSourceTool(
                    source_provider,
                    worker.spine.identity,
                ).install(registry)
                grants = (readonly_source_grant(maximum_calls=3),)
            run = NativeJeevesRuntime(worker, tools=registry)
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
                    max_tool_calls=3 if args.enable_source_tool else 1,
                    max_tokens=min(
                        100_000,
                        args.max_output_tokens * args.max_model_calls * 2,
                    ),
                    max_wall_seconds=args.max_wall_seconds,
                ),
                preferred_provider="jeeves_native",
                grants=grants,
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
