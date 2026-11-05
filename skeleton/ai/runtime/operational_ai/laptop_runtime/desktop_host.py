"""One live installed GGUF + one SQLite owner for a private desktop UI.

Only the canonical NativeJeevesChat may generate text. Commands arrive over a
bounded private binary pipe. There is no HTTP listener, hosted fallback, file
tool, second database, implicit memory permission or automatic native retry.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import threading
from typing import BinaryIO

from .contracts import ContractViolation, identifier
from .desktop_protocol import (
    DesktopProtocolHold, MAX_INBOUND, MAX_OUTBOUND, MAX_PROMPT,
    read_frame, require_command, response, write_frame,
)
from .desktop_conversation import compose_conversation, view_history
from .identity import ActiveModel
from .startup import activate_checked


class DesktopHostHold(ValueError):
    """A terminal desktop host violation, never permission to retry inference."""


@dataclass(frozen=True, slots=True)
class DesktopHostLimits:
    maximum_commands: int = 1024
    maximum_publication_bytes: int = 16 * 1024 * 1024
    maximum_history_messages: int = 128
    maximum_history_bytes: int = 131072

    def __post_init__(self):
        for name, value, lo, hi in (
            ("maximum_commands", self.maximum_commands, 1, 65536),
            ("maximum_publication_bytes", self.maximum_publication_bytes, 1024, 67108864),
            ("maximum_history_messages", self.maximum_history_messages, 1, 512),
            ("maximum_history_bytes", self.maximum_history_bytes, 1024, 262144),
        ):
            if type(value) is not int or not lo <= value <= hi:
                raise DesktopHostHold("invalid bounded desktop host " + name)


class DesktopHost:
    """All desk commands share exactly one supervised native GGUF worker."""

    def __init__(
        self, worker, installed, *, tenant: str, subject: str,
        resume_session: str | None = None,
        limits: DesktopHostLimits | None = None,
        signed_source: object | None = None,
        preload_admission: object | None = None,
    ) -> None:
        # Delayed import keeps pure framing tests independent of native GGUF.
        from skeleton.jeeves.agent.native_chat import NativeJeevesChat
        from skeleton.jeeves.agent.native_source_fence import NativeSourceFence

        self.worker = worker
        self.tenant = identifier(tenant, "tenant")
        self.subject = identifier(subject, "subject")
        self.limits = limits or DesktopHostLimits()
        if not isinstance(self.limits, DesktopHostLimits):
            raise DesktopHostHold("typed private desktop limits required")
        self.source = NativeSourceFence(
            worker, installed, expected_tenant=self.tenant,
            expected_subject=self.subject,
        )
        self.identity = ActiveModel.from_supervisor(worker)
        from .desktop_preload_admission import PreloadAdmission
        if preload_admission is not None:
            if (
                type(preload_admission) is not PreloadAdmission
                or preload_admission.model_sha256 != self.identity.model_sha256
            ):
                raise DesktopHostHold(
                    "live preloader model differs from activated native owner",
                )
        self.preload_admission = preload_admission
        self.source.assert_live(worker)
        from .desktop_signed_source import ActivatedSignedSource
        if signed_source is not None and type(signed_source) is not ActivatedSignedSource:
            raise DesktopHostHold("signed source tool requires canonical admission")
        if signed_source is not None:
            signed_source.assert_current(worker)
        self.signed_source = signed_source
        if resume_session is not None:
            identifier(resume_session, "reopened session")
        # SQLite create or resume is authenticated by NativeJeevesChat.
        self.chat = NativeJeevesChat(
            worker, session_id=resume_session, source_fence=self.source,
        )
        self._chat_class = NativeJeevesChat
        self._commands = 0
        self._publication_bytes = 0
        self._output_uncertain = False
        self._stopped = False
        self._lock = threading.RLock()

    def _live(self):
        if self._stopped:
            raise DesktopHostHold("desktop host already terminated")
        self.source.assert_live(self.worker)
        if ActiveModel.from_supervisor(self.worker) != self.identity:
            raise DesktopHostHold("desktop host source principal drifted")

    def _public(self, status: str, **fields: object) -> dict[str, object]:
        return response(
            status, session_id=self.chat.session_id if self.chat else None,
            model_sha256=self.identity.model_sha256, **fields,
        )

    def handle(self, item: object) -> tuple[dict[str, object], bool]:
        """Process one explicitly authorized operator action; never retry."""
        with self._lock:
            req = require_command(item)
            self._live()
            op = req["op"]
            if op == "quit":
                return self._public("session-preserved-for-resume"), True
            if op == "status":
                return self._public(
                    "ready" if self.chat else "no-active-session",
                    tenant=self.tenant, subject=self.subject,
                    commands_processed=self._commands,
                    physical_device_qualified=False,
                ), False
            if op == "source-status":
                active = getattr(self, "signed_source", None)
                if active is not None:
                    active.assert_current(self.worker)
                self._live()
                return self._public(
                    "signed-source-status",
                    signed_source_tool_active=active is not None,
                    signed_source=active.public_metadata if active else None,
                    physical_device_qualified=False,
                ), False
            if op == "telemetry":
                # Only the already active, source-checked supervisor provides
                # the runtime state. No model generation or extra store.
                from .budget_observer import inspect as observe_runtime
                observed = observe_runtime(self.worker)
                self._live()
                return self._public(
                    "observed-runtime-capacity", observed=observed,
                    physical_device_qualified=False,
                ), False
            if op == "agent":
                # Reuse this single installed native worker and source fence.
                # The existing strict Jeeves runtime owns planner/verifier
                # state; tool registry is empty and no grants are supplied.
                from .desktop_agent_mode import run_agent
                report = run_agent(
                    self.worker, self.source,
                    tenant=self.tenant, subject=self.subject,
                    prompt=req["prompt"], run_id=req["run_id"],
                    maximum_steps=req.get("maximum_steps", 8),
                    maximum_model_calls=req.get("maximum_model_calls", 8),
                    maximum_wall_seconds=req.get("maximum_wall_seconds", 180),
                    signed_source=getattr(self, "signed_source", None),
                    reasoning_profile=req.get("profile", "guarded"),
                )
                self._live()
                if report.get("success") is not True:
                    raise DesktopHostHold("strict Jeeves agent result held")
                return self._public(
                    "verified-agent-response",
                    run_id=req["run_id"], agent=report,
                    physical_device_qualified=False,
                ), False
            if op == "durable":
                # The existing NativeDurableJeevesAgent owns all real SQLite
                # checkpoints, restart fences and explicit recovery authority.
                from .desktop_durable_work import run_durable
                report = run_durable(
                    self.worker, self.source,
                    action=req["action"],
                    tenant=self.tenant, subject=self.subject,
                    task=req["prompt"], run_id=req["run_id"],
                    maximum_steps=req.get("maximum_steps", 8),
                    maximum_model_calls=req.get("maximum_model_calls", 8),
                    maximum_wall_seconds=req.get("maximum_wall_seconds", 180),
                )
                self._live()
                status = report.get("status")
                if status == "inspected":
                    label = "durable-work-inspected"
                elif status == "terminal-replayed":
                    label = "durable-work-replayed"
                elif status == "terminal-committed":
                    label = "durable-work-committed"
                else:
                    raise DesktopHostHold("durable native result held for inspection")
                return self._public(
                    label, run_id=req["run_id"], durable=report,
                    physical_device_qualified=False,
                ), False
            if op == "new":
                self.chat = self._chat_class(self.worker, source_fence=self.source)
                self._live()
                return self._public("new-durable-session"), False
            if op == "resume":
                # NativeJeevesChat verifies the binding and SQLite history.
                # Never adopt an existing foreign or closed session.
                resumed = self._chat_class(
                    self.worker, session_id=req["session_id"],
                    source_fence=self.source,
                )
                self._live()
                self.chat = resumed
                return self._public("existing-durable-session-reopened"), False
            if self.chat is None:
                raise DesktopHostHold("create or resume a session first")
            if op == "close":
                closed = self.chat.close()
                self._live()
                identifier(self.chat.session_id, "closed session")
                prior = self.chat.session_id
                self.chat = None
                return response(
                    "durable-session-closed", session_id=None,
                    closed_session_id=prior,
                    model_sha256=self.identity.model_sha256, closed=closed,
                    release_certified=False,
                ), False
            if op == "history":
                # The same canonical SQLite, never a UI-owned transcript store.
                history = self.chat.history(
                    maximum_messages=self.limits.maximum_history_messages,
                    maximum_total_bytes=self.limits.maximum_history_bytes,
                )
                self._live()
                visible = view_history(
                    history,
                    maximum_messages=self.limits.maximum_history_messages,
                    maximum_bytes=self.limits.maximum_history_bytes,
                )
                return self._public(
                    "durable-history", messages=visible,
                    message_count=len(visible),
                ), False
            if op == "turn":
                # Explicit contextual conversation is constructed only from
                # this same principal-bound, committed canonical SQLite.
                # No second store, model, memory grant or source inspector.
                prompted = req["prompt"]
                context_count = 0
                if req.get("context", False) is True:
                    previous = self.chat.history(
                        maximum_messages=self.limits.maximum_history_messages,
                        maximum_total_bytes=self.limits.maximum_history_bytes,
                    )
                    self._live()
                    prompted, context_count = compose_conversation(
                        prompted, previous,
                        max_prompt_bytes=min(
                            MAX_PROMPT, self.worker.spine.limits.input_bytes,
                        ),
                    )
                # Exactly one assigned request ID; a lost stdout frame is an
                # uncertain outcome, not a request to regenerate the prompt.
                turn = self.chat.turn(
                    prompted, request_id=req["request_id"],
                    seed=req.get("seed", 0),
                    temperature=req.get("temperature", 0.8),
                )
                self._live()
                return self._public(
                    "committed-native-chat-turn", turn=turn.to_record(),
                    request_id=turn.request_id,
                    context_messages=context_count,
                ), False
            raise DesktopHostHold("unapproved desktop command")

    def _emit(self, target: BinaryIO, result: dict[str, object]):
        # Charge before publishing; never refund after an unknown partial write.
        from .desktop_protocol import encoded
        encoded_bytes = len(encoded(result, limit=MAX_OUTBOUND))
        if self._publication_bytes + encoded_bytes > self.limits.maximum_publication_bytes:
            raise DesktopHostHold("private desktop disclosure budget exhausted")
        self._publication_bytes += encoded_bytes
        self._output_uncertain = True
        write_frame(
            target, result, limit=MAX_OUTBOUND,
            source_check=lambda: self.source.assert_live(self.worker),
        )
        self._output_uncertain = False

    def serve(self, incoming: BinaryIO, outgoing: BinaryIO) -> int:
        """Single bounded ownership of stdin; no daemon or background model."""
        with self._lock:
            if self._stopped:
                raise DesktopHostHold("desktop host already terminated")
            try:
                self._live()
                self._emit(outgoing, self._public(
                    "native-gguf-ready", tenant=self.tenant,
                    subject=self.subject, source_bound=True,
                    preload_admission=(
                        self.preload_admission.to_public()
                        if getattr(self, "preload_admission", None) is not None
                        else None
                    ),
                    signed_source_tool_active=(
                        getattr(self, "signed_source", None) is not None
                    ),
                    signed_source_manifest_sha256=(
                        self.signed_source.admission.preflight.manifest_sha256
                        if getattr(self, "signed_source", None) is not None else None
                    ),
                    physical_device_qualified=False,
                ))
                while self._commands < self.limits.maximum_commands:
                    self._live()
                    item = read_frame(incoming, limit=MAX_INBOUND)
                    if item is None:
                        return 0  # EOF preserves committed SQLite session.
                    self._commands += 1
                    result, terminate = self.handle(item)
                    self._emit(outgoing, result)
                    if terminate:
                        return 0
                raise DesktopHostHold("bounded desktop request quota exhausted")
            except (Exception, KeyboardInterrupt) as exc:
                # Native or SQLite uncertainty is terminal: never recover by
                # retrying generation, and never print private error strings.
                if not self._output_uncertain:
                    try:
                        self._emit(outgoing, response(
                            "held", error_class=type(exc).__name__,
                            uncertain_native_effect=True,
                        ))
                    except BaseException:
                        pass
                return 2
            finally:
                self._stopped = True


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise DesktopHostHold("invalid private desktop host arguments")


def _args(argv):
    parser = _PrivateParser(description="Local installed-GGUF desktop worker", allow_abbrev=False)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--approve-native", action="store_true")
    parser.add_argument("--enforce-preload-safety", action="store_true")
    parser.add_argument("--resume-session")
    parser.add_argument("--enable-source-tool", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--signed-source-manifest", type=Path)
    parser.add_argument("--max-sources", type=int, default=4)
    parser.add_argument("--max-source-tool-calls", type=int, default=3)
    parser.add_argument("--context", type=int, default=4096)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--gpu-layers", type=int, default=0)
    parser.add_argument("--inference-ms", type=int, default=90000)
    parser.add_argument("--capacity-root", type=Path)
    parser.add_argument("--capacity-budget-bytes", type=int, default=8000000000)
    parser.add_argument("--maximum-commands", type=int, default=1024)
    parser.add_argument("--maximum-publication-bytes", type=int, default=16777216)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    try:
        args = _args(argv)
        if args.approve_native is not True:
            raise DesktopHostHold("operator must explicitly approve local native activation")
        identifier(args.tenant, "tenant")
        identifier(args.subject, "subject")
        if args.resume_session is not None:
            identifier(args.resume_session, "reopened session")
        for value in (args.model_root, args.state_dir, args.capacity_root):
            if value is None:
                continue
            if (not isinstance(value, Path) or not value.is_absolute()
                    or ".." in value.parts or chr(0) in str(value)):
                raise DesktopHostHold("absolute canonical private host path required")
        from skeleton.jeeves.agent.native_operator_preflight import check_native_resource_shape
        check_native_resource_shape(
            context_tokens=args.context, output_tokens=args.max_output_tokens,
            native_threads=args.threads, gpu_layers=args.gpu_layers,
            capacity_budget_bytes=args.capacity_budget_bytes,
            inference_ms=args.inference_ms,
        )
        limits = DesktopHostLimits(
            maximum_commands=args.maximum_commands,
            maximum_publication_bytes=args.maximum_publication_bytes,
        )
        # Verify all original signed bytes, HMAC, principal and expiry BEFORE
        # loading the licensed GGUF or allocating a native SQLite session.
        signed_admission = None
        if args.enable_source_tool:
            if args.source_root is None or args.signed_source_manifest is None:
                raise DesktopHostHold("signed source root and manifest required")
            from .desktop_signed_source import preflight_signed_source
            signed_admission = preflight_signed_source(
                root=args.source_root, manifest_path=args.signed_source_manifest,
                tenant=args.tenant, subject=args.subject,
                maximum_sources=args.max_sources,
                maximum_tool_calls=args.max_source_tool_calls,
            )
        elif args.source_root is not None or args.signed_source_manifest is not None:
            raise DesktopHostHold("signed source locations require explicit tool approval")
        if (
            type(args.max_sources) is not int or not 1 <= args.max_sources <= 6
            or type(args.max_source_tool_calls) is not int
            or not 1 <= args.max_source_tool_calls <= 3
        ):
            raise DesktopHostHold("invalid finite signed lookup allowance")
        # The GUI's profile is advisory only. The protected startup path
        # takes new CPU/RAM/cgroup/private-disk measurements immediately
        # before activating actual GGUF bytes; it never silently shrinks
        # operator-selected native memory, threads or token limits.
        preload = None
        if args.enforce_preload_safety:
            from .desktop_preload_admission import check_fresh_native_preload
            preload = check_fresh_native_preload(
                model_root=args.model_root, state_dir=args.state_dir,
                n_ctx=args.context, max_new_tokens=args.max_output_tokens,
                n_threads=args.threads, gpu_layers=args.gpu_layers,
                capacity_budget_bytes=args.capacity_budget_bytes,
                inference_ms=args.inference_ms,
            )
        stack, worker, installed = activate_checked(
            model_root=args.model_root, state_dir=args.state_dir,
            tenant=args.tenant, subject=args.subject, n_ctx=args.context,
            max_new_tokens=args.max_output_tokens, n_threads=args.threads,
            gpu_layers=args.gpu_layers, inference_ms=args.inference_ms,
            capacity_root=args.capacity_root,
            capacity_budget_bytes=args.capacity_budget_bytes,
            isolated=True,
        )
        with stack:
            active_sources = None
            if signed_admission is not None:
                from .desktop_signed_source import activate_signed_source
                active_sources = activate_signed_source(signed_admission, worker)
            host = DesktopHost(
                worker, installed, tenant=args.tenant, subject=args.subject,
                resume_session=args.resume_session, limits=limits,
                signed_source=active_sources,
                preload_admission=preload,
            )
            return host.serve(sys.stdin.buffer, sys.stdout.buffer)
    except (Exception, KeyboardInterrupt) as exc:
        # The desktop parent sees EOF, never untrusted traceback/path/prompt.
        sys.stderr.write(json.dumps({
            "status": "held", "error_class": type(exc).__name__,
            "release_certified": False,
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
