"""Bounded subprocess isolation for optional accelerator helpers."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
from typing import Any, Mapping, Sequence


_SAFE_ENVIRONMENT_KEYS = frozenset({"PATH", "JAVA_HOME", "LANG", "LC_ALL"})


class AcceleratorIsolationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IsolatedProcessResult:
    returncode: int
    payload: Any
    stderr: str
    request_digest: str
    response_digest: str
    isolation_mode: str = "subprocess-json" 
    authority_scope: str = "native-isolation-evidence-only"


def run_json_process(
    argv: Sequence[str],
    payload: Mapping[str, Any],
    *,
    timeout_s: float,
    cwd: str | Path | None = None,
    allowed_environment: Sequence[str] = ("PATH", "JAVA_HOME", "LANG", "LC_ALL"),
    max_input_bytes: int = 1_048_576,
    max_output_bytes: int = 4_194_304,
) -> IsolatedProcessResult:
    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise ValueError("argv must contain non-empty strings")
    if (
        isinstance(timeout_s, bool)
        or not isinstance(timeout_s, (int, float))
        or not math.isfinite(float(timeout_s))
        or timeout_s <= 0
    ):
        raise ValueError("timeout_s must be finite and positive")
    for field, value in (
        ("max_input_bytes", max_input_bytes),
        ("max_output_bytes", max_output_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{field} must be an integer")
        if value <= 0:
            raise ValueError(f"{field} must be positive")
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")

    try:
        encoded = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AcceleratorIsolationError(
            "accelerator request must be canonical-JSON serializable"
        ) from exc
    request_digest = hashlib.sha256(encoded).hexdigest()
    if len(encoded) > max_input_bytes:
        raise AcceleratorIsolationError("accelerator request exceeds input bound")

    requested_environment = tuple(allowed_environment)
    if (
        any(not isinstance(key, str) or not key for key in requested_environment)
        or len(requested_environment) != len(set(requested_environment))
    ):
        raise ValueError("allowed_environment must contain unique non-empty names")
    unsafe_environment = sorted(set(requested_environment) - _SAFE_ENVIRONMENT_KEYS)
    if unsafe_environment:
        raise AcceleratorIsolationError(
            "accelerator environment request exceeds safe allowlist: "
            + ", ".join(unsafe_environment)
        )
    env = {
        key: os.environ[key]
        for key in requested_environment
        if key in os.environ
    }
    def terminate_tree(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except (OSError, ProcessLookupError):
            try:
                process.kill()
            except OSError:
                pass

    stdout_buffer = bytearray()
    stderr_buffer = bytearray()
    overflow = threading.Event()
    overflow_stream: list[str] = []
    overflow_lock = threading.Lock()

    def drain(stream: Any, buffer: bytearray, label: str) -> None:
        try:
            while True:
                chunk = stream.read(65_536)
                if not chunk:
                    return
                if len(buffer) + len(chunk) > max_output_bytes:
                    remaining = max(0, max_output_bytes + 1 - len(buffer))
                    if remaining:
                        buffer.extend(chunk[:remaining])
                    with overflow_lock:
                        if not overflow_stream:
                            overflow_stream.append(label)
                    overflow.set()
                    terminate_tree(process)
                    return
                buffer.extend(chunk)
        finally:
            try:
                stream.close()
            except OSError:
                pass

    try:
        with tempfile.TemporaryFile() as input_file:
            input_file.write(encoded)
            input_file.seek(0)
            process = subprocess.Popen(
                list(argv),
                stdin=input_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=None if cwd is None else str(Path(cwd)),
                env=env,
                start_new_session=True,
            )
            if process.stdout is None or process.stderr is None:
                terminate_tree(process)
                raise AcceleratorIsolationError("accelerator pipes were not created")
            stdout_thread = threading.Thread(
                target=drain,
                args=(process.stdout, stdout_buffer, "stdout"),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=drain,
                args=(process.stderr, stderr_buffer, "stderr"),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()
            try:
                returncode = process.wait(timeout=float(timeout_s))
            except subprocess.TimeoutExpired as exc:
                terminate_tree(process)
                process.wait(timeout=5)
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                raise AcceleratorIsolationError("accelerator subprocess timed out") from exc
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)
            if stdout_thread.is_alive() or stderr_thread.is_alive():
                terminate_tree(process)
                raise AcceleratorIsolationError("accelerator output drain did not terminate")
    except OSError as exc:
        raise AcceleratorIsolationError(
            f"accelerator subprocess failed to start: {type(exc).__name__}"
        ) from exc

    if overflow.is_set():
        label = overflow_stream[0] if overflow_stream else "output"
        raise AcceleratorIsolationError(
            f"accelerator {label} exceeds output bound"
        )

    stderr = bytes(stderr_buffer).decode("utf-8", errors="replace")
    if returncode != 0:
        detail = " ".join(stderr.split())[:1200]
        raise AcceleratorIsolationError(
            f"accelerator subprocess exited {returncode}: {detail}"
        )
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise AcceleratorIsolationError(
                    f"accelerator returned duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    def reject_nonfinite_constant(value: str) -> None:
        raise AcceleratorIsolationError(
            f"accelerator returned non-finite JSON constant: {value}"
        )

    try:
        result = json.loads(
            bytes(stdout_buffer).decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonfinite_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceleratorIsolationError("accelerator returned invalid JSON") from exc
    response_bytes = json.dumps(
        result,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return IsolatedProcessResult(
        returncode=returncode,
        payload=result,
        stderr=stderr,
        request_digest=request_digest,
        response_digest=hashlib.sha256(response_bytes).hexdigest(),
    )


__all__ = ["AcceleratorIsolationError", "IsolatedProcessResult", "run_json_process"]
