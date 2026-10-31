"""Sealed engine execution endpoints backed by durable cognitive state."""

from __future__ import annotations

import base64
import binascii
import hmac
import sqlite3
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from skeleton.api.engine_authority import EngineAuthorityError
from skeleton.api.engine_service import (
    EngineExecutionCommand,
    EngineExecutionService,
    EngineServiceError,
    EngineSubmissionConflict,
)
from skeleton.persistence.execution_repository import (
    ExecutionRepositoryConflict,
    ExecutionRepositoryError,
)
from skeleton.provider_runtime import (
    ProviderError,
    ProviderImageRequest,
    ProviderSpeechRequest,
    ProviderUnavailableError,
)

router = APIRouter(prefix="/engine", tags=["engine"])


class EngineSubmitBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    command: dict[str, Any]


class EngineCancelBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    reason: str = Field(min_length=1, max_length=2048)


class EngineRuntimePolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_fields(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("runtime policy requires non-null fields")
        return self


class EngineRuntimeServingPatch(EngineRuntimePolicyPatch):
    enabled: bool | None = None
    min_effective_concurrency: int | None = Field(default=None, ge=1, le=32)
    max_effective_concurrency: int | None = Field(default=None, ge=1, le=32)
    target_latency_ms: float | None = Field(default=None, ge=100, le=600000)
    cooldown_seconds: float | None = Field(default=None, ge=0.5, le=300)
    recovery_samples: int | None = Field(default=None, ge=2, le=128)
    max_queue_wait_seconds: float | None = Field(default=None, ge=0.05, le=3600)
    background_max_concurrency: int | None = Field(default=None, ge=0, le=32)
    cache_max_bytes: int | None = Field(default=None, ge=0, le=1073741824)
    cache_ttl_seconds: float | None = Field(default=None, ge=0, le=86400)
    memory_high_watermark: float | None = Field(default=None, ge=0.5, le=0.99)
    memory_low_watermark: float | None = Field(default=None, ge=0.1, le=0.95)
    max_active_per_tenant: int | None = Field(default=None, ge=1, le=32)
    max_queued_per_tenant: int | None = Field(default=None, ge=0, le=65536)
    background_starvation_seconds: float | None = Field(default=None, ge=0.1, le=3600)
    memory_shed_watermark: float | None = Field(default=None, ge=0.5, le=1)


class EngineRuntimeLearningPatch(EngineRuntimePolicyPatch):
    enabled: bool | None = None
    min_samples: int | None = Field(default=None, ge=4, le=10000)
    replay_capacity: int | None = Field(default=None, ge=8, le=256)
    replay_steps: int | None = Field(default=None, ge=0, le=3)
    learning_rate: float | None = Field(default=None, ge=1e-05, le=0.05)
    gradient_clip: float | None = Field(default=None, ge=0.01, le=5)
    max_effort_rounds: int | None = Field(default=None, ge=1, le=3)
    target_latency_seconds: float | None = Field(default=None, ge=0.1, le=86400)
    pressure_threshold: float | None = Field(default=None, ge=0.1, le=1)
    uncertainty_ceiling: float | None = Field(default=None, ge=0.05, le=0.75)
    partition_limit: int | None = Field(default=None, ge=1, le=128)
    retained_outcomes: int | None = Field(default=None, ge=128, le=100000)
    outcome_max_age_days: int | None = Field(default=None, ge=1, le=3650)
    maintenance_receipt_retention: int | None = Field(default=None, ge=16, le=100000)


class EngineRuntimeMaintenancePatch(EngineRuntimePolicyPatch):
    enabled: bool | None = None
    augmentation_enabled: bool | None = None
    maximum_tasks_per_tick: int | None = Field(default=None, ge=1, le=8)
    maximum_queue: int | None = Field(default=None, ge=1, le=8192)
    maximum_scope_queue: int | None = Field(default=None, ge=1, le=8192)
    maximum_retained_tasks: int | None = Field(default=None, ge=1, le=8192)
    maximum_chunk_wall_ms: int | None = Field(default=None, ge=1, le=5000)
    maximum_chunk_cpu_ms: int | None = Field(default=None, ge=1, le=5000)
    maximum_chunk_polls: int | None = Field(default=None, ge=4, le=65536)
    maximum_memory_drop_ppm: int | None = Field(default=None, ge=0, le=1000000)
    maximum_consecutive_failures: int | None = Field(default=None, ge=1, le=32)
    initial_backoff_ms: int | None = Field(default=None, ge=1, le=300000)
    maximum_backoff_ms: int | None = Field(default=None, ge=1, le=86400000)
    preemption_backoff_ms: int | None = Field(default=None, ge=1, le=300000)
    circuit_failure_threshold: int | None = Field(default=None, ge=1, le=32)
    circuit_cooldown_ms: int | None = Field(default=None, ge=1, le=86400000)
    interrupted_lease_grace_ms: int | None = Field(default=None, ge=1000, le=300000)
    priority_aging_ms: int | None = Field(default=None, ge=1000, le=86400000)
    maximum_admission_wait_ms: int | None = Field(default=None, ge=1000, le=3600000)
    clock_jump_tolerance_ms: int | None = Field(default=None, ge=100, le=60000)
    maximum_owner_heartbeat_ms: int | None = Field(default=None, ge=10000, le=300000)
    maximum_chunk_results: int | None = Field(default=None, ge=1, le=16384)
    maximum_ack_retries_per_tick: int | None = Field(default=None, ge=1, le=16)


EngineRuntimeEnabledPatch = EngineRuntimeLearningPatch


class EngineRuntimeControlPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    expected_version: int = Field(ge=1, le=2**63 - 1)
    serving: EngineRuntimeServingPatch | None = None
    learning: EngineRuntimeLearningPatch | None = None
    maintenance: EngineRuntimeMaintenancePatch | None = None
    action: str | None = Field(default=None, pattern="^(trim_cache|clear_cache|drain|resume)$")
    serving_route_id: str | None = Field(default=None, min_length=1, max_length=384)

    @model_validator(mode="after")
    def validate_patch(self):
        fields = self.model_fields_set - {"actor_id", "tenant_id", "expected_version", "serving_route_id"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("runtime control requires a non-null patch")
        if self.serving is not None:
            if not self.serving.model_fields_set or any(
                getattr(self.serving, field) is None for field in self.serving.model_fields_set
            ):
                raise ValueError("serving policy requires non-null fields")
        return self


class EngineLearningCheckpointUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    action: str = Field(pattern="^(import|reset|restore_last_healthy)$")
    expected_policy_version: int = Field(ge=1, le=2**63 - 1)
    expected_state_version: int = Field(ge=1, le=2**63 - 1)
    model_selection_digest: str = Field(pattern="^[0-9a-f]{64}$")
    checkpoint: dict[str, Any] | None = None
    checkpoint_json: str | None = Field(default=None, max_length=256 * 1024)

    @model_validator(mode="after")
    def validate_checkpoint(self):
        count = int(self.checkpoint is not None) + int(self.checkpoint_json is not None)
        if count != (1 if self.action == "import" else 0):
            raise ValueError("import requires exactly one checkpoint representation; other actions accept neither")
        if self.checkpoint_json is not None and len(self.checkpoint_json.encode("utf-8")) > 256 * 1024:
            raise ValueError("checkpoint exceeds the 256 KiB limit")
        return self


class EngineMaintenanceRetry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    source_digest: str = Field(pattern="^[0-9a-f]{64}$")
    expected_attempts: int = Field(ge=0, le=1_000_000)


class EngineMaintenanceCircuitReset(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    expected_generation: int = Field(ge=1, le=8_999_999_999_999_999)
    expected_failure_digest: str = Field(pattern="^[0-9a-f]{64}$")
    source_digest: str = Field(pattern="^[0-9a-f]{64}$")


class EngineImageGenerateBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    operation_id: str = Field(min_length=1, max_length=512)
    prompt: str = Field(min_length=1, max_length=16_384)
    size: str = Field(default="1024x1024", min_length=3, max_length=64)
    quality: str = Field(default="standard", min_length=1, max_length=64)
    count: int = Field(default=1, ge=1, le=4)


class EngineImageVariationBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    operation_id: str = Field(min_length=1, max_length=512)
    image_base64: str = Field(min_length=1, max_length=32 * 1024 * 1024)
    count: int = Field(default=1, ge=1, le=4)
    size: str = Field(default="1024x1024", min_length=3, max_length=64)


class EngineImageEditBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    operation_id: str = Field(min_length=1, max_length=512)
    image_base64: str = Field(min_length=1, max_length=32 * 1024 * 1024)
    mask_base64: str | None = Field(
        default=None,
        max_length=32 * 1024 * 1024,
    )
    prompt: str = Field(min_length=1, max_length=16_384)
    size: str = Field(default="1024x1024", min_length=3, max_length=64)


class EngineSpeechBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    operation_id: str = Field(min_length=1, max_length=512)
    text: str = Field(min_length=1, max_length=16_384)
    voice: str = Field(default="nova", min_length=1, max_length=128)
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    response_format: str = Field(default="mp3", min_length=2, max_length=16)


class EngineStorageAdmissionBody(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=512)
    capability: str = Field(min_length=1, max_length=256)
    resource_id: str = Field(min_length=1, max_length=512)
    write_id: str = Field(min_length=1, max_length=1024)
    storage_bytes: int = Field(ge=1, le=1024 * 1024 * 1024)


class EngineGovernanceWriteBody(BaseModel):
    mode: str = Field(min_length=1, max_length=32)
    plane: str = Field(min_length=1, max_length=64)
    record_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    source_ref: str = Field(min_length=1, max_length=512)
    data_class: str = Field(min_length=1, max_length=64)
    purposes: list[str] = Field(min_length=1, max_length=32)
    deletion_targets: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=32,
    )
    created_at: float | None = Field(default=None, ge=0)
    retention_until: float | None = Field(default=None, ge=0)
    exportable: bool = True


class EngineGovernanceDeletionPlanBody(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=512)
    record_ids: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=10_000,
    )
    reason: str = Field(
        default="tenant-request",
        min_length=1,
        max_length=512,
    )


class EngineGovernancePlanExecutionBody(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=512)


class EngineGovernanceDeletionAckBody(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=512)
    plan_id: str = Field(min_length=1, max_length=512)
    record_id: str = Field(min_length=1, max_length=512)
    target: str = Field(min_length=1, max_length=256)


class EngineToolApprovalBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=512)
    tenant_id: str = Field(min_length=1, max_length=512)
    call_id: str = Field(min_length=1, max_length=256)
    tool_id: str = Field(min_length=1, max_length=128)
    arguments_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    idempotency_key: str = Field(min_length=1, max_length=1024)
    expires_at: datetime


