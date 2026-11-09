"""Private local desktop bridge: one child, one installed GGUF, one SQLite.

This parent never opens model weights or reads the authoritative database.
All prompts and receipts travel over strictly bounded binary pipes. Native
errors terminate the bridge; nothing is silently retried.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from typing import Any

from .contracts import identifier, identity_hash
from .desktop_environment import native_child_environment
from .desktop_protocol import (
    SCHEMA_RESPONSE, DesktopProtocolHold, MAX_OUTBOUND,
    command, read_frame, write_frame,
)


class DesktopBridgeHold(RuntimeError):
    """Native child is untrusted, unavailable or has an uncertain outcome."""


@dataclass(frozen=True, slots=True)
class DesktopConfig:
    model_root: str
    state_dir: str
    tenant: str
    subject: str
    capacity_root: str | None = None
    context: int = 4096
    max_output_tokens: int = 1024
    threads: int = 4
    gpu_layers: int = 0
    inference_ms: int = 90000
    capacity_budget_bytes: int = 8000000000
    startup_deadline_seconds: int = 180
    signed_source_root: str | None = None
    signed_source_manifest: str | None = None
    enable_signed_source_tool: bool = False
    max_signed_sources: int = 4
    max_signed_tool_calls: int = 3
    enable_pressure_guard: bool = False
    minimum_free_ram_bytes: int = 512 * 1024 * 1024
    minimum_free_disk_bytes: int = 256 * 1024 * 1024
    pressure_interval_ms: int = 500

    def __post_init__(self) -> None:
        identifier(self.tenant, "tenant")
        identifier(self.subject, "subject")
        if type(self.enable_pressure_guard) is not bool:
            raise DesktopBridgeHold("explicit boolean pressure supervision required")
        from .desktop_pressure import PressurePolicy
        PressurePolicy(
            minimum_available_ram_bytes=self.minimum_free_ram_bytes,
            minimum_state_disk_bytes=self.minimum_free_disk_bytes,
            sample_interval_ms=self.pressure_interval_ms,
            maximum_native_rss_bytes=min(
                20_000_000_000,
                self.capacity_budget_bytes * 95 // 100,
            ) if self.enable_pressure_guard else 0,
        )
        if type(self.enable_signed_source_tool) is not bool:
            raise DesktopBridgeHold("explicit boolean source tool approval required")
        if (
            (self.signed_source_root is None) != (self.signed_source_manifest is None)
            or (self.signed_source_root is not None) is not self.enable_signed_source_tool
        ):
            raise DesktopBridgeHold("signed source manifest/root need explicit operator approval")
        for name, low, high in (
            ("max_signed_sources", 1, 6),
            ("max_signed_tool_calls", 1, 3),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise DesktopBridgeHold("signed source grant exceeds finite ceiling")
        for name in (
            "model_root", "state_dir", "capacity_root",
            "signed_source_root", "signed_source_manifest",
        ):
            value = getattr(self, name)
            if value is None and name in (
                "capacity_root", "signed_source_root", "signed_source_manifest",
            ):
                continue
            if type(value) is not str or not value or chr(0) in value:
                raise DesktopBridgeHold("canonical local model/state path required")
            path = Path(value)
            if not path.is_absolute() or ".." in path.parts:
                raise DesktopBridgeHold("absolute private model/state paths required")
        bounds = {
            "context": (128, 131072),
            "max_output_tokens": (1, 8192),
            "threads": (1, 64),
            "gpu_layers": (0, 128),
            "inference_ms": (100, 600000),
            "capacity_budget_bytes": (1, 20000000000),
            "startup_deadline_seconds": (10, 600),
        }
        for name, (lo, hi) in bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise DesktopBridgeHold("invalid bounded local resource " + name)
        if self.max_output_tokens >= self.context:
            raise DesktopBridgeHold("native output tokens exceed active context")

    def worker_args(self, *, resume_session: str | None = None) -> list[str]:
        if resume_session is not None:
            identifier(resume_session, "resume session")
        argv = [
            sys.executable,
            "-m", "skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_host",
            "--approve-native",
            "--model-root", self.model_root,
            "--state-dir", self.state_dir,
            "--tenant", self.tenant,
            "--subject", self.subject,
            "--context", str(self.context),
            "--max-output-tokens", str(self.max_output_tokens),
            "--threads", str(self.threads),
            "--gpu-layers", str(self.gpu_layers),
            "--inference-ms", str(self.inference_ms),
            "--capacity-budget-bytes", str(self.capacity_budget_bytes),
        ]
        if self.capacity_root is not None:
            argv += ["--capacity-root", self.capacity_root]
        if self.enable_pressure_guard:
            # The child must establish fresh CPU/cgroup/installed-source fit
            # BEFORE loading GGUF; a stale advisory profile never suffices.
            argv += ["--enforce-preload-safety"]
        if self.enable_signed_source_tool:
            argv += [
                "--enable-source-tool",
                "--source-root", self.signed_source_root,
                "--signed-source-manifest", self.signed_source_manifest,
                "--max-sources", str(self.max_signed_sources),
                "--max-source-tool-calls", str(self.max_signed_tool_calls),
            ]
        if resume_session is not None:
            argv += ["--resume-session", resume_session]
        return argv


def _request_deadline_seconds(op: str, fields: dict[str, object], inference_ms: int) -> float:
    """Bound native watchdog timing before starting timers or publishing IPC.

    The native worker may commit a durable SQLite result before a timeout.
    Malformed wall clocks therefore cannot be normalized into a retry or
    silently poison a healthy process. No clamp is an extra work grant.
    """
    if op == "turn":
        if type(inference_ms) is not int or not 100 <= inference_ms <= 600000:
            raise DesktopBridgeHold("invalid finite native inference deadline")
        return min(660.0, inference_ms / 1000.0 + 45.0)
    if op == "agent" or (
        op == "durable" and fields.get("action") in ("start", "resume")
    ):
        value = fields.get("maximum_wall_seconds", 180)
        if (
            type(value) not in (int, float)
            or not 1 <= value <= 3600
            or (type(value) is float and not math.isfinite(value))
        ):
            raise DesktopBridgeHold("invalid native agent wall deadline")
        return min(660.0, float(value) + 45.0)
    return 30.0


class DesktopBridge:
    """Synchronous framing; call from a UI-owned worker thread, never Tk."""

    def __init__(self, config: DesktopConfig, *, resume_session: str | None = None):
        if not isinstance(config, DesktopConfig):
            raise DesktopBridgeHold("typed local desktop configuration required")
        self.config = config
        self.resume_session = resume_session
        self._process: subprocess.Popen[bytes] | None = None
        self._flight = threading.Lock()
        # One foreground-approved multi-task batch may own the *entire*
        # sequence, not just a single IPC frame. RLock permits that same
        # executor thread to submit its own individual durable requests.
        self._batch_gate = threading.RLock()
        self._dead = False
        self._started = False
        self.session_id: str | None = None
        self.model_sha256: str | None = None
        self.signed_source_manifest_sha256: str | None = None
        self._pressure_guard = None
        self._pressure_reason: str | None = None

    @property
    def pressure_status(self) -> dict[str, Any]:
        guard = getattr(self, "_pressure_guard", None)
        return {
            "schema": "jeeves.desktop.parent-pressure.v1",
            "enabled": bool(
                getattr(getattr(self, "config", None), "enable_pressure_guard", False),
            ),
            "pressure_hold": getattr(self, "_pressure_reason", None),
            "sample": guard.latest if guard is not None else None,
            "native_worker_connected": self.connected,
            "gpu_pressure_qualified": False,
            "release_certified": False,
        }

    def _revoke_on_pressure(self, reason: str) -> None:
        self._pressure_reason = reason
        self.abort()

    @property
    def connected(self) -> bool:
        process = self._process
        return (
            self._started and not self._dead and process is not None
            and process.poll() is None
        )

    def _verify(self, result: object) -> dict[str, Any]:
        if (type(result) is not dict
                or result.get("schema") != SCHEMA_RESPONSE
                or result.get("release_certified") is not False):
            raise DesktopBridgeHold("unexpected native desktop response")
        if result.get("status") == "held":
            raise DesktopBridgeHold("native operation held: outcome may be uncertain")
        claimed_model = identity_hash(result.get("model_sha256"))
        if self.model_sha256 is not None and claimed_model != self.model_sha256:
            raise DesktopBridgeHold("installed native model source changed")
        if "session_id" not in result:
            raise DesktopBridgeHold("native response lacks durable session identity")
        session_id = result["session_id"]
        if session_id is not None:
            identifier(session_id, "durable desktop session")
        if result.get("status") == "native-gguf-ready":
            checked_preload = result.get("preload_admission")
            requires_preload = getattr(
                getattr(self, "config", None), "enable_pressure_guard", False,
            )
            if requires_preload:
                from .desktop_preload_admission import (
                    PreloadAdmissionHold, verify_public_preload_receipt,
                )
                try:
                    verify_public_preload_receipt(
                        checked_preload,
                        expected_model_sha256=claimed_model,
                        requested_context_tokens=self.config.context,
                        requested_output_tokens=self.config.max_output_tokens,
                        requested_cpu_threads=self.config.threads,
                        requested_gpu_layers=self.config.gpu_layers,
                        requested_capacity_budget_bytes=(
                            self.config.capacity_budget_bytes
                        ),
                    )
                except PreloadAdmissionHold as exc:
                    raise DesktopBridgeHold(
                        "native child skipped exact live RAM/cgroup preload admission",
                    ) from exc
            elif checked_preload is not None:
                raise DesktopBridgeHold(
                    "unrequested native preload resource admission evidence",
                )
            approved_tool = getattr(getattr(self, "config", None), "enable_signed_source_tool", False)
            if (
                type(approved_tool) is not bool
                or result.get("signed_source_tool_active", False) is not approved_tool
            ):
                raise DesktopBridgeHold("native child source grants disagree with operator")
            signed_digest = result.get("signed_source_manifest_sha256")
            if approved_tool:
                if (
                    type(signed_digest) is not str
                    or len(signed_digest) != 64
                    or any(ch not in "0123456789abcdef" for ch in signed_digest)
                ):
                    raise DesktopBridgeHold("signed source manifest witness absent")
            elif signed_digest is not None:
                raise DesktopBridgeHold("unrequested signed manifest receipt")
            self.signed_source_manifest_sha256 = signed_digest
            if (result.get("source_bound") is not True
                    or result.get("physical_device_qualified") is not False
                    or result.get("tenant") != self.config.tenant
                    or result.get("subject") != self.config.subject
                    or session_id is None):
                raise DesktopBridgeHold("unapproved or incomplete native startup witness")
        self.model_sha256 = claimed_model
        self.session_id = session_id
        return result

    _SUCCESS = {
        "status": frozenset(("ready", "no-active-session")),
        "telemetry": frozenset(("observed-runtime-capacity",)),
        "source-status": frozenset(("signed-source-status",)),
        "agent": frozenset(("verified-agent-response",)),
        "durable": frozenset((
            "durable-work-inspected", "durable-work-committed",
            "durable-work-replayed",
        )),
        "new": frozenset(("new-durable-session",)),
        "resume": frozenset(("existing-durable-session-reopened",)),
        "turn": frozenset(("committed-native-chat-turn",)),
        "history": frozenset(("durable-history",)),
        "close": frozenset(("durable-session-closed",)),
        "quit": frozenset(("session-preserved-for-resume",)),
    }

    def _operation_receipt(
        self, op: str, fields: dict[str, object],
        result: dict[str, Any], old_session: str | None,
    ) -> None:
        """Reject spurious, reordered, or cross-session native IPC replies."""
        if result.get("status") not in self._SUCCESS[op]:
            raise DesktopBridgeHold("native response operation differs from issued request")
        session = result["session_id"]
        if op in ("new", "resume"):
            if session is None:
                raise DesktopBridgeHold("new native session missing durable identity")
            if op == "resume" and session != fields["session_id"]:
                raise DesktopBridgeHold("native resumed another SQLite session")
        elif op == "close":
            if session is not None or result.get("closed_session_id") != old_session:
                raise DesktopBridgeHold("native close receipt disagrees with requested session")
        elif session != old_session:
            raise DesktopBridgeHold("native request crossed SQLite session boundary")
        if op == "turn":
            record = result.get("turn")
            if type(record) is not dict:
                raise DesktopBridgeHold("canonical committed native answer absent")
            if (
                record.get("session_id") != old_session
                or record.get("request_id") != fields["request_id"]
                or result.get("request_id") != fields["request_id"]
                or record.get("authoritative_commit") is not True
                or record.get("release_certified") is not False
                or record.get("model_sha256") != self.model_sha256
            ):
                raise DesktopBridgeHold("native response receipt or owner not authoritative")
            text = record.get("answer")
            digest = record.get("output_sha256")
            if type(text) is not str or type(digest) is not str:
                raise DesktopBridgeHold("native receipt lacks exact answer digest")
            try:
                actual = sha256(text.encode("utf-8", "strict")).hexdigest()
            except UnicodeError as exc:
                raise DesktopBridgeHold("native answer has invalid Unicode") from exc
            if actual != digest:
                raise DesktopBridgeHold("native committed answer bytes changed in IPC")
        if op == "agent":
            report = result.get("agent")
            if (
                type(report) is not dict
                or report.get("schema") != "jeeves.desktop.strict-agent.v1"
                or report.get("status") != "verified"
                or report.get("success") is not True
                or report.get("run_id") != fields["run_id"]
                or result.get("run_id") != fields["run_id"]
                or report.get("model_sha256") != self.model_sha256
                or report.get("device_qualified") is not False
                or report.get("release_certified") is not False
                or report.get("filesystem_write_authorized") is not False
                or report.get("automatic_retry") is not False
                or type(report.get("usage")) is not dict
                or type(report["usage"].get("tool_calls")) is not int
                or report["usage"].get("tool_calls") < 0
                or report["usage"].get("tool_calls") > (
                    getattr(getattr(self, "config", None), "max_signed_tool_calls", 3)
                    if getattr(getattr(self, "config", None), "enable_signed_source_tool", False)
                    else 0
                )
                or report.get("signed_source_tool_active", False) is not getattr(
                    getattr(self, "config", None), "enable_signed_source_tool", False
                )
                or report.get("signed_source_manifest_sha256") != getattr(
                    self, "signed_source_manifest_sha256", None
                )
                or report.get("reasoning_profile", "guarded") != fields.get(
                    "profile", "guarded"
                )
            ):
                raise DesktopBridgeHold("native strict Jeeves agent result not authorized")
            policy = report.get("planning_policy")
            if policy is not None and (
                type(policy) is not dict
                or policy.get("schema") != "jeeves.desktop.native-planning-profile.v1"
                or policy.get("profile") != fields.get("profile", "guarded")
                or policy.get("persistent_memory_promotion_enabled") is not False
                or policy.get("tool_grants_changed_by_profile") is not False
                or policy.get("additional_provider_started") is not False
                or policy.get("release_certified") is not False
            ):
                raise DesktopBridgeHold("native planner profile or permission receipt changed")
            if fields.get("profile", "guarded") == "advanced" and policy is None:
                raise DesktopBridgeHold("advanced native planning policy proof absent")
            answer = report.get("answer")
            proof = report.get("output_sha256")
            if type(answer) is not str or type(proof) is not str:
                raise DesktopBridgeHold("agent answer or digest missing")
            try:
                observed = sha256(answer.encode("utf-8", "strict")).hexdigest()
            except UnicodeError as exc:
                raise DesktopBridgeHold("agent answer contains invalid Unicode") from exc
            if observed != proof:
                raise DesktopBridgeHold("agent answer differs from source-checked bytes")
        if op == "source-status":
            active = getattr(getattr(self, "config", None), "enable_signed_source_tool", False)
            receipt = result.get("signed_source")
            if result.get("signed_source_tool_active") is not active:
                raise DesktopBridgeHold("current signed source approval changed")
            if active:
                if (
                    type(receipt) is not dict
                    or receipt.get("schema") != "jeeves.desktop.signed-source-admission.v1"
                    or receipt.get("manifest_sha256") != getattr(
                        self, "signed_source_manifest_sha256", None
                    )
                    or receipt.get("source_tool_active") is not True
                    or receipt.get("independent_legal_rights_verified") is not False
                    or receipt.get("release_certified") is not False
                ):
                    raise DesktopBridgeHold("signed source admission metadata not authenticated")
            elif receipt is not None:
                raise DesktopBridgeHold("unapproved signed source receipt disclosed")
        if op == "durable":
            report = result.get("durable")
            action = fields["action"]
            expected = {
                "start": ("durable-work-committed", "terminal-committed", True),
                "resume": ("durable-work-committed", "terminal-committed", True),
                "inspect": ("durable-work-inspected", "inspected", False),
                "replay": ("durable-work-replayed", "terminal-replayed", False),
            }[action]
            if (
                type(report) is not dict
                or result.get("status") != expected[0]
                or report.get("status") != expected[1]
                or report.get("schema") != "jeeves.desktop.durable-work.v1"
                or report.get("action") != action
                or report.get("run_id") != fields["run_id"]
                or result.get("run_id") != fields["run_id"]
                or report.get("model_sha256") != self.model_sha256
                or report.get("native_generation_executed") is not expected[2]
                or report.get("device_qualified") is not False
                or report.get("release_certified") is not False
                or report.get("automatic_resume") is not False
            ):
                raise DesktopBridgeHold("durable SQLite work response not authorized")
            if action == "inspect":
                snapshot = report.get("snapshot")
                if (
                    type(snapshot) is not dict
                    or snapshot.get("schema") != "jeeves.native_durable_run.v1"
                    or snapshot.get("run_id") != fields["run_id"]
                    or snapshot.get("model_sha256") != self.model_sha256
                    or snapshot.get("device_qualified") is not False
                    or snapshot.get("release_certified") is not False
                ):
                    raise DesktopBridgeHold("durable checkpoint inspection not source bound")
            else:
                if (
                    report.get("success") is not True
                    or type(report.get("usage")) is not dict
                    or report["usage"].get("tool_calls") != 0
                    or (action == "replay")
                    is not (report.get("replayed_without_native_generation") is True)
                ):
                    raise DesktopBridgeHold("durable terminal result missing committed proof")
                answer = report.get("answer")
                proof = report.get("output_sha256")
                if type(answer) is not str or type(proof) is not str:
                    raise DesktopBridgeHold("durable terminal answer or digest missing")
                try:
                    observed = sha256(answer.encode("utf-8", "strict")).hexdigest()
                except UnicodeError as exc:
                    raise DesktopBridgeHold("durable terminal text invalid Unicode") from exc
                if observed != proof:
                    raise DesktopBridgeHold("durable committed answer differs from SQLite bytes")
        if op == "history":
            if (
                type(result.get("messages")) is not list
                or type(result.get("message_count")) is not int
                or result["message_count"] != len(result["messages"])
            ):
                raise DesktopBridgeHold("native history response missing bounded records")
        if op == "telemetry":
            observed = result.get("observed")
            if (
                type(observed) is not dict
                or observed.get("native_e2e_certified") is not False
            ):
                raise DesktopBridgeHold("untrusted native telemetry qualification")

    def open(self) -> dict[str, Any]:
        if self._started or self._process is not None:
            raise DesktopBridgeHold("desktop native child already started")
        self._started = True
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        try:
            self._process = subprocess.Popen(
                self.config.worker_args(resume_session=self.resume_session),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, close_fds=True,
                bufsize=0, creationflags=creationflags,
                env=native_child_environment(),
            )
            process = self._process
            assert process.stdout is not None
            # Model initialization can fail or hang. Time out the *entire*
            # startup, not just a read from a pipe. Timer kills the child.
            guard = threading.Timer(
                self.config.startup_deadline_seconds, self.abort,
            )
            guard.daemon = True
            guard.start()
            try:
                first = read_frame(process.stdout, limit=MAX_OUTBOUND)
            finally:
                guard.cancel()
            result = self._verify(first)
            if result["status"] != "native-gguf-ready":
                raise DesktopBridgeHold("native child never published source-checked ready")
            if process.poll() is not None:
                raise DesktopBridgeHold("native worker exited during startup")
            if getattr(self.config, "enable_pressure_guard", False):
                from .desktop_pressure import (
                    NativePressureSupervisor, PressurePolicy,
                )
                limits = PressurePolicy(
                    minimum_available_ram_bytes=self.config.minimum_free_ram_bytes,
                    minimum_state_disk_bytes=self.config.minimum_free_disk_bytes,
                    maximum_native_rss_bytes=min(
                        20_000_000_000,
                        self.config.capacity_budget_bytes * 95 // 100,
                    ),
                    sample_interval_ms=self.config.pressure_interval_ms,
                )
                guard = NativePressureSupervisor(
                    process, state_dir=Path(self.config.state_dir),
                    policy=limits, revoke=self._revoke_on_pressure,
                )
                self._pressure_guard = guard
                guard.start()
                if not self.connected:
                    raise DesktopBridgeHold("native startup exceeded resource pressure")
            return result
        except BaseException:
            self.abort()
            raise

    @contextmanager
    def exclusive_batch(self, manifest_sha256: str):
        """Hold this model/SQLite child for one approved finite work sequence.

        Ordinary chat, agent, history and durable work requests from other
        threads are REFUSED immediately. They cannot interleave between two
        source-approved durable work orders and cannot become hidden jobs.
        The lock is never used by pressure abort, avoiding a cancellation
        deadlock when the native child has been revoked mid-inference.
        """
        if (
            type(manifest_sha256) is not str
            or len(manifest_sha256) != 64
            or any(char not in "0123456789abcdef" for char in manifest_sha256)
        ):
            raise DesktopBridgeHold("exact reviewed batch manifest SHA-256 required")
        if not self._batch_gate.acquire(blocking=False):
            raise DesktopBridgeHold("native model owned by another in-flight request")
        try:
            if not self.connected:
                raise DesktopBridgeHold("single native source-bound worker unavailable")
            yield
        finally:
            self._batch_gate.release()

    def request(self, op: str, **fields: object) -> dict[str, Any]:
        if not self.connected:
            raise DesktopBridgeHold("local native model is disconnected")
        payload = command(op, **fields)
        if not self._batch_gate.acquire(blocking=False):
            raise DesktopBridgeHold(
                "native model is under exclusive work batch or in-flight request",
            )
        try:
            with self._flight:
                if not self.connected:
                    raise DesktopBridgeHold("local source worker terminated")
                process = self._process
                assert process is not None
                assert process.stdin is not None
                assert process.stdout is not None
                previous_session = self.session_id
                # Native inference has its own bounded deadline, but a hung
                # pipe/child teardown must not hold the GUI forever. The timer
                # revokes the child; a committed uncertain result is not retried.
                deadline = _request_deadline_seconds(
                    op, fields, self.config.inference_ms,
                )
                watchdog = threading.Timer(deadline, self.abort)
                watchdog.daemon = True
                watchdog.start()
                try:
                    if not self.connected:
                        raise DesktopBridgeHold("native request source revoked before publication")
                    write_frame(process.stdin, payload, limit=65536)
                    received = read_frame(process.stdout, limit=MAX_OUTBOUND)
                    if received is None:
                        raise DesktopBridgeHold("native worker exited before reply")
                    result = self._verify(received)
                    self._operation_receipt(op, fields, result, previous_session)
                    if not self.connected:
                        raise DesktopBridgeHold("native source died before request completed")
                    return result
                except BaseException:
                    # Once a request has entered the pipe, the SQLite/native
                    # effect may already have committed. No retries of this ID.
                    self.abort()
                    raise
                finally:
                    watchdog.cancel()

        finally:
            self._batch_gate.release()

    def turn(self, prompt: str, *, request_id: str | None = None) -> dict[str, Any]:
        rid = request_id if request_id is not None else "r_" + secrets.token_hex(16)
        return self.request("turn", prompt=prompt, request_id=rid)

    def abort(self) -> None:
        """Terminally revoke the child. Never launch replacement implicitly."""
        self._dead = True
        guard = getattr(self, "_pressure_guard", None)
        if guard is not None:
            guard.stop()
        process = self._process
        if process is not None:
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired, ProcessLookupError):
                pass
            for pipe in (process.stdin, process.stdout):
                if pipe is not None:
                    try:
                        pipe.close()
                    except OSError:
                        pass

    def close(self) -> None:
        """Explicit process exit preserves the durable session for later resume."""
        if self.connected:
            try:
                self.request("quit")
            except (DesktopBridgeHold, DesktopProtocolHold, OSError):
                pass
        self.abort()


__all__ = ["DesktopBridge", "DesktopBridgeHold", "DesktopConfig"]
