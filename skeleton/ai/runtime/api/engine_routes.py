"""Sealed engine execution endpoints backed by durable cognitive state."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

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
            status.HTTP_404_NOT_FOUND
            if "unknown" in detail.lower()
            else status.HTTP_422_UNPROCESSABLE_ENTITY
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
            deletion_targets=(
                None
                if body.deletion_targets is None
                else tuple(body.deletion_targets)
            ),
            created_at=body.created_at,
            retention_until=body.retention_until,
            exportable=body.exportable,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise
    return receipt.as_dict()


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


@router.post("/executions/{execution_id}/cancel")
def cancel_execution(
    execution_id: str,
    body: EngineCancelBody,
    request: Request,
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.cancel(
            execution_id,
            verified_service_principal=principal,
            actor_id=body.actor_id,
            tenant_id=body.tenant_id,
        ).as_dict()
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
    mask = (
        None
        if body.mask_base64 is None
        else _decode_media(body.mask_base64, "mask_base64")
    )
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


@router.get("/executions/{execution_id}/events")
def execution_events(
    execution_id: str,
    request: Request,
    actor_id: str = Query(..., min_length=1, max_length=512),
    tenant_id: str = Query(..., min_length=1, max_length=512),
    service: EngineExecutionService = Depends(_engine_service),
    service_token: str = Depends(_engine_service_token),
) -> dict[str, Any]:
    principal = _verified_service_principal(request, service_token)
    try:
        return service.events(
            execution_id,
            verified_service_principal=principal,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        _raise_engine_error(exc)
        raise


__all__ = [
    "router",
    "_engine_coordinator",
    "_engine_service",
    "_engine_service_token",
]