def _engine_service() -> EngineExecutionService:
    from skeleton.api.server import get_state

    service = getattr(get_state(), "engine_execution_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine execution service unavailable",
        )
    return service


def _engine_coordinator():
    from skeleton.api.server import get_state

    return getattr(get_state(), "engine_execution_coordinator", None)


def _engine_service_token() -> str:
    from skeleton.config.settings import get_settings

    token = get_settings().engine.service_token.get_secret_value()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine service authentication is not configured",
        )
    return token


def _verified_service_principal(
    request: Request,
    expected_token: str,
) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, separator, presented = authorization.partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not presented
        or not hmac.compare_digest(presented, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="engine service authentication failed",
        )
    principal = request.headers.get("x-zaibatsu-attester")
    if not principal:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="verified service principal required",
        )
    return principal


def _authorize_media(
    service: EngineExecutionService,
    *,
    principal: str,
    tenant_id: str,
    capability: str,
) -> None:
    try:
        grant = service.authorities.grant_for(principal)
    except EngineAuthorityError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engine media authority denied",
        ) from exc
    if "engine:media" not in grant.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engine media scope denied",
        )
    if not grant.allows_tenant(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engine media tenant denied",
        )
    if not grant.allows_capability(capability):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engine media capability denied",
        )


@router.get("/providers")
def providers(
    request: Request,
    service: Annotated[EngineExecutionService, Depends(_engine_service)],
    coordinator: Annotated[Any, Depends(_engine_coordinator)],
    service_token: Annotated[str, Depends(_engine_service_token)],
    tenant_id: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
) -> dict[str, Any]:
    """Observe the canonical registry under the existing service read grant."""
    principal = _verified_service_principal(request, service_token)
    try:
        grant = service.authorities.grant_for(principal)
    except EngineAuthorityError as exc:
        raise HTTPException(status_code=403, detail="engine provider read denied") from exc
    if "engine:read" not in grant.scopes:
        raise HTTPException(status_code=403, detail="engine provider read denied")
    if tenant_id is not None and not grant.allows_tenant(tenant_id):
        raise HTTPException(status_code=403, detail="engine provider tenant denied")
    if coordinator is None:
        raise HTTPException(status_code=503, detail="engine provider registry unavailable")
    registry = coordinator.provider_registry
    fields = (
        "id", "provider_id", "model", "available", "active", "fallback",
        "architecture_acknowledged", "configured", "readiness_code",
        "execution_mode", "network_policy", "credential_free", "capabilities",
        "context_window", "max_output_tokens", "default_output_tokens",
        "limits_source", "tokenizer", "supports_temperature", "artifact",
        "model_family", "protocol_capabilities", "generation_limits",
        "model_digest", "runtime_digest", "execution_profile_digest", "capacity", "runtime",
        "semantic_verifier_configured", "semantic_verifier_route",
    )
    rows = [{key: value[key] for key in fields if key in value} for value in registry.statuses()]
    artifact_fields = (
        "schema", "model_id", "model_digest", "artifact_sha256", "artifact_bytes",
        "manifest_digest", "runtime_digest", "runtime_kind", "reference",
        "source_model_id", "catalog_digest", "catalog_entry_digest", "catalog_source_sha256",
    )
    for row in rows:
        row.setdefault("id", row.get("provider_id"))
        artifact = row.get("artifact")
        if isinstance(artifact, dict):
            row["artifact"] = {
                key: artifact[key] for key in artifact_fields if key in artifact
            }
        runtime = row.get("runtime")
        serving = runtime.get("serving") if isinstance(runtime, dict) else None
        if isinstance(serving, dict) and isinstance(serving.get("capacity"), dict):
            row["serving_state"] = {
                "draining": serving["draining"],
                "active": runtime["active"],
                "queued": runtime["queued"],
                "effective_concurrency": serving["capacity"]["effective_concurrency"],
            }
        for field, allowed in {
            "generation_limits": (
                "context_window", "max_output_tokens", "max_total_tokens", "shared_context",
                "tokenizer", "limits_source",
                "tokenizer_max_chars", "tokenizer_max_tokens",
                "max_output_utf8_bytes",
            ),
            "capacity": ("max_concurrency", "max_batch_size", "max_queue_size", "cache_entries"),
            "runtime": ("active", "queued", "completed", "failed", "cancelled", "overloaded", "cache_hits", "cache_entries"),
        }.items():
            value = row.get(field)
            if isinstance(value, dict):
                row[field] = {key: value[key] for key in allowed if key in value}
    return {"active": registry.active_id, "available": registry.available, "providers": rows}


