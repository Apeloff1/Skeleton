"""Governed tool execution: authorize -> guard -> contain -> scrub -> audit.

:class:`~skeleton.security.generated_code_sandbox.GeneratedCodeSandbox`
decides *whether* a process effect is granted but deliberately never spawns
anything; :func:`.process.run_isolated` contains a process but has no notion
of grants.  :class:`GuardedExecutor` is the single path that composes them for
tool calls driven by untrusted (model / user / web) input:

1. **Deny by default** - only tools registered as a :class:`ToolSpec` exist.
2. **Authorize** - the mediator must be *sealed* and must grant the
   ``process`` capability for the tool's executable (and ``network`` for each
   declared host); argv is checked by both layers.
3. **Guard** - every argument (and stdin, when the spec scans it) runs through
   :func:`.injection.detect` in the spec's context; ``block`` verdicts stop the
   call before launch.
4. **Contain** - path arguments are resolved inside the :class:`.fs.FsJail`;
   the process runs via :func:`.process.run_isolated` with the spec's limits
   and network denied unless hosts were granted (fail closed when isolation is
   unavailable, unless the policy explicitly opts out).
5. **Scrub** - output is stripped of control/bidi/ANSI characters, secrets
   are redacted, and the output itself is scanned for indirect prompt
   injection before :meth:`ToolOutcome.for_model` fences it.
6. **Audit** - each decision is appended to a hash-chained :class:`AuditLog`
   with redacted arguments and output digests (never raw output).

Every refusal is an :class:`ToolOutcome` with ``status`` ``denied`` or
``blocked``; :meth:`GuardedExecutor.execute` only raises for programming
errors (bad request types).
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from skeleton.security.generated_code_sandbox import (
    GeneratedCodeSandbox,
    Operation,
    OperationKind,
    SandboxCapability,
)

from .errors import FsPolicyError, PathEscapeError, ProcessPolicyError, SandboxError, SanitizerError
from .fs import FsJail
from .injection import CONTEXT_FAMILIES, detect, quarantine
from .process import ProcessLimits, ProcessResult, check_argv, network_isolation_available, run_isolated
from .sanitizers import redact_secrets, sanitize_text, shell_quote

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
STATUS_DENIED = "denied"
STATUS_BLOCKED = "blocked"
STATUSES = (STATUS_OK, STATUS_FAILED, STATUS_TIMEOUT, STATUS_DENIED, STATUS_BLOCKED)
MAX_TOOL_NAME = 64
MAX_AUDIT_ENTRIES = 10_000
GENESIS_HASH = "0" * 64


class ExecutorConfigError(SandboxError):
    """The executor or a tool spec is misconfigured (raised at construction)."""

    code = "SANDBOX.EXEC.CONFIG"


class AuditIntegrityError(SandboxError):
    """The audit hash chain does not verify."""

    code = "SANDBOX.EXEC.AUDIT"


@dataclass(frozen=True)
class ToolSpec:
    """A registered tool. ``executable`` must be in the mediator's allowlist."""

    name: str
    executable: str
    max_args: int = 32
    arg_context: str = "shell"
    stdin_context: str | None = "any"  # None: stdin is opaque data, not scanned
    allow_stdin: bool = True
    path_args: frozenset[int] = frozenset()  # indexes into the request args
    network_hosts: tuple[str, ...] = ()
    limits: ProcessLimits = field(default_factory=ProcessLimits)
    block_threshold: float = 0.7
    output_chars: int = 200_000

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > MAX_TOOL_NAME or not self.name.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ExecutorConfigError("tool name must be a short identifier", context={"name": self.name[:80]})
        if not self.executable or any(ch in self.executable for ch in "\x00\n\r"):
            raise ExecutorConfigError("tool executable is invalid", context={"tool": self.name})
        if self.arg_context not in CONTEXT_FAMILIES or (self.stdin_context is not None and self.stdin_context not in CONTEXT_FAMILIES):
            raise ExecutorConfigError("unknown injection context", context={"tool": self.name})
        if (
            type(self.max_args) is not int
            or not 1 <= self.max_args <= 256
            or not isinstance(self.path_args, frozenset)
            or any(type(i) is not int or i < 0 or i >= self.max_args for i in self.path_args)
        ):
            raise ExecutorConfigError("argument bounds are invalid", context={"tool": self.name})
        if type(self.block_threshold) not in (int, float) or not 0.0 < self.block_threshold <= 1.0:
            raise ExecutorConfigError("block threshold must be in (0, 1]", context={"tool": self.name})
        if type(self.output_chars) is not int or not 1 <= self.output_chars <= 200_000:
            raise ExecutorConfigError("output cap must be a bounded positive integer", context={"tool": self.name})
        if not isinstance(self.limits, ProcessLimits):
            raise ExecutorConfigError("process limits must be ProcessLimits", context={"tool": self.name})


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    args: tuple[str, ...] = ()
    stdin: bytes | None = None
    env: Mapping[str, str] | None = None
    cwd: str | None = None
    source: str = "untrusted"


