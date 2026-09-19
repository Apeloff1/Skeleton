"""Versioned declarative manifests for bounded shell pipelines.

Manifests name already-registered logical commands.  They never carry executable
paths or arbitrary shell text, so deserialization cannot expand process
authority beyond the runtime policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping

from skeleton.shells.pipeline import PipelineSpec, PipelineStep
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.runner import ShellCommand

MANIFEST_SCHEMA_VERSION = 1
_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class ManifestLimits:
    max_bytes: int = 512 * 1024
    max_steps: int = 256
    max_args_per_step: int = 128
    max_env_keys_per_step: int = 32
    max_string_chars: int = 16_384

    def __post_init__(self) -> None:
        if any(value <= 0 for value in self.__dict__.values()):
            raise ValueError("manifest limits must be positive")


def _bounded_string(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ManifestError(f"{label} must be a non-empty bounded string")
    if "\x00" in value:
        raise ManifestError(f"{label} may not contain NUL")
    return value


def _bounded_id(value: Any, label: str, limit: int) -> str:
    text = _bounded_string(value, label, limit)
    if not _ID.fullmatch(text):
        raise ManifestError(f"{label} has invalid characters")
    return text


def _parse_retry(raw: Any) -> RetryPolicy | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ManifestError("retry must be an object")
    allowed = {
        "max_attempts",
        "initial_delay_seconds",
        "multiplier",
        "max_delay_seconds",
        "retry_returncodes",
        "retry_timeouts",
        "retry_output_limits",
    }
    if set(raw) - allowed:
        raise ManifestError("retry contains unknown fields")
    codes = raw.get("retry_returncodes", [])
    if not isinstance(codes, list) or any(not isinstance(code, int) for code in codes):
        raise ManifestError("retry_returncodes must be an integer list")
    return RetryPolicy(
        max_attempts=int(raw.get("max_attempts", 1)),
        initial_delay_seconds=float(raw.get("initial_delay_seconds", 0.0)),
        multiplier=float(raw.get("multiplier", 2.0)),
        max_delay_seconds=float(raw.get("max_delay_seconds", 30.0)),
        retry_returncodes=frozenset(codes),
        retry_timeouts=bool(raw.get("retry_timeouts", False)),
        retry_output_limits=bool(raw.get("retry_output_limits", False)),
    )


def parse_manifest(payload: str | bytes, *, limits: ManifestLimits | None = None) -> PipelineSpec:
    bounds = limits or ManifestLimits()
    raw_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    if len(raw_bytes) > bounds.max_bytes:
        raise ManifestError("manifest exceeds byte limit")
    try:
        decoded = json.loads(raw_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestError("manifest is not valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ManifestError("manifest root must be an object")
    if decoded.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ManifestError("unsupported manifest schema_version")
    name = _bounded_id(decoded.get("name"), "manifest name", 128)
    steps_raw = decoded.get("steps")
    if not isinstance(steps_raw, list):
        raise ManifestError("steps must be an array")
    if len(steps_raw) > bounds.max_steps:
        raise ManifestError("step count exceeds bound")

    steps: list[PipelineStep] = []
    for index, raw in enumerate(steps_raw):
        if not isinstance(raw, dict):
            raise ManifestError(f"step {index} must be an object")
        allowed = {
            "id",
            "command",
            "args",
            "cwd",
            "env",
            "timeout",
            "allowed_returncodes",
            "depends_on",
            "retry",
            "continue_on_failure",
        }
        if set(raw) - allowed:
            raise ManifestError(f"step {index} contains unknown fields")
        step_id = _bounded_id(raw.get("id"), f"step {index} id", 128)
        command = _bounded_id(raw.get("command"), f"step {index} command", 128)
        args_raw = raw.get("args", [])
        if not isinstance(args_raw, list) or len(args_raw) > bounds.max_args_per_step:
            raise ManifestError(f"step {index} args must be a bounded array")
        args = tuple(_bounded_string(value, f"step {index} arg", bounds.max_string_chars) for value in args_raw)
        env_raw = raw.get("env", {})
        if not isinstance(env_raw, dict) or len(env_raw) > bounds.max_env_keys_per_step:
            raise ManifestError(f"step {index} env must be a bounded object")
        env: dict[str, str] = {}
        for key, value in env_raw.items():
            safe_key = _bounded_id(key, f"step {index} env key", 128)
            env[safe_key] = _bounded_string(value, f"step {index} env value", bounds.max_string_chars)
        cwd_raw = raw.get("cwd")
        cwd = None if cwd_raw is None else _bounded_string(cwd_raw, f"step {index} cwd", bounds.max_string_chars)
        returncodes_raw = raw.get("allowed_returncodes", [0])
        if not isinstance(returncodes_raw, list) or not returncodes_raw or any(not isinstance(code, int) for code in returncodes_raw):
            raise ManifestError(f"step {index} allowed_returncodes must be a non-empty integer array")
        deps_raw = raw.get("depends_on", [])
        if not isinstance(deps_raw, list):
            raise ManifestError(f"step {index} depends_on must be an array")
        dependencies = frozenset(_bounded_id(value, f"step {index} dependency", 128) for value in deps_raw)
        shell_command = ShellCommand(
            command,
            args,
            cwd=cwd,
            env=env,
            timeout=None if raw.get("timeout") is None else float(raw["timeout"]),
            allowed_returncodes=frozenset(returncodes_raw),
        )
        steps.append(
            PipelineStep(
                step_id,
                shell_command,
                depends_on=dependencies,
                retry=_parse_retry(raw.get("retry")),
                continue_on_failure=bool(raw.get("continue_on_failure", False)),
            )
        )
    return PipelineSpec(name, tuple(steps), max_steps=bounds.max_steps)


def manifest_dict(spec: PipelineSpec) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    for step in spec.steps:
        command = step.command
        item: dict[str, Any] = {
            "id": step.step_id,
            "command": command.command,
            "args": list(command.args),
            "env": dict(command.env),
            "allowed_returncodes": sorted(command.allowed_returncodes),
            "depends_on": sorted(step.depends_on),
            "continue_on_failure": step.continue_on_failure,
        }
        if command.cwd is not None:
            item["cwd"] = str(command.cwd)
        if command.timeout is not None:
            item["timeout"] = command.timeout
        if step.retry is not None:
            item["retry"] = {
                "max_attempts": step.retry.max_attempts,
                "initial_delay_seconds": step.retry.initial_delay_seconds,
                "multiplier": step.retry.multiplier,
                "max_delay_seconds": step.retry.max_delay_seconds,
                "retry_returncodes": sorted(step.retry.retry_returncodes),
                "retry_timeouts": step.retry.retry_timeouts,
                "retry_output_limits": step.retry.retry_output_limits,
            }
        steps.append(item)
    return {"schema_version": MANIFEST_SCHEMA_VERSION, "name": spec.name, "steps": steps}