def _media_adapter(coordinator):
    if coordinator is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine media runtime unavailable",
        )
    try:
        return coordinator.provider_registry.require_active()
    except ProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine media provider unavailable",
        ) from exc


def _authorize_runtime_control(
    request: Request, service: EngineExecutionService, service_token: str,
    *, tenant_id: str, write: bool = False,
) -> None:
    principal = _verified_service_principal(request, service_token)
    try:
        grant = service.authorities.grant_for(principal)
    except EngineAuthorityError as exc:
        raise HTTPException(status_code=403, detail="engine runtime authority denied") from exc
    scope = "engine:runtime-control" if write else "engine:read"
    if scope not in grant.scopes or not grant.allows_tenant(tenant_id):
        raise HTTPException(status_code=403, detail="engine runtime authority denied")
    if write and not grant.allows_capability("assistant.runtime.control"):
        raise HTTPException(status_code=403, detail="engine runtime capability denied")


@router.get("/runtime-control")
def runtime_control_snapshot(
    request: Request,
    service: Annotated[EngineExecutionService, Depends(_engine_service)],
    coordinator: Annotated[Any, Depends(_engine_coordinator)],
    service_token: Annotated[str, Depends(_engine_service_token)],
    actor_id: Annotated[str, Query(min_length=1, max_length=512)],
    tenant_id: Annotated[str, Query(min_length=1, max_length=512)],
    learning_offset: Annotated[int, Query(ge=0, le=127)] = 0,
) -> dict[str, Any]:
    _authorize_runtime_control(request, service, service_token, tenant_id=tenant_id)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="engine runtime control unavailable")
    try:
        return coordinator.runtime_control.snapshot(actor_id=actor_id, tenant_id=tenant_id, learning_offset=learning_offset)
    except (ExecutionRepositoryError, ValueError, TypeError, sqlite3.Error) as exc:
        _raise_engine_error(exc)