@dataclass(frozen=True)
class ExecutorPolicy:
    require_sealed_mediator: bool = True
    require_network_isolation: bool = True
    max_executions: int | None = None
    scan_output: bool = True
    output_block_threshold: float = 0.7

    def __post_init__(self) -> None:
        if self.max_executions is not None and (
            type(self.max_executions) is not int or self.max_executions < 0
        ):
            raise ExecutorConfigError("execution budget must be a nonnegative integer")
        if (
            type(self.output_block_threshold) not in (int, float)
            or not 0.0 < self.output_block_threshold <= 1.0
        ):
            raise ExecutorConfigError("output block threshold must be in (0, 1]")


@dataclass
class ToolOutcome:
    tool: str
    status: str
    reason: str
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    redactions: list[str] = field(default_factory=list)
    input_findings: list[dict[str, Any]] = field(default_factory=list)
    output_report: dict[str, Any] | None = None
    output_flagged: bool = False
    truncated: bool = False
    duration_s: float = 0.0
    network_enforced: bool = False
    audit_hash: str = ""

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    def for_model(self) -> str:
        """Tool output fenced as untrusted data for an LLM prompt."""
        body = self.stdout if self.ok or self.status == STATUS_FAILED else f"[{self.status}] {self.reason}"
        return quarantine(body, source=f"tool:{self.tool}")

    def to_record(self) -> dict[str, Any]:
        return {
            "tool": self.tool, "status": self.status, "reason": self.reason, "returncode": self.returncode,
            "redactions": list(self.redactions), "input_findings": list(self.input_findings),
            "output_flagged": self.output_flagged, "truncated": self.truncated,
            "duration_s": round(self.duration_s, 4), "network_enforced": self.network_enforced,
            "audit_hash": self.audit_hash,
        }


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("ascii")


class AuditLog:
    """Append-only, hash-chained record of executor decisions (bounded)."""

    def __init__(self, *, sink: Callable[[dict[str, Any]], None] | None = None, max_entries: int = MAX_AUDIT_ENTRIES) -> None:
        # An invalid retention budget must fail during configuration, not on
        # the first audited denial or execution. Keep retention strictly
        # bounded to prevent accidental unbounded in-memory custody.
        if type(max_entries) is not int or not 1 <= max_entries <= MAX_AUDIT_ENTRIES:
            raise ExecutorConfigError("audit max_entries must be a bounded positive integer")
        if sink is not None and not callable(sink):
            raise ExecutorConfigError("audit sink must be callable")
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._sink = sink
        self._max = max_entries
        self._dropped = 0
        self._head = GENESIS_HASH
        self._anchor = GENESIS_HASH  # prev-hash of the oldest retained entry

    def append(self, event: Mapping[str, Any]) -> str:
        with self._lock:
            entry = {"seq": len(self._entries) + self._dropped, "prev": self._head, "event": dict(event)}
            digest = hashlib.sha256(_canonical(entry)).hexdigest()
            entry["hash"] = digest
            self._entries.append(entry)
            self._head = digest
            if len(self._entries) > self._max:
                self._entries.pop(0)
                self._dropped += 1
                self._anchor = self._entries[0]["prev"]
        if self._sink is not None:
            # Never give callbacks aliases into a retained hash-chain entry:
            # nested dict/list mutation through a sink would corrupt custody.
            self._sink(json.loads(_canonical(entry)))
        return digest

    @property
    def head(self) -> str:
        return self._head

    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            return [json.loads(_canonical(e)) for e in self._entries]

    def verify(self, entries: Sequence[Mapping[str, Any]] | None = None, *, anchor: str | None = None) -> bool:
        """Recompute the chain; raise :class:`AuditIntegrityError` on mismatch."""
        if entries is None:
            with self._lock:
                items = [json.loads(_canonical(e)) for e in self._entries]
                prev = self._anchor
        else:
            items = [dict(e) for e in entries]
            prev = anchor if anchor is not None else (items[0]["prev"] if items else GENESIS_HASH)
        for item in items:
            claimed = item.get("hash")
            body = {k: item[k] for k in ("seq", "prev", "event") if k in item}
            if item.get("prev") != prev or hashlib.sha256(_canonical(body)).hexdigest() != claimed:
                raise AuditIntegrityError("audit chain broken", context={"seq": item.get("seq")})
            prev = claimed
        return True

    def export_jsonl(self) -> str:
        return "".join(json.dumps(e, sort_keys=True, ensure_ascii=True) + "\n" for e in self.entries())


