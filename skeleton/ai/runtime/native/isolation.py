"""Bounded subprocess isolation for optional accelerator helpers."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence


_SAFE_ENVIRONMENT_KEYS = frozenset({"PATH", "JAVA_HOME", "LANG", "LC_ALL"})


class AcceleratorIsolationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IsolatedProcessResult:
    returncode: int
    payload: Any
    stderr: str


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
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    if max_input_bytes <= 0 or max_output_bytes <= 0:
        raise ValueError("byte bounds must be positive")

    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
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
    try:
        completed = subprocess.run(
            list(argv),
            input=encoded,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=None if cwd is None else str(Path(cwd)),
            env=env,
            timeout=float(timeout_s),
            check=False,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise AcceleratorIsolationError("accelerator subprocess timed out") from exc
    except OSError as exc:
        raise AcceleratorIsolationError(
            f"accelerator subprocess failed to start: {type(exc).__name__}"
        ) from exc

    if len(completed.stdout) > max_output_bytes:
        raise AcceleratorIsolationError("accelerator response exceeds output bound")
    if len(completed.stderr) > max_output_bytes:
        raise AcceleratorIsolationError("accelerator stderr exceeds output bound")

    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        detail = " ".join(stderr.split())[:1200]
        raise AcceleratorIsolationError(
            f"accelerator subprocess exited {completed.returncode}: {detail}"
        )
    try:
        result = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceleratorIsolationError("accelerator returned invalid JSON") from exc
    return IsolatedProcessResult(
        returncode=completed.returncode,
        payload=result,
        stderr=stderr,
    )


__all__ = ["AcceleratorIsolationError", "IsolatedProcessResult", "run_json_process"]