@router.patch("/runtime-control")
def configure_runtime_control(
    request: Request,
    body: EngineRuntimeControlPatch,
    service: Annotated[EngineExecutionService, Depends(_engine_service)],
    coordinator: Annotated[Any, Depends(_engine_coordinator)],
    service_token: Annotated[str, Depends(_engine_service_token)],
) -> dict[str, Any]:
    # The application checks the authenticated operator's administrator role;
    # the engine separately grants this sealed application service write scope.
    _authorize_runtime_control(request, service, service_token, tenant_id=body.tenant_id, write=True)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="engine runtime control unavailable")
    try:
        return coordinator.runtime_control.configure(
            actor_id=body.actor_id,
            tenant_id=body.tenant_id,
            expected_version=body.expected_version,
            serving=None if body.serving is None else body.serving.model_dump(exclude_unset=True),
            learning=None if body.learning is None else body.learning.model_dump(exclude_unset=True),
            maintenance=None if body.maintenance is None else body.maintenance.model_dump(exclude_unset=True),
            action=body.action,
            serving_route_id=body.serving_route_id,
        )
    except (ExecutionRepositoryError, ValueError, TypeError, sqlite3.Error) as exc:
        _raise_engine_error(exc)


@router.get("/runtime-control/learning/partitions/{partition_id}/checkpoint")
def export_runtime_learning_checkpoint(
    request: Request,
    partition_id: str,
    service: Annotated[EngineExecutionService, Depends(_engine_service)],
    coordinator: Annotated[Any, Depends(_engine_coordinator)],
    service_token: Annotated[str, Depends(_engine_service_token)],
    actor_id: Annotated[str, Query(min_length=1, max_length=512)],
    tenant_id: Annotated[str, Query(min_length=1, max_length=512)],
    expected_state_version: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
) -> dict[str, Any]:
    _authorize_runtime_control(request, service, service_token, tenant_id=tenant_id, write=True)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="engine runtime control unavailable")
    try:
        return coordinator.runtime_control.export_learning_checkpoint(
            actor_id=actor_id, tenant_id=tenant_id, partition_id=partition_id,
            expected_state_version=expected_state_version,
        )
    except (ExecutionRepositoryError, ValueError, TypeError, sqlite3.Error) as exc:
        _raise_engine_error(exc)


