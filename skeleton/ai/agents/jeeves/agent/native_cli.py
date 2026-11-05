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
from skeleton.ai.runtime.operational_ai.laptop_runtime.publication import emit_native_jsonl
from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    identifier, utf8,
)
from .native_runtime import NativeJeevesRuntime
from .native_chat import NativeJeevesChat
from .native_repl import NativeJeevesRepl
from .native_signed_evidence import (
    NativeSignedEvidenceProvider, attach_signed_native_evidence,
)
from .native_operator_preflight import check_operator_admission
from .native_source_preflight import verify_sources_before_native_start
from .native_source_tool import (
    BoundSignedSourceTool, readonly_source_grant,
)
from .tools import ToolRegistry
from .native_readiness import inspect_native_jeeves
from .native_source_fence import NativeSourceFence
from .runtime import RunInputs
from .types import Budget, Goal


class _RedactedParser(argparse.ArgumentParser):
    """Never echo a private model path or command token on parse errors."""

    def error(self, message: str) -> None:
        raise ValueError("invalid local Jeeves operator arguments")


def _assert_same_owner(worker, active: ActiveModel) -> None:
    if ActiveModel.from_supervisor(worker) != active:
        raise ValueError("native Jeeves model or operator principal changed")


def main(argv: list[str] | None = None) -> int:
    parser = _RedactedParser(
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
    parser.add_argument("--inference-ms", type=int, default=90000)
    parser.add_argument("--capacity-root", type=Path)
    parser.add_argument("--capacity-budget-bytes", type=int, default=8000000000)
    parser.add_argument("--mode", choices=("chat", "agent", "repl", "durable-agent"), default="agent")
    parser.add_argument("--run-id", help="Explicit principal-bound durable agent run identifier")
    parser.add_argument("--resume-run", action="store_true", help="Operator-authorized cold checkpoint resume; never automatic")
    parser.add_argument("--inspect-run", action="store_true", help="Inspect private durable checkpoint without inference")
    parser.add_argument("--replay-result", action="store_true", help="Replay sealed terminal result without new inference")
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
    try:
        args = parser.parse_args(argv)
        identifier(args.tenant, "tenant")
        identifier(args.subject, "subject")
        for label, value in (
            ("model root", args.model_root),
            ("SQLite state directory", args.state_dir),
            ("capacity root", args.capacity_root),
        ):
            if value is None and label == "capacity root":
                continue
            if (not isinstance(value, Path) or not value.is_absolute()
                    or ".." in value.parts or chr(0) in str(value)):
                raise ValueError("absolute canonical private " + label + " required")
        # This pure stage runs before reading private prompt bytes, loading
        # source keys, validating a model package, or starting native workers.
        check_operator_admission(
            mode=args.mode,
            task_stdin=args.task_stdin,
            session=args.session,
            request_id=args.request_id,
            source_root=args.source_root,
            signed_source_manifest=args.signed_source_manifest,
            enable_source_tool=args.enable_source_tool,
            max_sources=args.max_sources,
            max_steps=args.max_steps,
            max_model_calls=args.max_model_calls,
            max_wall_seconds=args.max_wall_seconds,
            run_id=args.run_id,
            resume_run=args.resume_run,
            inspect_run=args.inspect_run,
            replay_result=args.replay_result,
            context_tokens=args.context,
            output_tokens=args.max_output_tokens,
            native_threads=args.threads,
            gpu_layers=args.gpu_layers,
            capacity_budget_bytes=args.capacity_budget_bytes,
            inference_ms=args.inference_ms,
        )
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
            task = utf8(raw.decode("utf-8", "strict"), maximum=32768)
        source_manifest = None
        operator_key = None
        source_preflight = None
        if args.source_root is not None:
            from skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli import (
                _environment_key, _read_private_manifest,
            )
            source_manifest = _read_private_manifest(args.signed_source_manifest)
            operator_key = _environment_key()
            source_preflight = verify_sources_before_native_start(
                source_root=args.source_root,
                signed_manifest=source_manifest,
                operator_key=operator_key,
                tenant=args.tenant,
                subject=args.subject,
                observed_at=int(time.time()),
                maximum_sources=args.max_sources,
            )
        stack, worker, installed = activate_checked(
            model_root=args.model_root, state_dir=args.state_dir,
            tenant=args.tenant, subject=args.subject,
            n_ctx=args.context, max_new_tokens=args.max_output_tokens,
            n_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
            inference_ms=args.inference_ms,
            isolated=True,
        )
        with stack:
            readiness = inspect_native_jeeves(worker, installed)
            if not readiness.source_bridge_ready:
                raise ValueError("native Jeeves source preflight blocked")
            source_fence = NativeSourceFence(
                worker, installed, expected_tenant=args.tenant,
                expected_subject=args.subject,
            )
            bound = source_fence.principal
            source_provider = None
            if source_preflight is not None:
                source_preflight.verify_active_model(worker.spine.identity)
                source_provider = NativeSignedEvidenceProvider(
                    source_root=args.source_root,
                    raw_manifest=source_manifest,
                    operator_key=operator_key,
                    scope=source_preflight.scope,
                    maximum_sources=args.max_sources,
                    clock=time.time,
                )
                if args.mode != "agent":
                    # The native chat prompt is the actual bounded question.
                    # Agent model prompts are structured envelopes and
                    # retrieval is instead an explicitly granted host tool.
                    attach_signed_native_evidence(worker, source_provider)
            if args.mode == "repl":
                chat = NativeJeevesChat(
                    worker, session_id=args.session, source_fence=source_fence,
                )
                return NativeJeevesRepl(chat, source_fence=source_fence).serve(sys.stdin.buffer, sys.stdout)
            if args.mode == "chat":
                chat = NativeJeevesChat(
                    worker, session_id=args.session, source_fence=source_fence,
                )
                turn = chat.turn(task, request_id=args.request_id)
                source_fence.assert_live(worker)
                emit_native_jsonl(
                    worker, source_fence, {
                        "status": "native-chat-committed",
                        **turn.to_record(),
                    }, sys.stdout,
                )
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
            if args.mode == "durable-agent":
                from .native_durable_runtime import NativeDurableJeevesAgent
                run = NativeDurableJeevesAgent(worker)
            else:
                run = NativeJeevesRuntime(worker, tools=registry)
            digest = sha256(task.encode("utf-8")).hexdigest()
            inputs = RunInputs(
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
                run_id=args.run_id if args.mode == "durable-agent" else None,
            )
            if args.mode == "durable-agent" and args.replay_result:
                historical = run.replay_terminal(inputs)
                source_fence.assert_live(worker)
                emit_native_jsonl(
                    worker, source_fence, historical, sys.stdout,
                )
                return 0
            if args.mode == "durable-agent" and args.inspect_run:
                checkpoint = run.inspect(inputs)
                source_fence.assert_live(worker)
                emit_native_jsonl(
                    worker, source_fence, checkpoint, sys.stdout,
                )
                return 0
            if args.mode == "durable-agent" and args.resume_run:
                result = run.resume_operator_approved(inputs)
            else:
                result = run.run(inputs)
            source_fence.assert_live(worker)
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
            emit_native_jsonl(
                worker, source_fence, record, sys.stdout,
            )
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
