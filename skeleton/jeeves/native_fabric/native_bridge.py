"""Read-only bridge from the canonical production supervisor into host facts.

Never wrap a synthetic backend as physical hardware proof. A real installed
model is verified by the source-bound installer, and a real executed turn
by the execution-spine receipt. This bridge only reads existing typed
identity, resource ceilings and health signals; it makes no model call.
"""
from __future__ import annotations

from typing import Any, Mapping

from skeleton.ai.runtime.operational_ai.laptop_runtime.identity import ActiveModel
from .contracts import ContractHold, Scope, ResourceLimits, fingerprint
from .model_inventory import ModelIdentity, ModelQualification
from .device import DeviceSnapshot, DevicePolicy, evaluate_device


def scope_from_worker(worker: Any, *,
                      workspace: str = "default",
                      session: str | None = None) -> Scope:
    if worker is None or not hasattr(worker, "spine"):
        raise ContractHold("canonical native supervisor required")
    actual = ActiveModel.from_supervisor(worker)
    return Scope(
        tenant=actual.tenant,
        subject=actual.subject,
        model_sha256=actual.model_sha256,
        tokenizer_sha256=actual.tokenizer_sha256,
        workspace=workspace, session=session,
    )


def limits_from_worker(worker: Any) -> ResourceLimits:
    if worker is None or not hasattr(worker, "spine"):
        raise ContractHold("canonical native supervisor required")
    real = worker.spine.limits
    return ResourceLimits(
        input_bytes=real.input_bytes,
        output_bytes=real.response_bytes,
        context_tokens=real.context_tokens,
        output_tokens=real.max_output_tokens,
        model_calls=8,
        tool_calls=0,
        work_items=128,
        deadline_ms=real.deadline_ms,
    )


def snapshot_native_status(worker: Any) -> dict[str, object]:
    scope = scope_from_worker(worker)
    limits = limits_from_worker(worker)
    if not hasattr(worker.spine, "health") or not hasattr(worker, "status"):
        raise ContractHold("live native status authority missing")
    native_status = worker.status()
    spine_health = worker.spine.health()
    if type(native_status) is not dict or type(spine_health) is not dict:
        raise ContractHold("native supervisor returned malformed status")
    # Only publish a content-addressed digest of possibly sensitive health
    # metadata; no transcript, session, capacity file or private source path.
    return {
        "schema": "jeeves.fabric.native_supervisor_summary.v1",
        "scope_sha256": scope.binding,
        "model_sha256": scope.model_sha256,
        "tokenizer_sha256": scope.tokenizer_sha256,
        "resource_limits": limits.to_record(),
        "supervisor_status_sha256": fingerprint(native_status),
        "spine_health_sha256": fingerprint(spine_health),
        "status_authority": "canonical-supervised-ai",
        "real_native_inference_qualified": False,
        "release_certified": False,
    }


def require_same_native_identity(worker: Any, *, scope: Scope) -> None:
    if not isinstance(scope, Scope):
        raise ContractHold("typed admitted native principal required")
    active = scope_from_worker(
        worker, workspace=scope.workspace, session=scope.session,
    )
    if active != scope:
        raise ContractHold("native model or principal changed after admission")


__all__ = [
    "scope_from_worker", "limits_from_worker",
    "snapshot_native_status", "require_same_native_identity",
]