@router.get("/runtime-control/learning/dataset")
def export_runtime_learning_dataset(
    request: Request,
    service: Annotated[EngineExecutionService, Depends(_engine_service)],
    coordinator: Annotated[Any, Depends(_engine_coordinator)],
    service_token: Annotated[str, Depends(_engine_service_token)],
    actor_id: Annotated[str, Query(min_length=1, max_length=512)],
    tenant_id: Annotated[str, Query(min_length=1, max_length=512)],
    limit: Annotated[int, Query(ge=1, le=256)] = 128,
    cursor: Annotated[str | None, Query(min_length=1, max_length=6144)] = None,
    partition_id: Annotated[str | None, Query(pattern="^[0-9a-f]{64}$")] = None,
    include_untrained: bool = False,
) -> dict[str, Any]:
    _authorize_runtime_control(request, service, service_token, tenant_id=tenant_id, write=True)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="engine runtime control unavailable")
    try:
        return coordinator.runtime_control.export_learning_dataset(
            actor_id=actor_id,
            tenant_id=tenant_id,
            limit=limit,
            cursor=cursor,
            partition_id=partition_id,
            include_untrained=include_untrained,
        )
    except (ExecutionRepositoryError, ValueError, TypeError, sqlite3.Error) as exc:
        _raise_engine_error(exc)


@router.post("/runtime-control/maintenance/circuits/{kind}/reset")
def reset_runtime_maintenance_circuit(
    request: Request,
    kind: str,
    body: EngineMaintenanceCircuitReset,
    service: Annotated[EngineExecutionService, Depends(_engine_service)],
    coordinator: Annotated[Any, Depends(_engine_coordinator)],
    service_token: Annotated[str, Depends(_engine_service_token)],
) -> dict[str, Any]:
    _authorize_runtime_control(request, service, service_token, tenant_id=body.tenant_id, write=True)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="engine runtime control unavailable")
    try:
        return coordinator.runtime_control.reset_maintenance_circuit(kind=kind, **body.model_dump())
    except (ExecutionRepositoryError, ValueError, TypeError, sqlite3.Error) as exc:
        _raise_engine_error(exc)


