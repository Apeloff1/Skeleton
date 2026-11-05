"""One-source-approved GGUF, many operator-owned durable Jeeves tasks.

This is an explicit interactive operations protocol for a trusted *local*
operator terminal. Each task receives a separate immutable run identity,
a protected SQLite planner checkpoint and a terminal-result receipt. The
same loaded model is reused across commands without a hosted fallback.
The model never chooses command types, grants, paths or budgets.

Every command is a bounded, duplicate-key-free UTF-8 JSON line on stdin.
The operator can start, inspect, replay or EXPLICITLY resume only an existing
run; failures stop the session rather than silently resubmitting native
effects. The output is private local stdout by operator choice, not telemetry.
This is source/runtime integration, not physical GGUF qualification.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import threading
import time
from typing import Any, BinaryIO, Callable, TextIO

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from skeleton.ai.runtime.operational_ai.authority.canonical import load_json

from .native_durable_runtime import NativeDurableJeevesAgent
from .native_checkpoint_journal import NativeSQLiteCheckpointer
from .native_source_fence import NativeSourceFence
from .runtime import RunInputs
from .types import Budget, Goal
from skeleton.jeeves.native_fabric.contracts import (
    ContractHold, exact_integer, identifier, text,
)


class NativeOperatorSessionHold(ContractHold):
    """Local command, principal, resource budget or recovery boundary held."""


@dataclass(frozen=True, slots=True)
class OperatorSessionLimits:
    maximum_commands: int = 128
    maximum_line_bytes: int = 32768
    maximum_task_bytes: int = 16384
    maximum_reserved_model_calls: int = 128
    maximum_reserved_output_tokens: int = 131072
    maximum_wall_seconds: float = 3600
    maximum_result_bytes: int = 262144
    maximum_session_result_bytes: int = 8388608

    def __post_init__(self):
        for key, maximum in (
            ("maximum_commands", 4096),
            ("maximum_line_bytes", 262144),
            ("maximum_task_bytes", 65536),
            ("maximum_reserved_model_calls", 10000),
            ("maximum_reserved_output_tokens", 10000000),
            ("maximum_result_bytes", 1048576),
            ("maximum_session_result_bytes", 67108864),
        ):
            try:
                exact_integer(getattr(self,key),minimum=1,maximum=maximum)
            except ContractHold as exc:
                # Keep lower-level validation fail-closed, while exposing the
                # stable public operator admission error class to the CLI.
                raise NativeOperatorSessionHold(
                    "invalid bounded operator " + key
                ) from exc
        if self.maximum_task_bytes >= self.maximum_line_bytes:
            raise NativeOperatorSessionHold("command line must fit task plus envelope")
        if self.maximum_session_result_bytes < self.maximum_result_bytes:
            raise NativeOperatorSessionHold(
                "session disclosure ceiling must cover a single result"
            )
        if type(self.maximum_wall_seconds) not in (int,float) or (
            not math.isfinite(self.maximum_wall_seconds) or
            not 0 < self.maximum_wall_seconds <= 86400
        ):
            raise NativeOperatorSessionHold("bounded session wall clock required")


@dataclass(frozen=True, slots=True)
class OperatorCommand:
    operation: str
    run_id: str | None = None
    task: str | None = None
    max_steps: int = 8
    max_model_calls: int = 8
    max_wall_seconds: float = 180

    def __post_init__(self):
        if self.operation not in (
            "start","resume","inspect","replay","status","quit",
        ):
            raise NativeOperatorSessionHold("unrecognized operator command")
        if self.operation in ("status","quit"):
            if self.run_id is not None or self.task is not None:
                raise NativeOperatorSessionHold("session control cannot carry private task")
        else:
            identifier(self.run_id,"run")
            text(self.task,maximum_bytes=16384)
        exact_integer(self.max_steps,minimum=1,maximum=10000)
        exact_integer(self.max_model_calls,minimum=1,maximum=10000)
        if type(self.max_wall_seconds) not in (float,int) or (
            not math.isfinite(self.max_wall_seconds)
            or not 0 < self.max_wall_seconds <= 86400
        ):
            raise NativeOperatorSessionHold("invalid task wall limit")


_COMMAND_FIELDS=frozenset((
    "schema","operation","run_id","task",
    "max_steps","max_model_calls","max_wall_seconds",
))


def parse_operator_command(raw: bytes,*,limit:int=32768)->OperatorCommand:
    exact_integer(limit,minimum=64,maximum=262144)
    if type(raw) is not bytes or not 1<=len(raw)<=limit:
        raise NativeOperatorSessionHold("bounded command bytes required")
    try:
        document=load_json(raw,ceiling=limit)
    except Exception as exc:
        raise NativeOperatorSessionHold("duplicate-key-free strict JSON command required") from exc
    if (type(document) is not dict or
        document.get("schema")!="jeeves.native_operator_command.v1" or
        not {"schema","operation"}<=set(document) or
        not set(document)<=_COMMAND_FIELDS):
        raise NativeOperatorSessionHold("unknown or missing command fields")
    values={key:val for key,val in document.items() if key!="schema"}
    try:
        return OperatorCommand(**values)
    except (ValueError,TypeError) as exc:
        raise NativeOperatorSessionHold("invalid native command typed fields") from exc


class NativeOperatorSession:
    """Serial bounded operator-mode Jeeves atop the existing native supervisor.

    Only this host object chooses the task and budgets. A model output cannot
    be parsed into this command stream; it is returned as untrusted data.
    """

    def __init__(
        self, worker: Any,*,approved: bool,
        limits:OperatorSessionLimits|None=None,
        monotonic:Callable[[],float]=time.monotonic,
        source_fence:NativeSourceFence|None=None,
    ):
        if approved is not True:
            raise NativeOperatorSessionHold("explicit operator native approval required")
        if not callable(monotonic):
            raise NativeOperatorSessionHold("trusted monotonic clock required")
        self.identity=ActiveModel.from_supervisor(worker)
        self.worker=worker
        if source_fence is not None and not isinstance(
            source_fence, NativeSourceFence,
        ):
            raise NativeOperatorSessionHold("canonical native source fence required")
        self.source_fence=source_fence
        if source_fence is not None:
            source_fence.assert_live(worker)
        self.limits=limits or OperatorSessionLimits()
        if not isinstance(self.limits,OperatorSessionLimits):
            raise NativeOperatorSessionHold("typed session budget required")
        self._monotonic=monotonic
        self._started=monotonic()
        if (type(self._started) not in (int,float)
                or not math.isfinite(self._started)):
            raise NativeOperatorSessionHold("finite monotonic session clock required")
        self._closed=False
        self._command_count=0
        self._published_result_bytes=0
        self._reserved_calls=0
        self._reserved_output=0
        self._lock=threading.RLock()
        # A JSONL stream owns this session exclusively until its finally
        # block returns, even while blocking on untrusted bounded stdin.
        self._stream_open=False
        self._stream_thread=None
        self._native_output_ceiling=worker.spine.limits.max_output_tokens

    def _elapsed(self) -> float:
        """Finite monotonic wall-time fence, including publication boundaries.

        A clock regression, NaN, Infinity or expired wall budget makes this
        process-local session terminal rather than extending inference rights.
        """
        try:
            now=self._monotonic()
            if type(now) not in (int,float) or not math.isfinite(now):
                raise NativeOperatorSessionHold("native wall clock unavailable")
            elapsed=now-self._started
            if not math.isfinite(elapsed) or elapsed < 0:
                raise NativeOperatorSessionHold("native wall clock regressed")
            if elapsed >= self.limits.maximum_wall_seconds:
                raise NativeOperatorSessionHold("operator session time budget exhausted")
            return elapsed
        except BaseException:
            self._closed=True
            raise

    def _valid_worker(self):
        try:
            active=ActiveModel.from_supervisor(self.worker)
        except Exception as exc:
            self._closed=True
            raise NativeOperatorSessionHold(
                "native source identity unavailable"
            ) from exc
        if active!=self.identity:
            self._closed=True
            raise NativeOperatorSessionHold("native model epoch/principal changed")
        if self._closed:
            raise NativeOperatorSessionHold("session already stopped")
        self._elapsed()
        if self.source_fence is not None:
            try:
                self.source_fence.assert_live(self.worker)
            except BaseException:
                # A lost lease, installed archive or owner makes this whole
                # process-local operator session terminal, even when a caller
                # invokes dispatch() without the JSONL serve() outer loop.
                self._closed=True
                raise

    def _post_io(self) -> None:
        """Hold private SQLite or model output after a source/owner change.

        A failed post-I/O check permanently closes this process-local
        operator session. The canonical SQLite receipt remains authoritative
        and cannot be regenerated implicitly on an uncertain native effect.
        """
        try:
            self._valid_worker()
        except BaseException:
            self._closed=True
            raise

    def _before_publication(self) -> None:
        """Last source/owner fence after encoding and before stdout.

        Dispatch checks before/after SQLite I/O; however its caller may
        serialize a private result after the lease has been revoked. The
        output stream must not publish that stale result.
        """
        try:
            self._elapsed()
            if ActiveModel.from_supervisor(self.worker)!=self.identity:
                raise NativeOperatorSessionHold(
                    "native operator identity changed before publication"
                )
            if self.source_fence is not None:
                self.source_fence.assert_live(self.worker)
            if ActiveModel.from_supervisor(self.worker)!=self.identity:
                raise NativeOperatorSessionHold(
                    "native operator identity changed during publication check"
                )
        except BaseException:
            self._closed=True
            raise

    def _reserve(self,cmd:OperatorCommand):
        self._valid_worker()
        if cmd.operation not in ("start","resume"):
            return
        # The remaining *session* lifetime must cover the entire explicitly
        # reserved task wall budget. Never launch an inference that cannot
        # fit inside this operator's remaining authorized time window.
        remaining=self.limits.maximum_wall_seconds-self._elapsed()
        if cmd.max_wall_seconds>remaining:
            raise NativeOperatorSessionHold(
                "requested native run outlives remaining operator wall budget"
            )
        output=cmd.max_model_calls*self._native_output_ceiling
        if (self._reserved_calls+cmd.max_model_calls
                > self.limits.maximum_reserved_model_calls
            or self._reserved_output+output
                > self.limits.maximum_reserved_output_tokens):
            raise NativeOperatorSessionHold("global native session budget exhausted")
        # Charge the full possible native budget before any inference. An
        # exception may have performed an unknown effect, so no speculative
        # refunds are granted on failed/uncommitted calls.
        self._reserved_calls+=cmd.max_model_calls
        self._reserved_output+=output

    def _inputs(self,cmd:OperatorCommand)->RunInputs:
        if cmd.operation in ("status","quit"):
            raise NativeOperatorSessionHold("non-task command has no run inputs")
        text(cmd.task,maximum_bytes=self.limits.maximum_task_bytes)
        digest=sha256(cmd.task.encode("utf-8","strict")).hexdigest()
        if (cmd.max_model_calls*self._native_output_ceiling
            > self.limits.maximum_reserved_output_tokens):
            raise NativeOperatorSessionHold("single command exceeds output reservation")
        return RunInputs(
            goal=Goal(
                goal_id="jeeves_native_"+digest[:24],
                objective=cmd.task,
                constraints=(
                    "No unapproved external tools or data writes.",
                    "Mark uncertain claims unresolved.",
                ),
            ),
            tenant_id=self.identity.tenant,
            user_id=self.identity.subject,
            run_id=cmd.run_id,
            preferred_provider="jeeves_native",
            budget=Budget(
                max_steps=cmd.max_steps,
                max_model_calls=cmd.max_model_calls,
                max_tool_calls=1,
                max_tokens=min(
                    100000,
                    self._native_output_ceiling*cmd.max_model_calls*2,
                ),
                max_wall_seconds=cmd.max_wall_seconds,
            ),
        )

    def _result(self,result,*,operation):
        return {
            "schema":"jeeves.native_operator_command_result.v1",
            "operation":operation,"run_id":result.run_id,
            "goal_id":result.goal_id,"success":result.success,
            "termination_reason":result.reason.value,
            "trace_fingerprint":result.trace_fingerprint,
            "usage":{
                "model_calls":result.usage.model_calls,
                "prompt_tokens":result.usage.prompt_tokens,
                "completion_tokens":result.usage.completion_tokens,
                "tool_calls":result.usage.tool_calls,
            },
            **({"answer":result.answer} if result.success else {}),
            "native_model_sha256":self.identity.model_sha256,
            "native_tokenizer_sha256":self.identity.tokenizer_sha256,
            "real_hardware_qualified":False,
            "release_certified":False,
        }

    def dispatch(self,cmd:OperatorCommand)->dict[str,object]:
        if not isinstance(cmd,OperatorCommand):
            raise NativeOperatorSessionHold("typed operator command required")
        with self._lock:
            if (self._stream_open
                    and self._stream_thread != threading.get_ident()):
                raise NativeOperatorSessionHold(
                    "operator command stream exclusively owns native session"
                )
            self._valid_worker()
            if self._command_count>=self.limits.maximum_commands:
                raise NativeOperatorSessionHold("finite command inventory exhausted")
            self._command_count+=1
            if cmd.operation=="quit":
                self._closed=True
                return {
                    "schema":"jeeves.native_operator_command_result.v1",
                    "operation":"quit","status":"closed",
                    "model_calls_started":0,"release_certified":False,
                }
            if cmd.operation=="status":
                journal=NativeSQLiteCheckpointer(self.worker)
                report={
                    "schema":"jeeves.native_operator_command_result.v1",
                    "operation":"status","status":"active",
                    "installed_model_sha256":self.identity.model_sha256,
                    "tokenizer_sha256":self.identity.tokenizer_sha256,
                    "run_count":len(journal.runs()),
                    "commands_seen":self._command_count,
                    "maximum_commands":self.limits.maximum_commands,
                    "reserved_model_calls":self._reserved_calls,
                    "reserved_output_tokens":self._reserved_output,
                    "published_result_bytes":self._published_result_bytes,
                    "maximum_session_result_bytes":self.limits.maximum_session_result_bytes,
                    "actual_model_forward_pass_by_status":False,
                    "release_certified":False,
                }
                self._post_io()
                return report
            inputs=self._inputs(cmd)
            if cmd.operation in ("start","resume"):
                self._reserve(cmd)
            runner=NativeDurableJeevesAgent(self.worker)
            if cmd.operation=="inspect":
                record=runner.inspect(inputs)
                self._post_io()
                return record
            if cmd.operation=="replay":
                record=runner.replay_terminal(inputs)
                self._post_io()
                return record
            try:
                if cmd.operation=="start":
                    result=runner.run(inputs)
                else:
                    result=runner.resume_operator_approved(inputs)
                self._post_io()
            except BaseException:
                # A native call may have committed or become uncertain. Never
                # admit another command in this process after any such failure.
                self._closed=True
                raise
            # Failed terminal planning is still a durable result, but it does
            # not qualify as success and cannot implicitly authorize retry.
            if not result.success:
                self._closed=True
            return self._result(result,operation=cmd.operation)

    def serve(self,source:BinaryIO,destination:TextIO)->int:
        if not callable(getattr(source,"readline",None)) or not callable(
            getattr(destination,"write",None)
        ):
            raise NativeOperatorSessionHold("bounded binary input and text output required")
        with self._lock:
            if self._stream_open or self._closed:
                raise NativeOperatorSessionHold(
                    "operator command stream already active or stopped"
                )
            self._stream_open=True
            self._stream_thread=threading.get_ident()
        try:
            while not self._closed:
                self._valid_worker()
                # Reserve one extra byte beyond the maximum JSON payload
                # plus the optional CRLF framing. A stream returning text,
                # None or any other sentinel is never a successful EOF.
                raw=source.readline(self.limits.maximum_line_bytes+3)
                if raw==b"":
                    self._before_publication()
                    break
                if type(raw) is not bytes:
                    raise NativeOperatorSessionHold("binary command stream required")
                if (len(raw)>self.limits.maximum_line_bytes+2
                        or not raw.endswith(b"\n")):
                    raise NativeOperatorSessionHold("unterminated or oversized command")
                payload=raw[:-1]
                if payload.endswith(b"\r"):
                    payload=payload[:-1]
                if len(payload)>self.limits.maximum_line_bytes:
                    raise NativeOperatorSessionHold("operator command line too long")
                command=parse_operator_command(
                    payload,limit=self.limits.maximum_line_bytes,
                )
                result=self.dispatch(command)
                output=json.dumps(
                    result,sort_keys=True,ensure_ascii=False,allow_nan=False,
                    separators=(",",":"),
                )+"\n"
                output_size=len(output.encode("utf-8","strict"))
                if output_size>self.limits.maximum_result_bytes:
                    raise NativeOperatorSessionHold("operator disclosure exceeds result ceiling")
                if (self._published_result_bytes+output_size
                        > self.limits.maximum_session_result_bytes):
                    raise NativeOperatorSessionHold(
                        "cumulative operator disclosure budget exhausted"
                    )
                self._before_publication()
                # Reserve before attempting output. A partial/unknown write
                # must never refund bytes and silently resume the stream.
                self._published_result_bytes+=output_size
                written=destination.write(output)
                if type(written) is not int or written!=len(output):
                    raise NativeOperatorSessionHold(
                        "operator disclosure stream did not accept complete frame"
                    )
                if callable(getattr(destination,"flush",None)):
                    destination.flush()
            return 0
        except (Exception,KeyboardInterrupt) as exc:
            # A private user task or untrusted model answer may be embedded
            # in exception strings. Report only the exception class.
            self._closed=True
            destination.write(json.dumps({
                "schema":"jeeves.native_operator_command_error.v1",
                "status":"held","error_class":type(exc).__name__,
                "automatic_native_retry":False,
                "release_certified":False,
            },sort_keys=True)+"\n")
            return 2
        finally:
            with self._lock:
                self._stream_open=False
                self._stream_thread=None


__all__=[
    "NativeOperatorSessionHold","OperatorSessionLimits",
    "OperatorCommand","parse_operator_command","NativeOperatorSession",
]
