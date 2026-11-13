"""Pure operator admission contract before any expensive native model startup.

The CLI owns only input shape and resource admission; the source-approved
installer, descriptor-anchored custody, actual backend identity and durable
SQLite authority remain independent later gates. A malformed option cannot
cause an unnecessary model load, path read, tool grant or secret exposure.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import (
    ContractViolation, identifier,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.preflight import (
    validate_native_shape,
)


class NativeOperatorHold(ValueError):
    """Operator request must not initiate local model activation."""


@dataclass(frozen=True, slots=True)
class OperatorAdmission:
    mode: str
    task_stdin: bool
    session: str | None
    request_id: str | None
    source_root: Path | None
    signed_source_manifest: Path | None
    enable_source_tool: bool
    max_sources: int
    max_steps: int
    max_model_calls: int
    max_wall_seconds: float
    run_id: str | None = None
    resume_run: bool = False
    inspect_run: bool = False
    replay_result: bool = False
    context_tokens: int = 4096
    output_tokens: int = 1024
    native_threads: int = 4
    gpu_layers: int = 0
    capacity_budget_bytes: int = 8000000000
    inference_ms: int = 90000

    @property
    def source_material_enabled(self) -> bool:
        return self.source_root is not None

    @property
    def tool_call_ceiling(self) -> int:
        return 3 if self.enable_source_tool else 1

    def public_receipt(self) -> dict[str, object]:
        # No private path or session identity in diagnostic summaries.
        return {
            "schema": "jeeves.native_operator_admission.v1",
            "mode": self.mode,
            "durable_checkpoint_lane": self.mode == "durable-agent",
            "operator_resume_requested": self.resume_run,
            "read_only_inspection": self.inspect_run,
            "terminal_replay_requested": self.replay_result,
            "may_activate_native": False,
            "operator_resource_shape_admissible": True,
            "signed_source_required": self.source_material_enabled,
            "explicit_readonly_source_tool": self.enable_source_tool,
            "maximum_sources": self.max_sources,
            "max_steps": self.max_steps,
            "max_model_calls": self.max_model_calls,
            "tool_call_ceiling": self.tool_call_ceiling,
            "model_rights_verified": False,
            "device_qualified": False,
            "release_certified": False,
        }


def check_native_resource_shape(
    *,
    context_tokens: int,
    output_tokens: int,
    native_threads: int,
    gpu_layers: int,
    capacity_budget_bytes: int,
    inference_ms: int = 90000,
) -> None:
    """Validate finite requested shape before loading any local model.

    One shared check applies to both the single-task and the long-running
    durable operator CLI. These are structural limits, not observed host
    telemetry, model-source rights, installed receipt or native execution proof.
    """
    try:
        validate_native_shape(
            n_ctx=context_tokens, max_new_tokens=output_tokens,
            n_threads=native_threads, gpu_layers=gpu_layers,
            capacity_budget_bytes=capacity_budget_bytes,
            inference_ms=inference_ms,
        )
    except ContractViolation as exc:
        raise NativeOperatorHold("invalid finite native resource request") from exc


def check_operator_admission(
    *,
    mode: str,
    task_stdin: bool,
    session: str | None,
    request_id: str | None,
    source_root: Path | None,
    signed_source_manifest: Path | None,
    enable_source_tool: bool,
    max_sources: int,
    max_steps: int,
    max_model_calls: int,
    max_wall_seconds: int | float,
    run_id: str | None = None,
    resume_run: bool = False,
    inspect_run: bool = False,
    replay_result: bool = False,
    context_tokens: int = 4096,
    output_tokens: int = 1024,
    native_threads: int = 4,
    gpu_layers: int = 0,
    capacity_budget_bytes: int = 8000000000,
    inference_ms: int = 90000,
) -> OperatorAdmission:
    """Reject structurally unsound operator input before model startup."""
    if type(mode) is not str or mode not in ("agent", "chat", "repl", "durable-agent"):
        raise NativeOperatorHold("unsupported Jeeves operator mode")
    if (type(task_stdin) is not bool or type(enable_source_tool) is not bool
            or type(resume_run) is not bool or type(inspect_run) is not bool
            or type(replay_result) is not bool):
        raise NativeOperatorHold("explicit boolean operator flags required")
    if mode == "repl":
        if task_stdin or request_id is not None:
            raise NativeOperatorHold("interactive REPL cannot accept one-shot options")
    elif not task_stdin:
        raise NativeOperatorHold("one-shot Jeeves requires bounded task stdin")
    if mode in ("agent", "durable-agent") and (session is not None or request_id is not None):
        raise NativeOperatorHold("agent mode cannot borrow chat session or request identities")
    if mode == "durable-agent":
        if run_id is None:
            raise NativeOperatorHold("explicit run ID required for durable Jeeves")
        identifier(run_id, "run ID")
        if sum((resume_run, inspect_run, replay_result)) > 1:
            raise NativeOperatorHold("durable inspection, resume and replay are distinct operations")
        if enable_source_tool or source_root is not None or signed_source_manifest is not None:
            raise NativeOperatorHold("durable lane is reasoning-only until tool recovery qualification")
    elif run_id is not None or resume_run or inspect_run or replay_result:
        raise NativeOperatorHold("durable run options require durable-agent mode")
    if session is not None:
        identifier(session, "session")
    if request_id is not None:
        identifier(request_id, "request ID")
    if (source_root is None) != (signed_source_manifest is None):
        raise NativeOperatorHold("operator source root and signed manifest must be paired")
    for label, value in (
        ("signed source root", source_root),
        ("source manifest", signed_source_manifest),
    ):
        if value is not None:
            if not isinstance(value, Path) or not value.is_absolute():
                raise NativeOperatorHold("absolute private " + label + " required")
            if ".." in value.parts or "\x00" in str(value):
                raise NativeOperatorHold("noncanonical private path component")
    if type(max_sources) is not int or not 1 <= max_sources <= 6:
        raise NativeOperatorHold("signed source count exceeds established ceiling")
    if type(max_steps) is not int or not 1 <= max_steps <= 10000:
        raise NativeOperatorHold("invalid Jeeves step budget")
    if type(max_model_calls) is not int or not 1 <= max_model_calls <= 10000:
        raise NativeOperatorHold("invalid Jeeves model call budget")
    if (type(max_wall_seconds) not in (int, float)
        or not math.isfinite(max_wall_seconds)
        or not 0 < max_wall_seconds <= 86400):
        raise NativeOperatorHold("invalid bounded wall clock budget")
    check_native_resource_shape(
        context_tokens=context_tokens,
        output_tokens=output_tokens,
        native_threads=native_threads,
        gpu_layers=gpu_layers,
        capacity_budget_bytes=capacity_budget_bytes,
        inference_ms=inference_ms,
    )

    if enable_source_tool and (mode != "agent" or source_root is None):
        raise NativeOperatorHold("source tool requires agent mode and signed source custody")
    if mode == "agent" and source_root is not None and not enable_source_tool:
        raise NativeOperatorHold("agent sources require explicitly granted lookup capability")
    return OperatorAdmission(
        mode=mode,
        task_stdin=task_stdin,
        session=session,
        request_id=request_id,
        source_root=source_root,
        signed_source_manifest=signed_source_manifest,
        enable_source_tool=enable_source_tool,
        max_sources=max_sources,
        max_steps=max_steps,
        max_model_calls=max_model_calls,
        max_wall_seconds=float(max_wall_seconds),
        run_id=run_id,
        resume_run=resume_run,
        inspect_run=inspect_run,
        replay_result=replay_result,
        context_tokens=context_tokens,
        output_tokens=output_tokens,
        native_threads=native_threads,
        gpu_layers=gpu_layers,
        capacity_budget_bytes=capacity_budget_bytes,
        inference_ms=inference_ms,
    )


__all__ = ["NativeOperatorHold", "OperatorAdmission", "check_operator_admission", "check_native_resource_shape"]