@router.post("/runtime-control/maintenance/tasks/{task_id}/retry")
def retry_runtime_maintenance(
    request: Request, task_id: str, body: EngineMaintenanceRetry,
    service: Annotated[EngineExecutionService, Depends(_engine_service)],
    coordinator: Annotated[Any, Depends(_engine_coordinator)],
    service_token: Annotated[str, Depends(_engine_service_token)],
) -> dict[str, Any]:
    _authorize_runtime_control(request, service, service_token, tenant_id=body.tenant_id, write=True)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="engine runtime control unavailable")
    try:
        return coordinator.runtime_control.retry_maintenance(
            task_id=task_id, **body.model_dump(),
        )
    except (ExecutionRepositoryError, ValueError, TypeError, sqlite3.Error) as exc:
        _raise_engine_error(exc)


@router.post("/runtime-control/learning/partitions/{partition_id}/checkpoint")
def update_runtime_learning_checkpoint(
    request: Request, partition_id: str, body: EngineLearningCheckpointUpdate,
    service: Annotated[EngineExecutionService, Depends(_engine_service)],
    coordinator: Annotated[Any, Depends(_engine_coordinator)],
    service_token: Annotated[str, Depends(_engine_service_token)],
) -> dict[str, Any]:
    _authorize_runtime_control(request, service, service_token, tenant_id=body.tenant_id, write=True)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="engine runtime control unavailable")
    try:
        return coordinator.runtime_control.configure_learning_checkpoint(
            partition_id=partition_id, **body.model_dump(exclude_unset=True),
        )
    except (ExecutionRepositoryError, ValueError, TypeError, sqlite3.Error) as exc:
        _raise_engine_error(exc)


def _decode_media(raw: str, field: str, *, maximum: int = 20 * 1024 * 1024) -> bytes:
    try:
        decoded = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=field + " is invalid base64",
        ) from exc
    if not decoded or len(decoded) > maximum:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=field + " exceeds media size bound",
        )
    return decoded