class GuardedExecutor:
    """Single governed entry point for tool execution (see module docstring)."""

    def __init__(
        self,
        mediator: GeneratedCodeSandbox,
        jail: FsJail,
        tools: Sequence[ToolSpec],
        *,
        policy: ExecutorPolicy | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        if not isinstance(mediator, GeneratedCodeSandbox):
            raise ExecutorConfigError("mediator must be a GeneratedCodeSandbox")
        if not isinstance(jail, FsJail):
            raise ExecutorConfigError("jail must be an FsJail")
        self._mediator = mediator
        self._jail = jail
        self._policy = policy or ExecutorPolicy()
        self._audit = audit or AuditLog()
        self._lock = threading.Lock()
        self._executions = 0
        registry: dict[str, ToolSpec] = {}
        for spec in tools:
            if not isinstance(spec, ToolSpec):
                raise ExecutorConfigError("tools must be ToolSpec instances")
            if spec.name in registry:
                raise ExecutorConfigError("duplicate tool name", context={"tool": spec.name})
            registry[spec.name] = spec
        self._tools: Mapping[str, ToolSpec] = dict(registry)

    @property
    def audit(self) -> AuditLog:
        return self._audit

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    # -- pipeline -----------------------------------------------------------
    def execute(self, request: ToolRequest) -> ToolOutcome:
        if not isinstance(request, ToolRequest):
            raise TypeError("execute() needs a ToolRequest")
        # A ToolRequest can originate from decoded untrusted data. Do not
        # hash or stringify arbitrary objects before making a deny decision.
        if not isinstance(request.tool, str):
            return self._finish(request, ToolOutcome("<invalid>", STATUS_DENIED, "tool name must be a string"))
        tool_name = request.tool[:MAX_TOOL_NAME]
        spec = self._tools.get(request.tool)
        if spec is None:
            return self._finish(request, ToolOutcome(tool_name, STATUS_DENIED, "unknown tool (deny by default)"))
        try:
            args = self._check_args(spec, request)
        except SandboxError as exc:
            return self._finish(request, ToolOutcome(spec.name, STATUS_DENIED, exc.message))

        denied = self._authorize(spec, args)
        if denied is not None:
            return self._finish(request, ToolOutcome(spec.name, STATUS_DENIED, denied))

        findings, blocked = self._guard(spec, args, request.stdin)
        if blocked:
            return self._finish(request, ToolOutcome(spec.name, STATUS_BLOCKED, "input blocked by injection detector", input_findings=findings))

        try:
            launch_args = self._contain_paths(spec, args)
            limits, enforced = self._limits(spec)
        except SandboxError as exc:
            return self._finish(request, ToolOutcome(spec.name, STATUS_DENIED, exc.message, input_findings=findings))

        with self._lock:
            if self._policy.max_executions is not None and self._executions >= self._policy.max_executions:
                return self._finish(request, ToolOutcome(spec.name, STATUS_DENIED, "execution budget exhausted", input_findings=findings))
            self._executions += 1

        try:
            result = run_isolated([spec.executable, *launch_args], jail=self._jail, cwd=request.cwd, stdin=request.stdin, env=request.env, limits=limits)
        except SandboxError as exc:
            return self._finish(request, ToolOutcome(spec.name, STATUS_DENIED, exc.message, input_findings=findings, network_enforced=enforced))
        outcome = self._scrub(spec, result)
        outcome.input_findings = findings
        outcome.network_enforced = enforced
        return self._finish(request, outcome)

    def _check_args(self, spec: ToolSpec, request: ToolRequest) -> tuple[str, ...]:
        # Refuse malformed and string-shaped argv, including non-iterables.
        # tuple("abc") would otherwise turn one untrusted argument into three.
        if not isinstance(request.args, (tuple, list)):
            raise ProcessPolicyError("tool arguments must be a list or tuple of strings")
        if len(request.args) > spec.max_args:
            raise ProcessPolicyError("too many arguments for tool", context={"tool": spec.name, "maximum": spec.max_args})
        if any(not isinstance(value, str) for value in request.args):
            raise ProcessPolicyError("tool arguments must be a list or tuple of strings")
        args = tuple(request.args)
        if args:
            check_argv(args)
        if request.cwd is not None and not isinstance(request.cwd, str):
            raise ProcessPolicyError("cwd must be a string path inside the jail")
        if request.env is not None and not isinstance(request.env, Mapping):
            raise ProcessPolicyError("environment must be a mapping of strings")
        if request.stdin is not None:
            if not spec.allow_stdin:
                raise ProcessPolicyError("tool does not accept stdin", context={"tool": spec.name})
            if not isinstance(request.stdin, (bytes, bytearray)):
                raise ProcessPolicyError("stdin must be bytes")
        return args

    def _authorize(self, spec: ToolSpec, args: tuple[str, ...]) -> str | None:
        if self._policy.require_sealed_mediator and not self._mediator.sealed:
            return "mediator policy must be sealed before executing untrusted requests"
        decision = self._mediator.authorize(Operation(OperationKind.PROCESS, spec.executable, SandboxCapability.PROCESS, " ".join(args)))
        if not decision.allowed:
            return decision.reason
        for host in spec.network_hosts:
            net = self._mediator.authorize(Operation(OperationKind.NETWORK, host, SandboxCapability.NETWORK))
            if not net.allowed:
                return f"{net.reason}: {host}"
        return None

    def _guard(self, spec: ToolSpec, args: tuple[str, ...], stdin: bytes | None) -> tuple[list[dict[str, Any]], bool]:
        findings: list[dict[str, Any]] = []
        blocked = False
        items: list[tuple[str, str, str]] = [(f"arg[{i}]", a, spec.arg_context) for i, a in enumerate(args)]
        if stdin is not None and spec.stdin_context is not None:
            items.append(("stdin", bytes(stdin).decode("utf-8", errors="replace"), spec.stdin_context))
        for where, text, context in items:
            try:
                report = detect(text, context=context)
            except SanitizerError:
                findings.append({"where": where, "error": "unscannable"})
                blocked = True
                continue
            if report.findings:
                findings.append({"where": where, "score": round(report.score, 4), "families": report.families,
                                 "rules": [f.rule_id for f in report.findings][:8]})
            if report.score >= spec.block_threshold:
                blocked = True
        return findings, blocked

    def _contain_paths(self, spec: ToolSpec, args: tuple[str, ...]) -> tuple[str, ...]:
        out = list(args)
        for i in sorted(spec.path_args):
            if i < len(out):
                try:
                    out[i] = str(self._jail.resolve(out[i]))
                except (PathEscapeError, FsPolicyError):
                    raise
        return tuple(out)

    def _limits(self, spec: ToolSpec) -> tuple[ProcessLimits, bool]:
        if spec.network_hosts:
            # The process boundary only offers full network access or total
            # isolation. A mediator's grant for host A must never silently
            # become unrestricted egress to hosts B..Z.
            raise ProcessPolicyError(
                "host-scoped networking unavailable (fail closed)"
            )
        if network_isolation_available():
            return replace(spec.limits, network="deny"), True
        if self._policy.require_network_isolation:
            raise ProcessPolicyError("network isolation unavailable and required by policy (fail closed)")
        return replace(spec.limits, network="inherit"), False

    def _scrub(self, spec: ToolSpec, result: ProcessResult) -> ToolOutcome:
        try:
            out = sanitize_text(
                result.stdout.decode("utf-8", errors="replace")[: spec.output_chars],
                normalize=None,
            )
            err = sanitize_text(
                result.stderr.decode("utf-8", errors="replace")[: spec.output_chars],
                normalize=None,
            )
            out, kinds_out = redact_secrets(out)
            err, kinds_err = redact_secrets(err)
        except SanitizerError:
            # No unsanitized stdout/stderr can reach model context. Retain
            # bounded custody even if the sanitizer itself rejects output.
            return ToolOutcome(
                spec.name, STATUS_BLOCKED, "tool output could not be sanitized",
                returncode=result.returncode,
                output_report={"error": "unsanitizable"},
                output_flagged=True, truncated=result.truncated,
                duration_s=result.duration_s,
            )
        if result.timed_out:
            status, reason = STATUS_TIMEOUT, "wall-clock limit reached"
        elif result.returncode == 0:
            status, reason = STATUS_OK, "completed"
        else:
            status, reason = STATUS_FAILED, f"exit status {result.returncode}"
        outcome = ToolOutcome(spec.name, status, reason, stdout=out, stderr=err, returncode=result.returncode,
                              redactions=sorted(set(kinds_out) | set(kinds_err)), truncated=result.truncated,
                              duration_s=result.duration_s)
        if self._policy.scan_output and out:
            try:
                report = detect(out, context="prompt")
            except SanitizerError:
                # Unscannable tool output must never enter a model prompt.
                outcome.status = STATUS_BLOCKED
                outcome.reason = "tool output could not be safely scanned"
                outcome.output_report = {"error": "unscannable"}
                outcome.output_flagged = True
            else:
                outcome.output_report = report.to_record()
                outcome.output_flagged = report.score >= self._policy.output_block_threshold
                if outcome.output_flagged:
                    # Quarantine alone is not execution authority. A score
                    # above the explicit policy threshold must not be emitted
                    # into a model prompt as a successful tool result.
                    outcome.status = STATUS_BLOCKED
                    outcome.reason = "tool output blocked by injection detector"
        return outcome

    def _finish(self, request: ToolRequest, outcome: ToolOutcome) -> ToolOutcome:
        # Bad argument envelopes must still produce a custody receipt. Never
        # iterate an unchecked None/string/dict or unbounded custom iterable.
        raw_args = request.args if isinstance(request.args, (tuple, list)) else ()
        safe_args = [redact_secrets(sanitize_text(a[:512], keep_newlines=False))[0] if isinstance(a, str) else "<invalid>" for a in raw_args[:64]]
        safe_source = redact_secrets(
            sanitize_text(request.source[:4096] if isinstance(request.source, str) else "<invalid>", keep_newlines=False)
        )[0][:64]
        safe_reason = redact_secrets(
            sanitize_text(str(outcome.reason)[:4096], keep_newlines=False)
        )[0][:200]
        event = {
            "ts": round(time.time(), 3),
            "tool": outcome.tool,
            "source": safe_source,
            "status": outcome.status,
            "reason": safe_reason,
            "argv_display": shell_quote(safe_args)[:2048],
            "stdin_sha256": (hashlib.sha256(bytes(request.stdin)).hexdigest()
                             if isinstance(request.stdin, (bytes, bytearray)) else None),
            "stdout_sha256": hashlib.sha256(outcome.stdout.encode("utf-8")).hexdigest() if outcome.stdout else None,
            "returncode": outcome.returncode,
            "redactions": list(outcome.redactions),
            "input_findings": list(outcome.input_findings),
            "output_flagged": outcome.output_flagged,
            "network_enforced": outcome.network_enforced,
        }
        outcome.audit_hash = self._audit.append(event)
        return outcome


__all__ = [
    "STATUSES",
    "AuditIntegrityError",
    "AuditLog",
    "ExecutorConfigError",
    "ExecutorPolicy",
    "GuardedExecutor",
    "ToolOutcome",
    "ToolRequest",
    "ToolSpec",
]
