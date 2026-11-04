"""Private local desktop bridge: one child, one installed GGUF, one SQLite.

This parent never opens model weights or reads the authoritative database.
All prompts and receipts travel over strictly bounded binary pipes. Native
errors terminate the bridge; nothing is silently retried.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from typing import Any

from .contracts import identifier, identity_hash
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

    def __post_init__(self) -> None:
        identifier(self.tenant, "tenant")
        identifier(self.subject, "subject")
        for name in ("model_root", "state_dir", "capacity_root"):
            value = getattr(self, name)
            if value is None and name == "capacity_root":
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
        if resume_session is not None:
            argv += ["--resume-session", resume_session]
        return argv


class DesktopBridge:
    """Synchronous framing; call from a UI-owned worker thread, never Tk."""

    def __init__(self, config: DesktopConfig, *, resume_session: str | None = None):
        if not isinstance(config, DesktopConfig):
            raise DesktopBridgeHold("typed local desktop configuration required")
        self.config = config
        self.resume_session = resume_session
        self._process: subprocess.Popen[bytes] | None = None
        self._flight = threading.Lock()
        self._dead = False
        self._started = False
        self.session_id: str | None = None
        self.model_sha256: str | None = None

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
            if (result.get("source_bound") is not True
                    or result.get("physical_device_qualified") is not False
                    or result.get("tenant") != self.config.tenant
                    or result.get("subject") != self.config.subject
                    or session_id is None):
                raise DesktopBridgeHold("unapproved or incomplete native startup witness")
        self.model_sha256 = claimed_model
        self.session_id = session_id
        return result

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
            return result
        except BaseException:
            self.abort()
            raise

    def request(self, op: str, **fields: object) -> dict[str, Any]:
        if not self.connected:
            raise DesktopBridgeHold("local native model is disconnected")
        payload = command(op, **fields)
        with self._flight:
            if not self.connected:
                raise DesktopBridgeHold("local source worker terminated")
            process = self._process
            assert process is not None
            assert process.stdin is not None
            assert process.stdout is not None
            try:
                write_frame(process.stdin, payload, limit=65536)
                received = read_frame(process.stdout, limit=MAX_OUTBOUND)
                if received is None:
                    raise DesktopBridgeHold("native worker exited before reply")
                result = self._verify(received)
                return result
            except BaseException:
                # Once a request has entered the pipe, the SQLite/native
                # effect may already have committed. No retries of this ID.
                self.abort()
                raise

    def turn(self, prompt: str, *, request_id: str | None = None) -> dict[str, Any]:
        rid = request_id if request_id is not None else "r_" + secrets.token_hex(16)
        return self.request("turn", prompt=prompt, request_id=rid)

    def abort(self) -> None:
        """Terminally revoke the child. Never launch replacement implicitly."""
        self._dead = True
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