def _raise_engine_error(exc: Exception) -> None:
    if isinstance(exc, sqlite3.Error):
        raise HTTPException(status_code=503, detail="engine durable state is temporarily unavailable") from exc
    if isinstance(exc, EngineAuthorityError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="engine authority denied",
        ) from exc
    if isinstance(exc, EngineServiceError):
        normalized = str(exc).lower()
        authority_markers = (
            "different service principal",
            "different actor or tenant",
            "outside engine service grant",
            "service grant is missing required scope",
        )
        if any(marker in normalized for marker in authority_markers):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="engine authority denied",
            ) from exc
    if isinstance(exc, EngineSubmissionConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, ExecutionRepositoryConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, (EngineServiceError, ExecutionRepositoryError)):
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND if "unknown" in detail.lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=detail) from exc
    if isinstance(exc, (ValueError, TypeError)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    raise exc


@router.post("/executions", status_code=status.HTTP_202_ACCEPTED)
async def submit_execution(
    body: EngineSubmitBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        command = EngineExecutionCommand.from_dict(body.command)
        ack = service.submit(
            command,
            verified_service_principal=principal,
            actor_id=body.actor_id,
            tenant_id=body.tenant_id,
        )
        if coordinator is not None:
            await coordinator.ensure_started(command)
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return ack.as_dict()


@router.post("/admission/storage")
def admit_storage_write(
    body: EngineStorageAdmissionBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        receipt = service.consume_external_storage_write(
            verified_service_principal=principal,
            tenant_id=body.tenant_id,
            capability=body.capability,
            resource_id=body.resource_id,
            write_id=body.write_id,
            storage_bytes=body.storage_bytes,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return receipt.as_dict()


@router.post("/governance/writes")
def reconcile_governed_write(
    body: EngineGovernanceWriteBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        receipt = service.reconcile_external_governed_write(
            verified_service_principal=principal,
            mode=body.mode,
            plane=body.plane,
            record_id=body.record_id,
            tenant_id=body.tenant_id,
            source_ref=body.source_ref,
            data_class=body.data_class,
            purposes=tuple(body.purposes),
            deletion_targets=(None if body.deletion_targets is None else tuple(body.deletion_targets)),
            created_at=body.created_at,
            retention_until=body.retention_until,
            exportable=body.exportable,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return receipt.as_dict()


@router.post("/governance/retention/plan")
def plan_governance_retention(
    body: EngineGovernancePlanExecutionBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.plan_external_governance_retention(
            verified_service_principal=principal,
            tenant_id=body.tenant_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.post("/governance/deletions")
def request_governance_deletion(
    body: EngineGovernanceDeletionPlanBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.request_external_governance_deletion(
            verified_service_principal=principal,
            tenant_id=body.tenant_id,
            record_ids=(None if body.record_ids is None else tuple(body.record_ids)),
            reason=body.reason,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.post("/governance/deletions/{plan_id}/execute-engine-targets")
async def execute_governance_engine_targets(
    plan_id: str,
    body: EngineGovernancePlanExecutionBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return await service.execute_external_governance_engine_targets(
            verified_service_principal=principal,
            tenant_id=body.tenant_id,
            plan_id=plan_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.post("/governance/deletions/acknowledgements")
def acknowledge_governance_deletion(
    body: EngineGovernanceDeletionAckBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.acknowledge_external_governance_deletion(
            verified_service_principal=principal,
            tenant_id=body.tenant_id,
            plan_id=body.plan_id,
            record_id=body.record_id,
            target=body.target,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.get("/governance/inventory")
def governance_inventory(
    request: Request,
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.external_governance_inventory(
            verified_service_principal=principal,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.get("/executions/{execution_id}")
def execution_status(
    execution_id: str,
    request: Request,
    actor_id: str = Query(..., min_length=1, max_length=512),
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.status(
            execution_id,
            verified_service_principal=principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
        ).as_dict()
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.get("/executions/{execution_id}/handoff")
def execution_handoff_binding(
    execution_id: str,
    request: Request,
    actor_id: str = Query(..., min_length=1, max_length=512),
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.handoff_binding(
            execution_id,
            verified_service_principal=principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    body: EngineCancelBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        cancelled = service.cancel(
            execution_id,
            verified_service_principal=principal,
            actor_id=body.actor_id,
            tenant_id=body.tenant_id,
        )
        if coordinator is not None and cancelled.execution_state not in {"completed", "failed", "cancelled"}:
            await coordinator.interrupt_cancelled_execution(execution_id)
            cancelled = service.status(
                execution_id,
                verified_service_principal=principal,
                actor_id=body.actor_id,
                tenant_id=body.tenant_id,
            )
        return cancelled.as_dict()
    except Exception as exc:
        _raise_engine_error(exc)
        raise


@router.get("/executions/{execution_id}/tool-approvals/pending")
def pending_tool_approvals(
    execution_id: str,
    request: Request,
    actor_id: str = Query(..., min_length=1, max_length=512),
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        pending = service.pending_tool_approvals(
            execution_id,
            verified_service_principal=principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return {
        "execution_id": execution_id,
        "pending": [dict(item) for item in pending],
    }


@router.post(
    "/executions/{execution_id}/tool-approvals",
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_tool_call(
    execution_id: str,
    body: EngineToolApprovalBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        approval = service.approve_tool_call(
            execution_id,
            verified_service_principal=principal,
            actor_id=body.actor_id,
            tenant_id=body.tenant_id,
            call_id=body.call_id,
            tool_id=body.tool_id,
            arguments_digest=body.arguments_digest,
            idempotency_key=body.idempotency_key,
            expires_at=body.expires_at,
        )
        if coordinator is not None:
            await coordinator.ensure_execution(execution_id)
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return approval.as_dict()


@router.post("/media/images/generate")
async def generate_engine_image(
    body: EngineImageGenerateBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    _authorize_media(
        service,
        principal=principal,
        tenant_id=body.tenant_id,
        capability="media.image",
    )
    adapter = _media_adapter(coordinator)
    try:
        result = await adapter.generate_image(
            ProviderImageRequest(
                prompt=body.prompt,
                size=body.size,
                quality=body.quality,
                count=body.count,
                model="gpt-image-1",
                tenant_id=body.tenant_id,
                operation_id=body.operation_id,
                purpose="image-generation",
            )
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine image generation failed",
        ) from exc
    return {
        "provider": result.provider,
        "model": result.model,
        "images": [dict(item) for item in result.images],
        "request_id": result.request_id,
        "latency_ms": result.latency_ms,
        "governance_decision_id": result.governance_decision_id,
        "admission_decision_id": result.admission_decision_id,
        "data_class": result.data_class,
    }


@router.post("/media/images/variation")
async def vary_engine_image(
    body: EngineImageVariationBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    _authorize_media(
        service,
        principal=principal,
        tenant_id=body.tenant_id,
        capability="media.image",
    )
    adapter = _media_adapter(coordinator)
    image = _decode_media(body.image_base64, "image_base64")
    try:
        result = await adapter.create_image_variation(
            image,
            count=body.count,
            size=body.size,
            tenant_id=body.tenant_id,
            operation_id=body.operation_id,
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine image variation failed",
        ) from exc
    return {
        "provider": result.provider,
        "model": result.model,
        "images": [dict(item) for item in result.images],
        "request_id": result.request_id,
        "latency_ms": result.latency_ms,
        "governance_decision_id": result.governance_decision_id,
        "admission_decision_id": result.admission_decision_id,
        "data_class": result.data_class,
    }


@router.post("/media/images/edit")
async def edit_engine_image(
    body: EngineImageEditBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    _authorize_media(
        service,
        principal=principal,
        tenant_id=body.tenant_id,
        capability="media.image",
    )
    adapter = _media_adapter(coordinator)
    image = _decode_media(body.image_base64, "image_base64")
    mask = None if body.mask_base64 is None else _decode_media(body.mask_base64, "mask_base64")
    try:
        result = await adapter.edit_image(
            image,
            prompt=body.prompt,
            mask=mask,
            size=body.size,
            tenant_id=body.tenant_id,
            operation_id=body.operation_id,
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine image edit failed",
        ) from exc
    return {
        "provider": result.provider,
        "model": result.model,
        "images": [dict(item) for item in result.images],
        "request_id": result.request_id,
        "latency_ms": result.latency_ms,
        "governance_decision_id": result.governance_decision_id,
        "admission_decision_id": result.admission_decision_id,
        "data_class": result.data_class,
    }


@router.post("/media/speech")
async def synthesize_engine_speech(
    body: EngineSpeechBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
    coordinator=Depends(_engine_coordinator),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    _authorize_media(
        service,
        principal=principal,
        tenant_id=body.tenant_id,
        capability="media.speech",
    )
    adapter = _media_adapter(coordinator)
    try:
        result = await adapter.synthesize_speech(
            ProviderSpeechRequest(
                text=body.text,
                voice=body.voice,
                speed=body.speed,
                model="tts-1-hd",
                response_format=body.response_format,
                tenant_id=body.tenant_id,
                operation_id=body.operation_id,
                purpose="expressive-speech-synthesis",
            )
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="engine speech synthesis failed",
        ) from exc
    if len(result.audio) > 24 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="engine speech result exceeds size bound",
        )
    return {
        "provider": result.provider,
        "model": result.model,
        "response_format": result.response_format,
        "audio_base64": base64.b64encode(result.audio).decode("ascii"),
        "request_id": result.request_id,
        "latency_ms": result.latency_ms,
        "governance_decision_id": result.governance_decision_id,
        "admission_decision_id": result.admission_decision_id,
        "data_class": result.data_class,
    }


def authorize_execution_events(
    request: Request,
    execution_id: str,
    *,
    actor_id: str,
    tenant_id: str,
    service: EngineExecutionService | None = None,
    service_token: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Single source of truth for execution-events access.

    Verifies the bearer service token + gate attester, then the
    ``engine:events`` grant and actor/tenant ownership via
    ``EngineExecutionService.events``. Shared by this route and the realtime
    ``GET /api/v1/events?job_id=`` stream (Jenkins S1-1). Raises
    ``HTTPException`` on any failure; returns ``(principal, snapshot)``.
    """
    if service is None:
        service = _engine_service()
    if service_token is None:
        service_token = _engine_service_token()
    principal = _verified_service_principal(request, service_token)
    try:
        snapshot = service.events(
            execution_id,
            verified_service_principal=principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return principal, snapshot


@router.get("/executions/{execution_id}/events")
def execution_events(
    execution_id: str,
    request: Request,
    actor_id: str = Query(..., min_length=1, max_length=512),
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal, snapshot = authorize_execution_events(
        request,
        execution_id,
        actor_id=actor_id,
        tenant_id=tenant_id,
        service=service,
        service_token=service_token,
    )
    # ADR-realtime-transport (#4101): with ``Accept: text/event-stream`` this
    # route is the execution-scoped filtered view of ``/api/v1/events`` and
    # emits the same v1 envelope. Authorization above is unchanged; JSON
    # callers keep the existing response.
    from skeleton.api.realtime_routes import execution_stream_or_none

    stream = execution_stream_or_none(request, execution_id, principal=str(principal))
    # A Response instance bypasses the dict response model (FastAPI contract).
    return snapshot if stream is None else stream  # type: ignore[return-value]


__all__ = [
    "_engine_coordinator",
    "_engine_service",
    "_engine_service_token",
    "authorize_execution_events",
    "router",
]
